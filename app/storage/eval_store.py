"""
Eval store: SQLite- or Postgres-backed eval suites, runs, and case results (Part 6).

eval_suites: (id, agent_id, agent_version, name, description, created_at, updated_at, cases_json)
eval_runs: (id, eval_suite_id, agent_id, agent_version, status, created_at, updated_at, summary_json, error)
eval_case_results: (id, eval_run_id, case_index, status, score, expected_json, actual_json, matcher_type, message, run_id, created_at)

Uses same DB as run_store (db_path / DATABASE_URL).
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.storage.db import connect, is_postgres, sql


def _ensure_sqlite_dir() -> None:
    if is_postgres():
        return
    from app.config import get_settings

    path = get_settings().db_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def _ensure_eval_suites_table(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS eval_suites (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            agent_version TEXT,
            name TEXT NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            cases_json TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_eval_suites_agent_id ON eval_suites (agent_id)")


def _ensure_eval_runs_table(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS eval_runs (
            id TEXT PRIMARY KEY,
            eval_suite_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            agent_version TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            summary_json TEXT,
            error TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_eval_runs_eval_suite_id ON eval_runs (eval_suite_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_eval_runs_agent_id ON eval_runs (agent_id)")


def _ensure_eval_case_results_table(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS eval_case_results (
            id TEXT PRIMARY KEY,
            eval_run_id TEXT NOT NULL,
            case_index INTEGER NOT NULL,
            status TEXT NOT NULL,
            score REAL NOT NULL,
            expected_json TEXT,
            actual_json TEXT,
            matcher_type TEXT NOT NULL,
            message TEXT,
            run_id TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_eval_case_results_eval_run_id ON eval_case_results (eval_run_id)"
    )


def init_eval_db() -> None:
    """Create eval_suites, eval_runs, eval_case_results tables. Call at app startup."""
    _ensure_sqlite_dir()
    with connect() as conn:
        if not is_postgres():
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=3000")
        _ensure_eval_suites_table(conn)
        _ensure_eval_runs_table(conn)
        _ensure_eval_case_results_table(conn)
        conn.commit()


def create_eval_suite(
    agent_id: str,
    name: str,
    cases: List[Dict[str, Any]],
    *,
    agent_version: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new eval suite. Returns suite dict."""
    init_eval_db()
    suite_id = str(uuid.uuid4())
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    cases_text = json.dumps(cases, sort_keys=True, default=str)
    with connect() as conn:
        conn.execute(
            sql(
                """
                INSERT INTO eval_suites (
                    id, agent_id, agent_version, name, description, created_at, updated_at, cases_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """
            ),
            (suite_id, agent_id, agent_version, name, description, now, now, cases_text),
        )
        conn.commit()
    return {
        "id": suite_id,
        "agent_id": agent_id,
        "agent_version": agent_version,
        "name": name,
        "description": description,
        "created_at": now,
        "updated_at": now,
        "cases_json": cases,
    }


def get_eval_suite(eval_suite_id: str) -> Optional[Dict[str, Any]]:
    """Return eval suite dict or None."""
    init_eval_db()
    with connect() as conn:
        row = conn.execute(
            sql("SELECT * FROM eval_suites WHERE id = ?"),
            (eval_suite_id,),
        ).fetchone()
        if row is None:
            return None
        out: Dict[str, Any] = dict(row)
        if out.get("cases_json"):
            try:
                out["cases_json"] = json.loads(out["cases_json"])
            except (json.JSONDecodeError, TypeError):
                out["cases_json"] = []
        return out


def list_eval_suites(agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """List eval suites, optionally filtered by agent_id."""
    init_eval_db()
    with connect() as conn:
        if agent_id:
            rows = conn.execute(
                sql("SELECT * FROM eval_suites WHERE agent_id = ? ORDER BY created_at DESC"),
                (agent_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                sql("SELECT * FROM eval_suites ORDER BY created_at DESC")
            ).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            suite = dict(r)
            if suite.get("cases_json"):
                try:
                    suite["cases_json"] = json.loads(suite["cases_json"])
                except (json.JSONDecodeError, TypeError):
                    suite["cases_json"] = []
            out.append(suite)
        return out


def create_eval_run(
    eval_suite_id: str,
    agent_id: str,
    *,
    agent_version: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new eval run with status=queued. Returns run dict."""
    init_eval_db()
    run_id = str(uuid.uuid4())
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with connect() as conn:
        conn.execute(
            sql(
                """
                INSERT INTO eval_runs (
                    id, eval_suite_id, agent_id, agent_version, status, created_at, updated_at, summary_json, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
            ),
            (run_id, eval_suite_id, agent_id, agent_version, "queued", now, now, None, None),
        )
        conn.commit()
    return {
        "id": run_id,
        "eval_suite_id": eval_suite_id,
        "agent_id": agent_id,
        "agent_version": agent_version,
        "status": "queued",
        "created_at": now,
        "updated_at": now,
        "summary_json": None,
        "error": None,
    }


def set_eval_run_status(
    eval_run_id: str,
    status: str,
    *,
    summary_json: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    """Update eval run status and optional summary_json, error."""
    init_eval_db()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    summary_text = json.dumps(summary_json, sort_keys=True, default=str) if summary_json is not None else None
    with connect() as conn:
        if summary_json is not None or error is not None:
            conn.execute(
                sql(
                    """
                    UPDATE eval_runs SET status = ?, updated_at = ?, summary_json = ?, error = ?
                    WHERE id = ?
                    """
                ),
                (status, now, summary_text, error, eval_run_id),
            )
        else:
            conn.execute(
                sql("UPDATE eval_runs SET status = ?, updated_at = ? WHERE id = ?"),
                (status, now, eval_run_id),
            )
        conn.commit()


def append_eval_case_result(
    eval_run_id: str,
    case_index: int,
    status: str,
    score: float,
    matcher_type: str,
    *,
    expected_json: Optional[Any] = None,
    actual_json: Optional[Any] = None,
    message: Optional[str] = None,
    run_id: Optional[str] = None,
) -> None:
    """Append a case result to an eval run."""
    init_eval_db()
    result_id = str(uuid.uuid4())
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    expected_text = json.dumps(expected_json, sort_keys=True, default=str) if expected_json is not None else None
    actual_text = json.dumps(actual_json, sort_keys=True, default=str) if actual_json is not None else None
    with connect() as conn:
        conn.execute(
            sql(
                """
                INSERT INTO eval_case_results (
                    id, eval_run_id, case_index, status, score, expected_json, actual_json,
                    matcher_type, message, run_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
            ),
            (
                result_id,
                eval_run_id,
                case_index,
                status,
                score,
                expected_text,
                actual_text,
                matcher_type,
                message,
                run_id,
                now,
            ),
        )
        conn.commit()


def list_eval_case_results(eval_run_id: str) -> List[Dict[str, Any]]:
    """Return list of case result dicts for an eval run, ordered by case_index."""
    init_eval_db()
    with connect() as conn:
        rows = conn.execute(
            sql("SELECT * FROM eval_case_results WHERE eval_run_id = ? ORDER BY case_index"),
            (eval_run_id,),
        ).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            result = dict(r)
            if result.get("expected_json"):
                try:
                    result["expected_json"] = json.loads(result["expected_json"])
                except (json.JSONDecodeError, TypeError):
                    pass
            if result.get("actual_json"):
                try:
                    result["actual_json"] = json.loads(result["actual_json"])
                except (json.JSONDecodeError, TypeError):
                    pass
            out.append(result)
        return out


def get_eval_run(eval_run_id: str) -> Optional[Dict[str, Any]]:
    """Return eval run dict or None."""
    init_eval_db()
    with connect() as conn:
        row = conn.execute(
            sql("SELECT * FROM eval_runs WHERE id = ?"),
            (eval_run_id,),
        ).fetchone()
        if row is None:
            return None
        out: Dict[str, Any] = dict(row)
        if out.get("summary_json"):
            try:
                out["summary_json"] = json.loads(out["summary_json"])
            except (json.JSONDecodeError, TypeError):
                pass
        return out
