from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from app.storage.db import connect, is_postgres, sql

from .models import CAPABILITY_CATEGORIES, ToolCandidate


def _ensure_sqlite_dir() -> None:
    if is_postgres():
        return
    from app.config import get_settings

    path = get_settings().db_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def init_tool_ingestion_db() -> None:
    """
    Create tool_candidates and platform_tools tables and indexes (best-effort).
    """
    _ensure_sqlite_dir()
    with connect() as conn:
        if not is_postgres():
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=3000")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tool_candidates (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                description TEXT,
                source_repo TEXT NOT NULL,
                source_path TEXT NOT NULL,
                tool_type TEXT NOT NULL,
                execution_kind TEXT NOT NULL,
                capability_category TEXT NOT NULL,
                args_schema_json TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                tags_json TEXT,
                confidence REAL NOT NULL,
                promotion_reason TEXT,
                raw_snippet TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tool_candidates_repo_name ON tool_candidates (source_repo, normalized_name)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tool_candidates_category ON tool_candidates (capability_category)"
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS platform_tools (
                tool_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                description TEXT,
                tool_type TEXT NOT NULL,
                execution_kind TEXT NOT NULL,
                capability_category TEXT NOT NULL,
                args_schema_json TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                tags_json TEXT,
                source_repo TEXT,
                source_path TEXT,
                confidence REAL NOT NULL,
                promotion_reason TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_platform_tools_normalized_name ON platform_tools (normalized_name)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_platform_tools_category ON platform_tools (capability_category)"
        )
        conn.commit()


def _validate_candidate_for_insert(c: ToolCandidate) -> ToolCandidate:
    c2 = c.with_computed_fields()
    if c2.capability_category not in CAPABILITY_CATEGORIES:
        c2 = c2.model_copy(update={"capability_category": "code_execution"}).with_computed_fields()
    return c2


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def insert_tool_candidates(candidates: Iterable[ToolCandidate]) -> int:
    init_tool_ingestion_db()
    rows: List[Tuple[Any, ...]] = []
    now = _now_iso()
    for c in candidates:
        c2 = _validate_candidate_for_insert(c)
        rows.append(
            (
                str(uuid.uuid4()),
                c2.name,
                c2.normalized_name,
                c2.description or "",
                c2.source_repo,
                c2.source_path,
                c2.tool_type,
                c2.execution_kind,
                c2.capability_category,
                json.dumps(c2.args_schema, sort_keys=True, default=str),
                c2.risk_level,
                json.dumps(c2.tags, sort_keys=True, default=str) if c2.tags else None,
                float(c2.confidence),
                c2.promotion_reason,
                c2.raw_snippet,
                now,
            )
        )

    if not rows:
        return 0

    with connect() as conn:
        cur = conn.cursor()
        cur.executemany(
            sql(
                """
                INSERT INTO tool_candidates (
                    id, name, normalized_name, description, source_repo, source_path,
                    tool_type, execution_kind, capability_category, args_schema_json,
                    risk_level, tags_json, confidence, promotion_reason, raw_snippet, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
            ),
            rows,
        )
        conn.commit()
    return len(rows)


def insert_platform_tools(candidates: Iterable[ToolCandidate]) -> int:
    """
    Insert promoted tool candidates into platform_tools.

    Deterministic tool_id:
      {normalized_name}__{execution_kind}__{capability_category}
    If conflict, keep existing (V1 behavior).
    """
    init_tool_ingestion_db()
    rows: List[Tuple[Any, ...]] = []
    now = _now_iso()
    for c in candidates:
        c2 = _validate_candidate_for_insert(c)
        tool_id = f"{c2.normalized_name}__{c2.execution_kind}__{c2.capability_category}"
        rows.append(
            (
                tool_id,
                c2.name,
                c2.normalized_name,
                c2.description or "",
                c2.tool_type,
                c2.execution_kind,
                c2.capability_category,
                json.dumps(c2.args_schema, sort_keys=True, default=str),
                c2.risk_level,
                json.dumps(c2.tags, sort_keys=True, default=str) if c2.tags else None,
                c2.source_repo,
                c2.source_path,
                float(c2.confidence),
                c2.promotion_reason,
                now,
            )
        )

    if not rows:
        return 0

    insert_sql = """
        INSERT INTO platform_tools (
            tool_id, name, normalized_name, description, tool_type, execution_kind,
            capability_category, args_schema_json, risk_level, tags_json,
            source_repo, source_path, confidence, promotion_reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    if is_postgres():
        insert_sql = insert_sql.strip() + " ON CONFLICT (tool_id) DO NOTHING"
    else:
        insert_sql = insert_sql.strip() + " ON CONFLICT(tool_id) DO NOTHING"

    with connect() as conn:
        cur = conn.cursor()
        cur.executemany(sql(insert_sql), rows)
        conn.commit()
    return len(rows)


def list_platform_tools() -> List[Dict[str, Any]]:
    """
    Return all promoted tools from platform_tools for catalog merge.
    Each row is a dict with tool_id, name, description, category, execution_kind,
    confidence, source_repo, source_path, promotion_reason.
    """
    init_tool_ingestion_db()
    with connect() as conn:
        cur = conn.execute(
            """
            SELECT tool_id, name, description, capability_category, execution_kind,
                   confidence, source_repo, source_path, promotion_reason
            FROM platform_tools
            ORDER BY tool_id
            """
        )
        rows = cur.fetchall()
    out: List[Dict[str, Any]] = []
    for r in rows:
        row = dict(r) if hasattr(r, "keys") else r
        tool_id = row.get("tool_id")
        if not tool_id:
            continue
        out.append({
            "tool_id": tool_id,
            "name": row.get("name") or tool_id,
            "description": row.get("description"),
            "category": row.get("capability_category") or "Other",
            "execution_kind": row.get("execution_kind") or "general",
            "confidence": row.get("confidence"),
            "source_repo": row.get("source_repo"),
            "source_path": row.get("source_path"),
            "promotion_reason": row.get("promotion_reason"),
        })
    return out

