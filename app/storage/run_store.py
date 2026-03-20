"""
Run store: SQLite- or Postgres-backed runs and run_steps.

runs: (id, agent_id, agent_version, status, created_at, updated_at, session_id, input_json, output_json, error, step_count, usage_json)
run_steps: (id, run_id, step_index, step_type, model, action_json, tool_name, tool_args_json, tool_result_json, created_at, error)
Uses same DB as session_store (db_path / DATABASE_URL).
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.storage.db import connect, is_postgres, sql

logger = logging.getLogger("agent-gateway")

_run_db_initialized = False
_run_db_init_lock = threading.Lock()


def _ensure_sqlite_dir() -> None:
    if is_postgres():
        return
    from app.config import get_settings

    path = get_settings().db_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def _ensure_runs_tables(conn: Any) -> None:
    if not is_postgres():
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                agent_version TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                session_id TEXT,
                input_json TEXT NOT NULL,
                output_json TEXT,
                error TEXT,
                step_count INTEGER NOT NULL DEFAULT 0,
                usage_json TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_runs_status_created_at ON runs (status, created_at)"
        )
    else:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                agent_version TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                session_id TEXT,
                input_json TEXT NOT NULL,
                output_json TEXT,
                error TEXT,
                step_count INTEGER NOT NULL DEFAULT 0,
                usage_json TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_runs_status_created_at ON runs (status, created_at)"
        )


def _ensure_run_steps_tables(conn: Any) -> None:
    if not is_postgres():
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS run_steps (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                step_type TEXT NOT NULL,
                model TEXT,
                action_json TEXT NOT NULL,
                tool_name TEXT,
                tool_args_json TEXT,
                tool_result_json TEXT,
                created_at TEXT NOT NULL,
                error TEXT,
                FOREIGN KEY (run_id) REFERENCES runs(id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_run_steps_run_id_step_index ON run_steps (run_id, step_index)"
        )
    else:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS run_steps (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                step_type TEXT NOT NULL,
                model TEXT,
                action_json TEXT NOT NULL,
                tool_name TEXT,
                tool_args_json TEXT,
                tool_result_json TEXT,
                created_at TEXT NOT NULL,
                error TEXT,
                FOREIGN KEY (run_id) REFERENCES runs(id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_run_steps_run_id_step_index ON run_steps (run_id, step_index)"
        )
    _ensure_run_steps_columns(conn)


def _ensure_run_steps_columns(conn: Any) -> None:
    """Additive migration: add tool_latency_ms and Part 3 observability columns to run_steps."""
    part3_columns = [
        ("event_time", "TEXT"),
        ("latency_ms", "INTEGER"),
        ("tokens_prompt", "INTEGER"),
        ("tokens_completion", "INTEGER"),
        ("cost_microusd", "INTEGER"),
        ("error_code", "TEXT"),
    ]
    if is_postgres():
        conn.execute("ALTER TABLE run_steps ADD COLUMN IF NOT EXISTS tool_latency_ms INTEGER")
        for name, typ in part3_columns:
            if name == "latency_ms":
                conn.execute("ALTER TABLE run_steps ADD COLUMN IF NOT EXISTS latency_ms INTEGER")
            elif name == "event_time":
                conn.execute("ALTER TABLE run_steps ADD COLUMN IF NOT EXISTS event_time TEXT")
            elif name == "tokens_prompt":
                conn.execute("ALTER TABLE run_steps ADD COLUMN IF NOT EXISTS tokens_prompt INTEGER")
            elif name == "tokens_completion":
                conn.execute("ALTER TABLE run_steps ADD COLUMN IF NOT EXISTS tokens_completion INTEGER")
            elif name == "cost_microusd":
                conn.execute("ALTER TABLE run_steps ADD COLUMN IF NOT EXISTS cost_microusd INTEGER")
            elif name == "error_code":
                conn.execute("ALTER TABLE run_steps ADD COLUMN IF NOT EXISTS error_code TEXT")
        return
    try:
        cols = [row["name"] for row in conn.execute("PRAGMA table_info(run_steps)").fetchall()]
        if "tool_latency_ms" not in cols:
            conn.execute("ALTER TABLE run_steps ADD COLUMN tool_latency_ms INTEGER")
        for name, typ in part3_columns:
            if name not in cols:
                conn.execute(f"ALTER TABLE run_steps ADD COLUMN {name} {typ}")
    except Exception:
        pass


def _ensure_runs_columns(conn: Any) -> None:
    """Additive migration: add parent_run_id to runs for replay."""
    if is_postgres():
        conn.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS parent_run_id TEXT")
        return
    try:
        cols = [row["name"] for row in conn.execute("PRAGMA table_info(runs)").fetchall()]
        if "parent_run_id" not in cols:
            conn.execute("ALTER TABLE runs ADD COLUMN parent_run_id TEXT")
    except Exception:
        pass


def init_run_db() -> None:
    """
    Create runs and run_steps tables and indexes. Call at app startup or before first use.
    For Postgres, runs DDL only once per process to avoid deadlocks when concurrent
    requests re-run ALTER TABLE in different lock orders. SQLite always runs init
    (tests may use different db paths).
    """
    global _run_db_initialized
    if is_postgres() and _run_db_initialized:
        return
    if is_postgres():
        with _run_db_init_lock:
            if _run_db_initialized:
                return
            _do_init_run_db()
            _run_db_initialized = True
    else:
        _do_init_run_db()


def _do_init_run_db() -> None:
    """Actual DDL; called by init_run_db()."""
    _ensure_sqlite_dir()
    with connect() as conn:
        if not is_postgres():
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=3000")
        _ensure_runs_tables(conn)
        _ensure_run_steps_tables(conn)
        _ensure_runs_columns(conn)
        _ensure_run_steps_columns(conn)
        conn.commit()


def create_run(
    agent_id: str,
    agent_version: str,
    session_id: Optional[str],
    input_json: Dict[str, Any],
    parent_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new run; returns run dict with status=queued, step_count=0. Optional parent_run_id for replay."""
    init_run_db()
    run_id = str(uuid.uuid4())
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    input_text = json.dumps(input_json, sort_keys=True, default=str)
    with connect() as conn:
        conn.execute(
            sql(
                """
                INSERT INTO runs (
                    id, agent_id, agent_version, status, created_at, updated_at,
                    session_id, input_json, output_json, error, step_count, usage_json, parent_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
            ),
            (
                run_id,
                agent_id,
                agent_version,
                "queued",
                now,
                now,
                session_id,
                input_text,
                None,
                None,
                0,
                None,
                parent_run_id,
            ),
        )
        conn.commit()
    return {
        "id": run_id,
        "agent_id": agent_id,
        "agent_version": agent_version,
        "status": "queued",
        "created_at": now,
        "updated_at": now,
        "session_id": session_id,
        "input_json": input_json,
        "output_json": None,
        "error": None,
        "step_count": 0,
        "usage_json": None,
        "parent_run_id": parent_run_id,
    }


def set_run_status(
    run_id: str,
    status: str,
    output_json: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    usage_json: Optional[Dict[str, Any]] = None,
) -> None:
    """Update run status and optional output_json, error, usage_json."""
    init_run_db()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    output_text = json.dumps(output_json, sort_keys=True, default=str) if output_json is not None else None
    usage_text = json.dumps(usage_json, sort_keys=True, default=str) if usage_json is not None else None
    with connect() as conn:
        if output_json is not None or error is not None or usage_json is not None:
            conn.execute(
                sql(
                    """
                    UPDATE runs SET status = ?, updated_at = ?, output_json = ?, error = ?, usage_json = ?
                    WHERE id = ?
                    """
                ),
                (status, now, output_text, error, usage_text, run_id),
            )
        else:
            conn.execute(
                sql("UPDATE runs SET status = ?, updated_at = ? WHERE id = ?"),
                (status, now, run_id),
            )
        conn.commit()


def increment_run_step_count(run_id: str) -> None:
    """Increment step_count by 1 for the run."""
    init_run_db()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with connect() as conn:
        conn.execute(
            sql("UPDATE runs SET step_count = step_count + 1, updated_at = ? WHERE id = ?"),
            (now, run_id),
        )
        conn.commit()


def append_run_step(
    run_id: str,
    step_index: int,
    step_type: str,
    action_json: Dict[str, Any],
    tool_name: Optional[str] = None,
    tool_args_json: Optional[Dict[str, Any]] = None,
    tool_result_json: Optional[Dict[str, Any]] = None,
    model: Optional[str] = None,
    error: Optional[str] = None,
    tool_latency_ms: Optional[int] = None,
    event_time: Optional[str] = None,
    latency_ms: Optional[int] = None,
    tokens_prompt: Optional[int] = None,
    tokens_completion: Optional[int] = None,
    cost_microusd: Optional[int] = None,
    error_code: Optional[str] = None,
) -> None:
    """Append a step. Observability: tool_latency_ms/latency_ms, event_time, tokens_*, cost_microusd, error_code."""
    init_run_db()
    step_id = str(uuid.uuid4())
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    ts = event_time if event_time is not None else now
    action_text = json.dumps(action_json, sort_keys=True, default=str)
    tool_args_text = json.dumps(tool_args_json, sort_keys=True, default=str) if tool_args_json is not None else None
    tool_result_text = json.dumps(tool_result_json, sort_keys=True, default=str) if tool_result_json is not None else None
    with connect() as conn:
        conn.execute(
            sql(
                """
                INSERT INTO run_steps (
                    id, run_id, step_index, step_type, model, action_json,
                    tool_name, tool_args_json, tool_result_json, created_at, error, tool_latency_ms,
                    event_time, latency_ms, tokens_prompt, tokens_completion, cost_microusd, error_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
            ),
            (
                step_id,
                run_id,
                step_index,
                step_type,
                model,
                action_text,
                tool_name,
                tool_args_text,
                tool_result_text,
                now,
                error,
                tool_latency_ms,
                ts,
                latency_ms,
                tokens_prompt,
                tokens_completion,
                cost_microusd,
                error_code,
            ),
        )
        conn.commit()


def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    """Return run dict or None."""
    init_run_db()
    with connect() as conn:
        row = conn.execute(sql("SELECT * FROM runs WHERE id = ?"), (run_id,)).fetchone()
        if row is None:
            return None
        out: Dict[str, Any] = dict(row)
        if out.get("input_json"):
            try:
                out["input_json"] = json.loads(out["input_json"])
            except (json.JSONDecodeError, TypeError):
                pass
        if out.get("output_json"):
            try:
                out["output_json"] = json.loads(out["output_json"])
            except (json.JSONDecodeError, TypeError):
                pass
        if out.get("usage_json"):
            try:
                out["usage_json"] = json.loads(out["usage_json"])
            except (json.JSONDecodeError, TypeError):
                pass
        return out


def list_run_steps(run_id: str, after_step_index: Optional[int] = None) -> List[Dict[str, Any]]:
    """Return list of step dicts ordered by step_index. If after_step_index is set, only steps with step_index > after_step_index."""
    init_run_db()
    with connect() as conn:
        if after_step_index is not None:
            rows = conn.execute(
                sql("SELECT * FROM run_steps WHERE run_id = ? AND step_index > ? ORDER BY step_index"),
                (run_id, after_step_index),
            ).fetchall()
        else:
            rows = conn.execute(
                sql("SELECT * FROM run_steps WHERE run_id = ? ORDER BY step_index"),
                (run_id,),
            ).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            step = dict(r)
            if step.get("action_json"):
                try:
                    step["action_json"] = json.loads(step["action_json"])
                except (json.JSONDecodeError, TypeError):
                    pass
            if step.get("tool_args_json"):
                try:
                    step["tool_args_json"] = json.loads(step["tool_args_json"])
                except (json.JSONDecodeError, TypeError):
                    pass
            if step.get("tool_result_json"):
                try:
                    step["tool_result_json"] = json.loads(step["tool_result_json"])
                except (json.JSONDecodeError, TypeError):
                    pass
            out.append(step)
        return out
