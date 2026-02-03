"""
Session store: SQLite-backed sessions and events.

Sessions table: (id, agent_id, created_at)
Events table: (id, session_id, role, content, ts, meta)
One connection per request; DB_PATH from env (default ./data/gateway.db).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import get_settings

logger = logging.getLogger("agent-gateway")


def _db_path() -> str:
    return get_settings().db_path


def _connect() -> sqlite3.Connection:
    path = _db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """
    Create tables and set PRAGMAs.
    Call at app startup (lifespan or startup event).
    """
    with _connect() as conn:
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
                ts TEXT,
                meta TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
            """
        )
        conn.commit()


def create_session(agent_id: str) -> str:
    """Create a new session; return session_id."""
    init_db()  # Idempotent; ensures tables exist when TestClient doesn't run lifespan before first request
    session_id = str(uuid.uuid4())
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with _connect() as conn:
        conn.execute(
            "INSERT INTO sessions (id, agent_id, created_at) VALUES (?, ?, ?)",
            (session_id, agent_id, created_at),
        )
        conn.commit()
    return session_id


def append_events(session_id: str, events: List[Dict[str, Any]]) -> int:
    """
    Append events to a session. Each event: { role, content, ts?, meta? }.
    Returns number of events appended.
    """
    if not events:
        return 0
    init_db()  # Idempotent; ensures tables exist when TestClient doesn't run lifespan before first request
    with _connect() as conn:
        cur = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        if cur.fetchone() is None:
            return 0
        appended = 0
        for ev in events:
            role = ev.get("role", "user")
            content = ev.get("content", "")
            ts = ev.get("ts") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            meta = json.dumps(ev.get("meta")) if ev.get("meta") is not None else None
            conn.execute(
                "INSERT INTO events (session_id, role, content, ts, meta) VALUES (?, ?, ?, ?, ?)",
                (session_id, role, content, ts, meta),
            )
            appended += 1
        conn.commit()
    return appended


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Return session dict with session_id, agent_id, created_at, events, running_summary
    or None when session not found. Do not raise.
    """
    init_db()  # Idempotent; ensures tables exist when TestClient doesn't run lifespan before first request
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, agent_id, created_at FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        out: Dict[str, Any] = {
            "session_id": row["id"],
            "agent_id": row["agent_id"],
            "created_at": row["created_at"],
            "events": [],
            "running_summary": "",
        }
        events_rows = conn.execute(
            "SELECT id, session_id, role, content, ts, meta FROM events WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        for e in events_rows:
            meta = None
            if e["meta"]:
                try:
                    meta = json.loads(e["meta"])
                except (json.JSONDecodeError, TypeError):
                    pass
            out["events"].append(
                {
                    "id": e["id"],
                    "session_id": e["session_id"],
                    "role": e["role"],
                    "content": e["content"],
                    "ts": e["ts"],
                    "meta": meta,
                }
            )
    return out
