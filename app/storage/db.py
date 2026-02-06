"""
Database helpers for SQLite (local) and Postgres (Supabase).
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from typing import Any, Optional

from app.config import get_settings

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - optional dependency for Postgres
    psycopg = None
    dict_row = None


@dataclass(frozen=True)
class DbInfo:
    dialect: str  # "sqlite" or "postgres"
    database_url: Optional[str]
    db_path: str


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DATABASE_URL")


def get_db_info() -> DbInfo:
    database_url = _database_url()
    db_path = get_settings().db_path
    if database_url:
        return DbInfo(dialect="postgres", database_url=database_url, db_path=db_path)
    return DbInfo(dialect="sqlite", database_url=None, db_path=db_path)


def is_postgres() -> bool:
    return get_db_info().dialect == "postgres"


def connect() -> Any:
    info = get_db_info()
    if info.dialect == "postgres":
        if psycopg is None:
            raise RuntimeError("psycopg is required for Postgres connections")
        return psycopg.connect(info.database_url, row_factory=dict_row)
    conn = sqlite3.connect(info.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def sql(query: str) -> str:
    """
    Convert parameter placeholders for the active dialect.
    SQLite uses '?', Postgres uses '%s'.
    """
    if is_postgres():
        return query.replace("?", "%s")
    return query
