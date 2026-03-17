"""
Migrate SQLite data (sessions, events, agents) to Postgres (Supabase).

Usage:
  DATABASE_URL=postgres://... python scripts/migrate_sqlite_to_postgres.py \
    --sqlite-path ./data/gateway.db
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from typing import Iterable, List, Tuple

try:
    import psycopg
except Exception:  # pragma: no cover
    psycopg = None

from app.storage.session_store import init_db
from app.storage.registry_store import init_registry_db


def _require_psycopg() -> None:
    if psycopg is None:
        raise SystemExit("psycopg is required. Install with: pip install psycopg[binary]")


def _sqlite_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _pg_count(pg: "psycopg.Connection", table: str) -> int:
    row = pg.execute(f"SELECT COUNT(1) AS c FROM {table}").fetchone()
    return int(row[0]) if row else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate SQLite data to Postgres.")
    parser.add_argument(
        "--sqlite-path",
        default=os.getenv("DB_PATH", "./data/gateway.db"),
        help="Path to SQLite DB (default: ./data/gateway.db or DB_PATH)",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append into non-empty Postgres tables (unsafe; may create duplicates).",
    )
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL (or SUPABASE_DATABASE_URL) must be set.")
    _require_psycopg()

    sqlite_conn = sqlite3.connect(args.sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row

    os.environ["DATABASE_URL"] = database_url
    init_db()
    init_registry_db()

    with psycopg.connect(database_url) as pg:
        if not args.append:
            for table in ("sessions", "events", "agents"):
                if _pg_count(pg, table) > 0:
                    raise SystemExit(
                        f"Postgres table '{table}' is not empty. "
                        "Use --append to force, or clear tables first."
                    )

        if _sqlite_table_exists(sqlite_conn, "sessions"):
            sessions = sqlite_conn.execute(
                "SELECT id, agent_id, created_at FROM sessions ORDER BY id"
            ).fetchall()
            if sessions:
                pg.executemany(
                    """
                    INSERT INTO sessions (id, agent_id, created_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    [(r["id"], r["agent_id"], r["created_at"]) for r in sessions],
                )

        if _sqlite_table_exists(sqlite_conn, "events"):
            events = sqlite_conn.execute(
                "SELECT session_id, role, content, ts, meta FROM events ORDER BY id"
            ).fetchall()
            if events:
                pg.executemany(
                    """
                    INSERT INTO events (session_id, role, content, ts, meta)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    [(r["session_id"], r["role"], r["content"], r["ts"], r["meta"]) for r in events],
                )

        if _sqlite_table_exists(sqlite_conn, "agents"):
            agents = sqlite_conn.execute(
                """
                SELECT id, version, name, description, primitive,
                       supports_memory, owner_user_id, tags, spec_json, created_at
                FROM agents
                ORDER BY id, created_at
                """
            ).fetchall()
            if agents:
                pg.executemany(
                    """
                    INSERT INTO agents (
                        id, version, name, description, primitive,
                        supports_memory, owner_user_id, tags, spec_json, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id, version) DO NOTHING
                    """,
                    [
                        (
                            r["id"],
                            r["version"],
                            r["name"],
                            r["description"],
                            r["primitive"],
                            bool(r["supports_memory"]),
                            r["owner_user_id"],
                            r["tags"],
                            r["spec_json"],
                            r["created_at"],
                        )
                        for r in agents
                    ],
                )

        pg.commit()

    sqlite_conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    main()
