"""
Session store: SQLite- or Postgres-backed sessions and events.

Sessions table: (id, agent_id, created_at)
Events table: (id, session_id, role, content, event_type, run_id, step_index, tool_name, idempotency_key, ts, meta)
One connection per request; DB_PATH from env (default ./data/gateway.db).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.storage.db import connect, is_postgres, sql

logger = logging.getLogger("agent-gateway")


def _infer_event_type(role: str, event_type: Optional[str]) -> str:
    if event_type:
        return event_type
    if role == "user":
        return "user"
    if role == "assistant":
        return "assistant"
    return "system"

def _ensure_sqlite_dir() -> None:
    if is_postgres():
        return
    from app.config import get_settings

    path = get_settings().db_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def init_db() -> None:
    """
    Create tables and set PRAGMAs.
    Call at app startup (lifespan or startup event).
    """
    _ensure_sqlite_dir()
    with connect() as conn:
        if not is_postgres():
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=3000")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    event_type TEXT,
                    run_id TEXT,
                    step_index INTEGER,
                    tool_name TEXT,
                    idempotency_key TEXT,
                    ts TEXT,
                    meta TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
                """
            )
        else:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id BIGSERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    event_type TEXT,
                    run_id TEXT,
                    step_index INTEGER,
                    tool_name TEXT,
                    idempotency_key TEXT,
                    ts TEXT,
                    meta TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_session_id ON events (session_id)")
        _ensure_sessions_columns(conn)
        _ensure_events_columns_and_indexes(conn)
        conn.commit()


def _ensure_events_columns_and_indexes(conn: Any) -> None:
    """Additive schema migrations for events table; safe to call repeatedly."""
    needed = [
        ("event_type", "TEXT"),
        ("run_id", "TEXT"),
        ("step_index", "INTEGER"),
        ("tool_name", "TEXT"),
        ("idempotency_key", "TEXT"),
    ]
    if is_postgres():
        for name, col_type in needed:
            conn.execute(sql(f"ALTER TABLE events ADD COLUMN IF NOT EXISTS {name} {col_type}"))
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_events_session_id_idem ON events (session_id, idempotency_key)"
        )
        return

    cols_rows = conn.execute("PRAGMA table_info(events)").fetchall()
    existing = {row["name"] for row in cols_rows}
    for name, col_type in needed:
        if name not in existing:
            conn.execute(f"ALTER TABLE events ADD COLUMN {name} {col_type}")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_events_session_id_idem ON events (session_id, idempotency_key)"
    )


def _ensure_sessions_columns(conn: Any) -> None:
    """Additive schema migrations for sessions table (running summary)."""
    if is_postgres():
        conn.execute(sql("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS running_summary TEXT DEFAULT ''"))
        conn.execute(sql("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS summary_updated_at TEXT"))
        conn.execute(sql("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS summary_message_count INTEGER DEFAULT 0"))
        return

    try:
        cols_rows = conn.execute("PRAGMA table_info(sessions)").fetchall()
        existing = {row["name"] for row in cols_rows}
        if "running_summary" not in existing:
            conn.execute("ALTER TABLE sessions ADD COLUMN running_summary TEXT DEFAULT ''")
        if "summary_updated_at" not in existing:
            conn.execute("ALTER TABLE sessions ADD COLUMN summary_updated_at TEXT")
        if "summary_message_count" not in existing:
            conn.execute("ALTER TABLE sessions ADD COLUMN summary_message_count INTEGER DEFAULT 0")
    except Exception:
        # Best-effort migration; do not break if PRAGMA not supported.
        return


def create_session(agent_id: str) -> str:
    """Create a new session; return session_id."""
    init_db()  # Idempotent; ensures tables exist when TestClient doesn't run lifespan before first request
    session_id = str(uuid.uuid4())
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with connect() as conn:
        conn.execute(
            sql("INSERT INTO sessions (id, agent_id, created_at) VALUES (?, ?, ?)"),
            (session_id, agent_id, created_at),
        )
        conn.commit()
    return session_id


def append_events_detailed(session_id: str, events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Append events to a session. Each event supports:
    { role, content, event_type?, run_id?, step_index?, tool_name?, idempotency_key?, ts?, meta? }.
    Returns detailed result with duplicate detection.
    """
    if not events:
        return {"appended": 0, "duplicated": False, "event_ids": []}
    init_db()  # Idempotent; ensures tables exist when TestClient doesn't run lifespan before first request
    with connect() as conn:
        cur = conn.execute(sql("SELECT id FROM sessions WHERE id = ?"), (session_id,))
        if cur.fetchone() is None:
            return {"appended": 0, "duplicated": False, "event_ids": []}
        appended = 0
        duplicated = False
        event_ids: List[int] = []
        for ev in events:
            role = ev.get("role", "user")
            content = ev.get("content", "")
            event_type = _infer_event_type(role, ev.get("event_type"))
            run_id = ev.get("run_id")
            step_index = ev.get("step_index")
            tool_name = ev.get("tool_name")
            idempotency_key = ev.get("idempotency_key")
            ts = ev.get("ts") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            meta = json.dumps(ev.get("meta")) if ev.get("meta") is not None else None
            insert_sql = sql(
                """
                INSERT INTO events (
                    session_id, role, content, event_type, run_id, step_index, tool_name, idempotency_key, ts, meta
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
            )
            conflict_sql = sql(
                "SELECT id FROM events WHERE session_id = ? AND idempotency_key = ? ORDER BY id LIMIT 1"
            )
            try:
                cur_insert = conn.execute(
                    insert_sql,
                    (
                        session_id,
                        role,
                        content,
                        event_type,
                        run_id,
                        step_index,
                        tool_name,
                        idempotency_key,
                        ts,
                        meta,
                    ),
                )
                inserted_id = cur_insert.lastrowid
                if inserted_id is None:
                    existing = conn.execute(
                        conflict_sql,
                        (session_id, idempotency_key),
                    ).fetchone()
                    if existing is not None:
                        inserted_id = existing["id"]
                if inserted_id is not None:
                    event_ids.append(int(inserted_id))
                else:
                    event_ids.append(-1)
            except Exception as exc:
                if idempotency_key is None:
                    raise
                err_text = str(exc).lower()
                if "unique" not in err_text and "duplicate key" not in err_text:
                    raise
                existing = conn.execute(
                    conflict_sql,
                    (session_id, idempotency_key),
                ).fetchone()
                duplicated = True
                if existing is not None:
                    event_ids.append(int(existing["id"]))
                else:
                    event_ids.append(-1)
                continue
            appended += 1
        conn.commit()
    return {"appended": appended, "duplicated": duplicated, "event_ids": event_ids}


def append_events(session_id: str, events: List[Dict[str, Any]]) -> int:
    """Backward-compatible append API; returns only appended count."""
    result = append_events_detailed(session_id, events)
    return int(result.get("appended", 0))


def get_session_events(session_id: str) -> List[Dict[str, Any]]:
    """Return all events for a session including event typing/linkage fields."""
    init_db()
    with connect() as conn:
        events_rows = conn.execute(
            sql(
                """
                SELECT id, session_id, role, content, event_type, run_id, step_index, tool_name, idempotency_key, ts, meta
                FROM events
                WHERE session_id = ?
                ORDER BY id
                """
            ),
            (session_id,),
        ).fetchall()
        out: List[Dict[str, Any]] = []
        for e in events_rows:
            meta = None
            if e["meta"]:
                try:
                    meta = json.loads(e["meta"])
                except (json.JSONDecodeError, TypeError):
                    pass
            role = e["role"]
            out.append(
                {
                    "id": e["id"],
                    "session_id": e["session_id"],
                    "role": role,
                    "content": e["content"],
                    "event_type": _infer_event_type(role, e["event_type"]),
                    "run_id": e["run_id"],
                    "step_index": e["step_index"],
                    "tool_name": e["tool_name"],
                    "idempotency_key": e["idempotency_key"],
                    "ts": e["ts"],
                    "meta": meta,
                }
            )
    return out


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Return session dict with session_id, agent_id, created_at, events, running_summary
    or None when session not found. Do not raise.
    """
    init_db()  # Idempotent; ensures tables exist when TestClient doesn't run lifespan before first request
    with connect() as conn:
        row = conn.execute(
            sql(
                "SELECT id, agent_id, created_at, running_summary, summary_updated_at, summary_message_count "
                "FROM sessions WHERE id = ?"
            ),
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        out: Dict[str, Any] = {
            "session_id": row["id"],
            "agent_id": row["agent_id"],
            "created_at": row["created_at"],
            "events": get_session_events(session_id),
            "running_summary": row.get("running_summary") if isinstance(row, dict) else row["running_summary"],
            "summary_updated_at": row.get("summary_updated_at") if isinstance(row, dict) else row["summary_updated_at"],
            "summary_message_count": row.get("summary_message_count")
            if isinstance(row, dict)
            else row["summary_message_count"],
        }
    return out


def get_session_summary(session_id: str) -> Dict[str, Any]:
    """
    Lightweight accessor for running_summary and counters.
    Returns {running_summary, summary_updated_at, summary_message_count} with safe defaults.
    """
    init_db()
    with connect() as conn:
        row = conn.execute(
            sql(
                "SELECT running_summary, summary_updated_at, summary_message_count "
                "FROM sessions WHERE id = ?"
            ),
            (session_id,),
        ).fetchone()
        if row is None:
            return {"running_summary": "", "summary_updated_at": None, "summary_message_count": 0}
        data = dict(row)
        return {
            "running_summary": data.get("running_summary") or "",
            "summary_updated_at": data.get("summary_updated_at"),
            "summary_message_count": int(data.get("summary_message_count") or 0),
        }


def update_session_summary(session_id: str, new_summary: str, summarized_count: int) -> None:
    """
    Persist running_summary and summary_message_count for a session.
    Safe no-op when session does not exist.
    """
    init_db()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with connect() as conn:
        conn.execute(
            sql(
                "UPDATE sessions "
                "SET running_summary = ?, summary_updated_at = ?, summary_message_count = ? "
                "WHERE id = ?"
            ),
            (new_summary, now, int(summarized_count), session_id),
        )
        conn.commit()
