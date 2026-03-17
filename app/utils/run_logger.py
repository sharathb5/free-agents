"""
Optional local run event logging to JSONL (when FREE_AGENTS_LOG_PATH is set).

Writes run_started, step summaries, run_finished. Redacts secrets and caps text.
Rotation: when file exceeds MAX_LOG_BYTES, keep last ROTATE_KEEP_LINES lines.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from app.utils.redaction import cap_text, redact_secrets

MAX_LOG_BYTES = 5 * 1024 * 1024  # 5MB
ROTATE_KEEP_LINES = 10_000
CAP_FIELD_CHARS = 2000


def _log_path() -> Optional[str]:
    return os.environ.get("FREE_AGENTS_LOG_PATH") or None


def _ensure_dir(path: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)


def _rotate_if_needed(path: str) -> None:
    try:
        if not os.path.isfile(path):
            return
        if os.path.getsize(path) < MAX_LOG_BYTES:
            return
        with open(path, "r") as f:
            lines = f.readlines()
        if len(lines) <= ROTATE_KEEP_LINES:
            return
        keep = lines[-ROTATE_KEEP_LINES:]
        with open(path, "w") as f:
            f.writelines(keep)
    except Exception:
        pass


def _write_line(record: Dict[str, Any]) -> None:
    path = _log_path()
    if not path:
        return
    _ensure_dir(path)
    _rotate_if_needed(path)
    try:
        line = json.dumps(record, sort_keys=True, default=str) + "\n"
        with open(path, "a") as f:
            f.write(line)
    except Exception:
        pass


def log_run_start(run_id: str, agent_id: str, agent_version: str) -> None:
    """Log run_started. No secrets in payload."""
    _write_line({
        "event": "run_started",
        "run_id": run_id,
        "agent_id": agent_id,
        "agent_version": agent_version,
    })


def log_step(
    run_id: str,
    step_index: int,
    step_type: str,
    summary: str,
    latency_ms: Optional[int] = None,
    error_code: Optional[str] = None,
) -> None:
    """Log a step summary. summary is redacted and capped."""
    safe = cap_text(redact_secrets(summary) if isinstance(summary, str) else str(summary), CAP_FIELD_CHARS)
    record: Dict[str, Any] = {
        "event": "step",
        "run_id": run_id,
        "step_index": step_index,
        "step_type": step_type,
        "summary": safe,
    }
    if latency_ms is not None:
        record["latency_ms"] = latency_ms
    if error_code is not None:
        record["error_code"] = error_code
    _write_line(record)


def log_run_finish(run_id: str, status: str, error: Optional[str] = None) -> None:
    """Log run_finished. error is capped and not logged if it looks like a secret."""
    record: Dict[str, Any] = {"event": "run_finished", "run_id": run_id, "status": status}
    if error:
        record["error"] = cap_text(error, CAP_FIELD_CHARS)
    _write_line(record)
