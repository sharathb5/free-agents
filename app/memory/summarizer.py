"""
Session running_summary maintenance (Agent Runtime Part 4).

maybe_update_running_summary() is called after successful invoke/run write-back.
It is conservative: best-effort only, never raises, and respects memory policy
and max_chars. It summarizes older events while keeping recent context fresh.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List
import time

from app.config import get_settings
from app.models import MemoryPolicy
from app.preset_loader import Preset
from app.providers import BaseProvider, ProviderResult
from app.storage import session_store
from app.utils.redaction import cap_text, redact_secrets

logger = logging.getLogger("agent-gateway")


def _coerce_policy(preset: Preset) -> MemoryPolicy:
    policy = getattr(preset, "memory_policy", None)
    if isinstance(policy, MemoryPolicy):
        return policy
    return MemoryPolicy(mode="last_n", max_messages=10, max_chars=8000)


def _summarizer_prompt(existing_summary: str, events_slice: List[Dict[str, Any]]) -> str:
    """Build a safe prompt for the running summary LLM call."""
    lines: List[str] = []
    lines.append(
        "You are a memory summarizer for a long-lived user session.\n"
        "Your job is to maintain a concise running summary of the user's goals,"
        " preferences, and important factual context.\n"
        "Do NOT include secrets such as passwords, API keys, tokens, or cookies."
    )
    if existing_summary.strip():
        lines.append("\n# Existing running summary:\n")
        lines.append(existing_summary.strip())
    lines.append("\n# New events to summarize (older first):\n")
    for ev in events_slice:
        role = ev.get("role", "user")
        content = (ev.get("content") or "").strip()
        if not content:
            continue
        # Apply redaction and cap per-event for safety.
        safe = cap_text(str(redact_secrets(content)), 500)
        lines.append(f"- {role}: {safe}")
    lines.append(
        "\nRespond ONLY with a concise bullet-point summary in plain text. "
        "Do not mention that you are an AI model."
    )
    return "\n".join(lines)


def maybe_update_running_summary(
    *,
    provider: BaseProvider,
    preset: Preset,
    session_id: str,
    events: List[Dict[str, Any]],
) -> None:
    """
    Best-effort running summary update.

    Triggered when:
    - new events since last summary >= summary_batch_size, OR
    - approximate total chars in memory exceeds 70% of max_chars.
    """
    if not events:
        return

    settings = get_settings()
    policy = _coerce_policy(preset)
    cfg_batch = max(1, int(getattr(settings, "summary_batch_size", 12)))
    cfg_max_chars = max(200, int(getattr(settings, "summary_max_chars", 1500)))

    try:
        summary_state = session_store.get_session_summary(session_id)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("get_session_summary failed for session_id=%s: %s", session_id, exc)
        return

    running_summary = summary_state.get("running_summary") or ""
    summarized_count = int(summary_state.get("summary_message_count") or 0)
    total_events = len(events)
    if total_events <= summarized_count:
        return

    new_events_count = total_events - summarized_count

    # Rough char budget check across user/assistant content.
    total_chars = 0
    for ev in events:
        if ev.get("role") in ("user", "assistant", "system"):
            total_chars += len(str(ev.get("content") or ""))
    char_threshold = int(0.7 * (policy.max_chars or 8000))
    trigger_chars = total_chars >= char_threshold if char_threshold > 0 else False

    if new_events_count < cfg_batch and not trigger_chars:
        return

    # Summarize older events, excluding the most recent K (from config).
    recent_k = max(0, int(getattr(settings, "memory_recent_k", 8)))
    start_index = summarized_count
    end_index = max(start_index, total_events - recent_k)
    if end_index <= start_index:
        return
    slice_events = events[start_index:end_index]
    if not slice_events:
        return

    # Build safe prompt and call provider over only previously-unsummarized events.
    prompt = _summarizer_prompt(
        existing_summary=cap_text(running_summary, cfg_max_chars),
        events_slice=slice_events,
    )

    try:
        result = provider.complete_json(
            prompt,
            schema={
                "type": "object",
                "required": ["summary"],
                "properties": {"summary": {"type": "string"}},
                "additionalProperties": True,
            },
        )
        if isinstance(result, ProviderResult):
            parsed = result.parsed_json
        else:
            parsed = result  # type: ignore[assignment]
        if not isinstance(parsed, dict):
            logger.warning("running_summary summarizer returned non-dict; skipping update")
            return
        new_text = str(parsed.get("summary") or "").strip()
        if not new_text:
            return
        # Compose new running summary, prefixed with a small header for debugging.
        combined_body = running_summary.strip()
        if combined_body:
            combined_body = combined_body + "\n" + new_text
        else:
            combined_body = new_text

        # Header: when the summary was updated and how many events it covers.
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        header = f"(Summary updated: {now}; covers first {end_index} events)"
        combined = header + "\n" + combined_body if combined_body else header

        # Hard cap: if over limit, keep last lines until within cfg_max_chars.
        if len(combined) > cfg_max_chars:
            lines = combined.splitlines()
            kept: List[str] = []
            total = 0
            for line in reversed(lines):
                length = len(line) + 1  # account for newline
                if total + length <= cfg_max_chars:
                    kept.append(line)
                    total += length
                else:
                    break
            if kept:
                combined = "\n".join(reversed(kept))
            else:
                combined = cap_text(combined, cfg_max_chars)
        try:
            session_store.update_session_summary(
                session_id=session_id,
                new_summary=combined,
                summarized_count=end_index,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("update_session_summary failed for session_id=%s: %s", session_id, exc)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("running_summary summarizer failed for session_id=%s: %s", session_id, exc)

