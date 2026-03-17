"""
Agent runtime runner: multi-step loop with run/step persistence.

When tool_registry is provided, tool_call actions are executed and results
fed back into the model until final or limits reached.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Protocol

from app.config import get_settings
from app.engine import _call_provider, _merge_and_truncate_memory, _memory_segment_text, write_back_session_events
from app.models import MemoryPolicy
from app.preset_loader import Preset
from app.providers import BaseProvider
from app.storage import run_store
from app.storage import session_store
from app.utils.redaction import cap_text, redact_secrets
from app.utils.run_logger import log_run_finish, log_run_start, log_step

logger = logging.getLogger("agent-gateway")

# Action contract: model returns exactly one of these.
ACTION_SCHEMA: Dict[str, Any] = {
    "oneOf": [
        {
            "type": "object",
            "required": ["type", "output"],
            "properties": {
                "type": {"const": "final"},
                "output": {},
            },
            "additionalProperties": True,
        },
        {
            "type": "object",
            "required": ["type", "tool_name", "args"],
            "properties": {
                "type": {"const": "tool_call"},
                "tool_name": {"type": "string"},
                "args": {},
            },
            "additionalProperties": True,
        },
    ]
}

TOOLS_DISABLED_MESSAGE = "Tool calls are not enabled yet for this deployment."


class ToolRegistry(Protocol):
    """Interface for tool execution. execute() raises ToolExecutionError on policy/execution failure."""

    def execute(self, tool_name: str, args: Dict[str, Any], run_context: Any) -> Dict[str, Any]:
        ...


def _build_prompt(
    preset: Preset,
    merged_events: List[Dict[str, Any]],
    input_payload: Dict[str, Any],
    conversation_turns: List[Dict[str, Any]],
    tool_registry: Optional[ToolRegistry] = None,
    run_context: Optional[Any] = None,
    max_tool_prompt_chars: int = 8000,
    running_summary: Optional[str] = None,
) -> str:
    """Build full prompt with optional tool description and conversation history."""
    pretty_input = json.dumps(input_payload, indent=2, sort_keys=True)
    parts = [
        preset.prompt.strip(),
        "",
        f"# Primitive: {preset.primitive}",
    ]
    if running_summary:
        rs = running_summary.strip()
        if rs:
            parts.append("# Memory (summary):\n" + rs + "\n\n")
    if merged_events:
        parts.append(_memory_segment_text(merged_events))
    parts.append(f"# Input JSON:\n{pretty_input}\n\n")

    if tool_registry is not None and run_context is not None and run_context.allowed_tools:
        tool_lines: List[str] = []
        allowed = run_context.allowed_tools
        if "http_request" in allowed:
            tool_lines.append(
                "- http_request: args { method?, url (required), headers?, query?, json?, data? }. "
                "method one of GET,POST,PUT,PATCH,DELETE. Do not pass Authorization or Cookie."
            )
        if "github_repo_read" in allowed:
            tool_lines.append(
                "- github_repo_read: args { owner, repo (required), ref?, path?, mode (overview|tree|file|sample), max_entries?, max_file_chars? }. "
                "Read-only repo inspection."
            )
        for name in allowed:
            if name not in ("http_request", "github_repo_read") and name:
                tool_lines.append(f"- {name}: (see tool schema)")
        parts.append("# Available tools (use only when necessary; respect allowed domains):\n")
        parts.append("\n".join(tool_lines) + "\n\n")
        tools_list = ", ".join(f'"{t}"' for t in allowed)
        parts.append(
            f"Respond with JSON: either {{\"type\": \"final\", \"output\": <result>}} or "
            f"{{\"type\": \"tool_call\", \"tool_name\": <one of {tools_list}>, \"args\": {{...}}}}.\n"
            "Return final when you have enough information.\n\n"
        )

    for turn in conversation_turns:
        parts.append("Assistant: " + json.dumps(turn["action"], sort_keys=True) + "\n")
        if turn.get("tool_result") is not None:
            tool_result_str = json.dumps(turn["tool_result"], sort_keys=True)
            if max_tool_prompt_chars > 0 and len(tool_result_str) > max_tool_prompt_chars:
                tool_result_str = cap_text(tool_result_str, max_tool_prompt_chars)
            parts.append("Tool (" + turn.get("tool_name", "") + "): " + tool_result_str + "\n\n")
        parts.append("Respond with next JSON action (final or tool_call).\n\n")

    if not conversation_turns:
        parts.append(
            "Respond ONLY with a single JSON object. It must be exactly one of:\n"
            '- {"type": "final", "output": <your result>}\n'
            '- {"type": "tool_call", "tool_name": "<name>", "args": <object>}\n'
            "No other text or markdown."
        )
    return "\n".join(parts)


def run_runner(
    *,
    preset: Preset,
    provider: BaseProvider,
    input_payload: Dict[str, Any],
    run_id: str,
    session_id: Optional[str] = None,
    request_id: Optional[str] = None,
    tool_registry: Optional[ToolRegistry] = None,
    max_steps: Optional[int] = None,
    max_wall_time_seconds: Optional[int] = None,
) -> None:
    """
    Execute the agent run: set status running, run loop (final or tool_call),
    persist steps, and optionally write back to session on success.
    When tool_registry is set, tool calls are executed and results fed back until final or limits.
    """
    from app.runtime.tools.registry import build_run_context
    from app.runtime.tools.http_tool import ToolExecutionError

    settings = get_settings()
    max_steps = max_steps if max_steps is not None else settings.max_steps
    max_wall_time_seconds = max_wall_time_seconds if max_wall_time_seconds is not None else settings.max_wall_time_seconds

    run_context = None
    if tool_registry is not None:
        run_context = build_run_context(run_id=run_id, preset=preset)

    run_store.set_run_status(run_id, "running")
    try:
        log_run_start(run_id, preset.id, getattr(preset, "version", "unknown"))
    except Exception:
        pass
    start_wall = time.monotonic()

    # Load merged memory if session_id
    merged_events: List[Dict[str, Any]] = []
    running_summary: Optional[str] = None
    if session_id:
        session = session_store.get_session(session_id)
        stored: List[Dict[str, Any]] = []
        if session and session.get("events"):
            stored = [
                {
                    "role": e.get("role", "user"),
                    "content": e.get("content", ""),
                    "event_type": e.get("event_type"),
                    "run_id": e.get("run_id"),
                    "step_index": e.get("step_index"),
                    "tool_name": e.get("tool_name"),
                }
                for e in session["events"]
            ]
            running_summary = str(session.get("running_summary") or "") or None
        policy = getattr(preset, "memory_policy", None) or MemoryPolicy(mode="last_n", max_messages=10, max_chars=8000)
        merged_events = _merge_and_truncate_memory(stored, None, policy)

    conversation_turns: List[Dict[str, Any]] = []
    max_tool_prompt_chars = get_settings().max_tool_prompt_chars
    prompt = _build_prompt(
        preset,
        merged_events,
        input_payload,
        conversation_turns,
        tool_registry,
        run_context,
        max_tool_prompt_chars=max_tool_prompt_chars,
        running_summary=running_summary,
    )

    final_output: Optional[Dict[str, Any]] = None
    raw_text_for_session: Optional[str] = None
    succeeded = False

    for step_index in range(1, max_steps + 1):
        if time.monotonic() - start_wall > max_wall_time_seconds:
            err_code = "timeout"
            run_store.append_run_step(
                run_id, step_index, "error", {},
                error="max_wall_time_exceeded",
                error_code=err_code,
            )
            run_store.set_run_status(run_id, "failed", error=f"{err_code}: max_wall_time_exceeded")
            try:
                log_run_finish(run_id, "failed", error="max_wall_time_exceeded")
            except Exception:
                pass
            return

        model_start = time.monotonic()
        try:
            result = _call_provider(provider, prompt=prompt, schema=ACTION_SCHEMA)
        except Exception as exc:
            err_code = "provider_failure"
            safe_msg = str(exc)[:500]
            run_store.append_run_step(
                run_id, step_index, "error", {},
                error=safe_msg,
                error_code=err_code,
            )
            run_store.set_run_status(run_id, "failed", error=f"{err_code}: {safe_msg}")
            try:
                log_run_finish(run_id, "failed", error=safe_msg)
            except Exception:
                pass
            return
        model_latency_ms = int((time.monotonic() - model_start) * 1000)

        raw_text_for_session = result.raw_text
        parsed = result.parsed_json
        if not isinstance(parsed, dict):
            err_code = "invalid_action_format"
            run_store.append_run_step(
                run_id, step_index, "error", {},
                error="invalid_action_format",
                error_code=err_code,
            )
            run_store.set_run_status(run_id, "failed", error=f"{err_code}: invalid_action_format")
            try:
                log_run_finish(run_id, "failed", error="invalid_action_format")
            except Exception:
                pass
            return

        action_type = parsed.get("type")
        run_store.append_run_step(
            run_id, step_index, "llm_action", parsed,
            latency_ms=model_latency_ms,
        )
        try:
            log_step(run_id, step_index, "llm_action", action_type or "llm_action", latency_ms=model_latency_ms)
        except Exception:
            pass
        run_store.increment_run_step_count(run_id)

        if action_type == "final":
            output_val = parsed.get("output")
            if output_val is None:
                err_code = "missing_output"
                run_store.append_run_step(
                    run_id, step_index + 1, "error", parsed,
                    error="missing_output",
                    error_code=err_code,
                )
                run_store.set_run_status(run_id, "failed", error=f"{err_code}: missing_output")
                try:
                    log_run_finish(run_id, "failed", error="missing_output")
                except Exception:
                    pass
                return
            final_output = output_val if isinstance(output_val, dict) else {"result": output_val}
            run_store.append_run_step(run_id, step_index + 1, "final", parsed)
            run_store.set_run_status(run_id, "succeeded", output_json=final_output)
            try:
                log_run_finish(run_id, "succeeded")
            except Exception:
                pass
            succeeded = True
            break

        if action_type == "tool_call":
            tool_name = parsed.get("tool_name") or ""
            tool_args = parsed.get("args")
            if not isinstance(tool_args, dict):
                tool_args = {}
            # Store redacted args
            run_store.append_run_step(
                run_id, step_index + 1, "tool_call", parsed,
                tool_name=tool_name, tool_args_json=redact_secrets(tool_args)
            )
            if tool_registry is None:
                err_code = "tools_disabled"
                run_store.append_run_step(
                    run_id, step_index + 2, "error", {},
                    error=TOOLS_DISABLED_MESSAGE,
                    error_code=err_code,
                )
                run_store.set_run_status(run_id, "failed", error=f"{err_code}: {TOOLS_DISABLED_MESSAGE}")
                try:
                    log_run_finish(run_id, "failed", error=TOOLS_DISABLED_MESSAGE)
                except Exception:
                    pass
                return
            try:
                tool_start = time.monotonic()
                tool_result = tool_registry.execute(tool_name, tool_args, run_context)
                tool_latency_ms = int((time.monotonic() - tool_start) * 1000)
            except ToolExecutionError as e:
                err_code = "tool_execution_failed"
                err_msg = getattr(e, "message", str(e))[:500]
                run_store.append_run_step(
                    run_id, step_index + 2, "error", {},
                    error=err_msg,
                    error_code=err_code,
                )
                run_store.set_run_status(run_id, "failed", error=f"{err_code}: {err_msg}")
                try:
                    log_run_finish(run_id, "failed", error=err_msg)
                except Exception:
                    pass
                return
            run_context.tool_calls_used += 1
            run_store.append_run_step(
                run_id, step_index + 2, "tool_result", parsed,
                tool_name=tool_name, tool_result_json=tool_result,
                tool_latency_ms=tool_latency_ms,
                latency_ms=tool_latency_ms,
            )
            try:
                if tool_name == "http_request":
                    tr_summary = str(tool_result.get("status_code", "")) + " " + (str(tool_result.get("text", ""))[:200] or "")
                else:
                    # Non-HTTP tools: safe summary without assuming status_code/text
                    tr_summary = str(tool_result)[:200] if tool_result else ""
                log_step(run_id, step_index + 2, "tool_result", tr_summary, latency_ms=tool_latency_ms)
            except Exception:
                pass
            # Normalize for model: status_code, content_type, body (capped), truncated, url
            from app.runtime.tools.http_tool import normalize_http_result_for_model
            if tool_name == "http_request":
                tool_result_for_prompt = normalize_http_result_for_model(
                    tool_result, url=tool_args.get("url") if isinstance(tool_args.get("url"), str) else None
                )
            else:
                tool_result_for_prompt = tool_result
            conversation_turns.append({
                "action": parsed,
                "tool_name": tool_name,
                "tool_result": tool_result_for_prompt,
            })
            prompt = _build_prompt(
                preset, merged_events, input_payload, conversation_turns,
                tool_registry, run_context, max_tool_prompt_chars=max_tool_prompt_chars,
            )
            continue

        err_code = "unknown_action_type"
        run_store.append_run_step(
            run_id, step_index + 1, "error", parsed,
            error="unknown_action_type",
            error_code=err_code,
        )
        run_store.set_run_status(run_id, "failed", error=f"{err_code}: unknown_action_type")
        try:
            log_run_finish(run_id, "failed", error="unknown_action_type")
        except Exception:
            pass
        return

    if not succeeded:
        err_code = "max_steps_exceeded"
        run_store.append_run_step(
            run_id, max_steps + 1, "error", {},
            error="limit reached",
            error_code=err_code,
        )
        run_store.set_run_status(run_id, "failed", error=f"{err_code}: limit reached")
        try:
            log_run_finish(run_id, "failed", error="max_steps_exceeded")
        except Exception:
            pass
        return

    if succeeded and session_id and getattr(preset, "supports_memory", False) and final_output is not None:
        write_back_session_events(
            session_id=session_id,
            preset=preset,
            request_id=request_id,
            input_payload=input_payload,
            output=final_output,
            raw_text=raw_text_for_session,
        )
        # Best-effort running summary update; failures must not break the run.
        try:
            from app.memory.summarizer import maybe_update_running_summary

            events = session_store.get_session_events(session_id)
            maybe_update_running_summary(
                provider=provider,
                preset=preset,
                session_id=session_id,
                events=events,
            )
        except Exception:
            logger.warning("running_summary update failed for session_id=%s", session_id)
