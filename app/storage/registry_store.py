"""
Registry store: SQLite- or Postgres-backed agent registry.

Agents table: (id, version, name, description, primitive, supports_memory, owner_user_id, tags, spec_json, created_at, archived)
One connection per request; DB_PATH from env (default ./data/gateway.db).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml
from jsonschema import Draft7Validator, SchemaError

from app.catalog.resolution import ResolutionError, resolve_spec_tools
from app.models import StoredAgent
from app.preset_loader import _coerce_memory_policy
from app.storage.db import connect, is_postgres, sql

logger = logging.getLogger("agent-gateway")

_registry_version = 0
_registry_event = asyncio.Event()

_DEBUG_LOG_PATH = "/Users/sharath/agent-toolbox/agent-toolbox/.cursor/debug-db76a9.log"


def _debug_log(*, hypothesis_id: str, location: str, message: str, data: Dict[str, Any] | None = None, run_id: str = "pre-fix") -> None:
    # #region agent log
    try:
        payload: Dict[str, Any] = {
            "sessionId": "db76a9",
            "timestamp": int(time.time() * 1000),
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion agent log


def _touch_registry_version() -> None:
    global _registry_version
    _registry_version += 1
    _registry_event.set()


def get_registry_version() -> int:
    return _registry_version


async def wait_for_registry_change(last_seen: int, timeout: float = 15.0) -> int:
    """
    Wait for a registry change or timeout; returns the latest version.
    """
    if _registry_version != last_seen:
        return _registry_version
    try:
        await asyncio.wait_for(_registry_event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        return _registry_version
    finally:
        _registry_event.clear()
    return _registry_version

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")
_MAX_SPEC_BYTES = 300_000
_MAX_PROMPT_CHARS = 20_000
_MAX_SCHEMA_BYTES = 200_000
_MAX_SCHEMA_DEPTH = 50


class RegistryError(RuntimeError):
    """Base registry error."""


class AgentSpecInvalid(RegistryError):
    """Raised when an agent spec fails validation."""

    def __init__(self, message: str, details: Any = None):
        super().__init__(message)
        self.details = details


class AgentVersionExists(RegistryError):
    """Raised when attempting to register an existing (id, version)."""

    def __init__(self, message: str, *, agent_id: str, version: str):
        super().__init__(message)
        self.agent_id = agent_id
        self.version = version


def _ensure_sqlite_dir() -> None:
    if is_postgres():
        return
    from app.config import get_settings

    path = get_settings().db_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def init_registry_db() -> None:
    """
    Create agents table and indexes. Call at app startup.
    """
    _ensure_sqlite_dir()
    with connect() as conn:
        if not is_postgres():
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=3000")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    primitive TEXT NOT NULL,
                    supports_memory INTEGER NOT NULL,
                    owner_user_id TEXT,
                    tags TEXT,
                    spec_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (id, version)
                )
                """
            )
            try:
                conn.execute("ALTER TABLE agents ADD COLUMN owner_user_id TEXT")
            except Exception:
                # Column already exists.
                pass
            try:
                conn.execute("ALTER TABLE agents ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
            except Exception:
                # Column already exists.
                pass
        else:
            # Serialize schema migration across processes and reduce startup lock contention.
            # If another process is migrating, we prefer to start without re-running ALTERs when not needed.
            try:
                conn.execute("SELECT pg_advisory_lock(92734012)")
            except Exception:
                pass
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    primitive TEXT NOT NULL,
                    supports_memory BOOLEAN NOT NULL,
                    owner_user_id TEXT,
                    tags TEXT,
                    spec_json TEXT NOT NULL,
                    created_at BIGINT NOT NULL,
                    archived BOOLEAN NOT NULL DEFAULT FALSE,
                    PRIMARY KEY (id, version)
                )
                """
            )
            # Only attempt ALTER TABLE when columns are missing; avoids blocking DDL when schema is already up to date.
            try:
                row = conn.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'agents'
                    """
                ).fetchall()
                existing = {r["column_name"] for r in row if isinstance(r, dict) and isinstance(r.get("column_name"), str)}
            except Exception:
                existing = set()
            _debug_log(
                hypothesis_id="H6",
                location="app/storage/registry_store.py:init_registry_db",
                message="Postgres agents schema columns (pre-alter)",
                data={"columns_sample": sorted(list(existing))[:30], "count": len(existing)},
            )
            try:
                if "owner_user_id" not in existing:
                    conn.execute("ALTER TABLE agents ADD COLUMN owner_user_id TEXT")
                if "archived" not in existing:
                    conn.execute("ALTER TABLE agents ADD COLUMN archived BOOLEAN DEFAULT FALSE")
            except Exception as exc:
                # If another process is performing the migration and we time out waiting for locks,
                # log it and proceed so the app can start if schema is already migrated.
                _debug_log(
                    hypothesis_id="H6",
                    location="app/storage/registry_store.py:init_registry_db",
                    message="Postgres agents ALTER TABLE failed",
                    data={"error_type": type(exc).__name__, "error": str(exc)[:300]},
                )
                # Re-raise only if we couldn't confirm the columns exist.
                if "owner_user_id" not in existing or "archived" not in existing:
                    raise
            finally:
                try:
                    conn.execute("SELECT pg_advisory_unlock(92734012)")
                except Exception:
                    pass
        conn.execute("CREATE INDEX IF NOT EXISTS idx_agents_id ON agents (id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_agents_primitive ON agents (primitive)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_agents_owner ON agents (owner_user_id)")
        conn.commit()


def _json_size_bytes(value: Any) -> int:
    try:
        return len(json.dumps(value).encode("utf-8"))
    except Exception:
        return 0


def _max_depth(value: Any, *, _depth: int = 0) -> int:
    if isinstance(value, dict):
        if not value:
            return _depth
        return max(_max_depth(v, _depth=_depth + 1) for v in value.values())
    if isinstance(value, list):
        if not value:
            return _depth
        return max(_max_depth(v, _depth=_depth + 1) for v in value)
    return _depth


def _validate_schema(schema: Any, *, field_name: str) -> Dict[str, Any]:
    if not isinstance(schema, dict):
        raise AgentSpecInvalid(f"{field_name} must be a JSON object")
    if schema.get("type") != "object":
        raise AgentSpecInvalid(f"{field_name} root type must be 'object'")
    depth = _max_depth(schema)
    if depth > _MAX_SCHEMA_DEPTH:
        raise AgentSpecInvalid(f"{field_name} is too deep")
    try:
        Draft7Validator.check_schema(schema)
    except SchemaError as exc:
        raise AgentSpecInvalid(f"{field_name} is not a valid Draft7 JSON schema", details={"message": str(exc)}) from exc
    return schema


def _normalize_spec(raw_spec: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw_spec, dict):
        raise AgentSpecInvalid("Spec must be an object")

    if _json_size_bytes(raw_spec) > _MAX_SPEC_BYTES:
        raise AgentSpecInvalid("Spec is too large")

    try:
        agent_id = str(raw_spec["id"])
        version = str(raw_spec["version"])
        name = str(raw_spec["name"])
        description = str(raw_spec["description"])
        primitive = str(raw_spec["primitive"])
        prompt = str(raw_spec["prompt"])
    except KeyError as exc:
        raise AgentSpecInvalid(f"Spec missing required field: {exc.args[0]}") from exc

    if not _ID_RE.match(agent_id):
        raise AgentSpecInvalid("Agent id must match ^[a-z0-9][a-z0-9_-]{1,62}$")
    if len(version) > 32:
        raise AgentSpecInvalid("Version too long (max 32 chars)")
    if len(prompt) > _MAX_PROMPT_CHARS:
        raise AgentSpecInvalid("Prompt too long")

    input_schema = _validate_schema(raw_spec.get("input_schema"), field_name="input_schema")
    output_schema = _validate_schema(raw_spec.get("output_schema"), field_name="output_schema")
    if _json_size_bytes(input_schema) + _json_size_bytes(output_schema) > _MAX_SCHEMA_BYTES:
        raise AgentSpecInvalid("Combined schema size too large")

    supports_memory = bool(raw_spec.get("supports_memory", False))
    memory_policy_raw = raw_spec.get("memory_policy")
    memory_policy: Dict[str, Any] | None = None
    if memory_policy_raw is not None:
        if not isinstance(memory_policy_raw, dict):
            raise AgentSpecInvalid("memory_policy must be an object when provided")
        coerced = _coerce_memory_policy(memory_policy_raw)
        memory_policy = {
            "mode": coerced.mode,
            "max_messages": int(coerced.max_messages),
            "max_chars": int(coerced.max_chars),
        }

    tags = raw_spec.get("tags")
    if tags is not None and not isinstance(tags, list):
        raise AgentSpecInvalid("tags must be a list of strings when provided")
    tags_list = [str(t) for t in tags] if isinstance(tags, list) else None

    credits = raw_spec.get("credits")
    credits_obj: Dict[str, str] | None = None
    if credits is not None:
        if not isinstance(credits, dict):
            raise AgentSpecInvalid("credits must be an object with name/url")
        name = credits.get("name")
        url = credits.get("url")
        if name is None or not str(name).strip():
            raise AgentSpecInvalid("credits.name is required when credits is provided")
        credits_obj = {"name": str(name).strip()}
        if url is not None and str(url).strip():
            credits_obj["url"] = str(url).strip()

    normalized: Dict[str, Any] = {
        "id": agent_id,
        "version": version,
        "name": name,
        "description": description,
        "primitive": primitive,
        "input_schema": input_schema,
        "output_schema": output_schema,
        "prompt": prompt,
        "supports_memory": supports_memory,
    }
    if memory_policy is not None:
        normalized["memory_policy"] = memory_policy
    if tags_list is not None:
        normalized["tags"] = tags_list
    if credits_obj is not None:
        normalized["credits"] = credits_obj
    # Tool catalog resolution (Part 5): same path as POST /catalog/tools/resolve
    try:
        resolved, tools_catalog = resolve_spec_tools(raw_spec)
    except ResolutionError as e:
        raise AgentSpecInvalid(str(e)) from e
    normalized["allowed_tools"] = resolved["resolved_allowed_tools"]
    normalized["tool_policies"] = resolved["resolved_tool_policies"]
    normalized["resolved_execution_limits"] = resolved["resolved_execution_limits"]
    if resolved["resolved_bundle_id"] is not None:
        normalized["bundle_id"] = resolved["resolved_bundle_id"]
    raw_additional = raw_spec.get("additional_tools") or raw_spec.get("extra_tools")
    if isinstance(raw_additional, list):
        tool_ids = {t["tool_id"] for t in (tools_catalog.get("tools") or []) if isinstance(t, dict) and t.get("tool_id")}
        additional_normalized = [str(t).strip() for t in raw_additional if t and str(t).strip() in tool_ids]
        normalized["additional_tools"] = additional_normalized
    http_allowed_domains = raw_spec.get("http_allowed_domains")
    if http_allowed_domains is not None and isinstance(http_allowed_domains, list):
        normalized["http_allowed_domains"] = [str(d).strip() for d in http_allowed_domains if d]
    # Repo-to-agent provenance (optional)
    if raw_spec.get("repo_owner") is not None and str(raw_spec["repo_owner"]).strip():
        normalized["repo_owner"] = str(raw_spec["repo_owner"]).strip()
    if raw_spec.get("repo_name") is not None and str(raw_spec["repo_name"]).strip():
        normalized["repo_name"] = str(raw_spec["repo_name"]).strip()
    if raw_spec.get("eval_cases") is not None and isinstance(raw_spec["eval_cases"], list):
        normalized["eval_cases"] = list(raw_spec["eval_cases"])
    return normalized


def register_agent(spec: Dict[str, Any], *, owner_user_id: Optional[str] = None) -> Tuple[str, str]:
    """
    Validate and register an agent spec. Returns (id, version).
    Raises AgentSpecInvalid or AgentVersionExists.
    """
    init_registry_db()
    normalized = _normalize_spec(spec)
    created_at = time.time_ns()
    tags_json = json.dumps(normalized.get("tags")) if normalized.get("tags") is not None else None
    supports_memory_value = bool(normalized.get("supports_memory")) if is_postgres() else (
        1 if normalized.get("supports_memory") else 0
    )

    with connect() as conn:
        if owner_user_id:
            existing_owner_rows = conn.execute(
                sql("SELECT DISTINCT owner_user_id FROM agents WHERE id = ?"),
                (normalized["id"],),
            ).fetchall()
            existing_owner_ids = {
                row["owner_user_id"]
                for row in existing_owner_rows
                if row.get("owner_user_id")
            }
            if existing_owner_ids and owner_user_id not in existing_owner_ids:
                raise AgentNotOwner("Agent is owned by another user")
        existing = conn.execute(
            sql("SELECT 1 FROM agents WHERE id = ? AND version = ?"),
            (normalized["id"], normalized["version"]),
        ).fetchone()
        if existing is not None:
            raise AgentVersionExists(
                f"Agent version already exists: {normalized['id']}@{normalized['version']}",
                agent_id=normalized["id"],
                version=normalized["version"],
            )
        conn.execute(
            sql(
                """
            INSERT INTO agents (
                id, version, name, description, primitive,
                supports_memory, owner_user_id, tags, spec_json, created_at, archived
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            ),
            (
                normalized["id"],
                normalized["version"],
                normalized["name"],
                normalized["description"],
                normalized["primitive"],
                supports_memory_value,
                owner_user_id,
                tags_json,
                json.dumps(normalized),
                created_at,
                0 if not is_postgres() else False,
            ),
        )
        conn.commit()
    _touch_registry_version()
    return normalized["id"], normalized["version"]


def preview_register_agent(spec: Dict[str, Any], *, owner_user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Same validation as register_agent without inserting.

    Returns:
        would_register: True if register_agent would succeed (no row conflict, no owner mismatch).
        would_conflict: True if (id, version) already exists.
        owner_mismatch: True if id is owned by another user (when owner_user_id is set).
        normalized: { agent_id, version, name } after _normalize_spec.
        existing: row metadata when would_conflict (else None).
    """
    init_registry_db()
    normalized = _normalize_spec(spec)
    owner_mismatch = False
    existing_meta: Optional[Dict[str, Any]] = None
    would_conflict = False

    with connect() as conn:
        if owner_user_id:
            existing_owner_rows = conn.execute(
                sql("SELECT DISTINCT owner_user_id FROM agents WHERE id = ?"),
                (normalized["id"],),
            ).fetchall()
            existing_owner_ids = {
                row["owner_user_id"]
                for row in existing_owner_rows
                if row.get("owner_user_id")
            }
            if existing_owner_ids and owner_user_id not in existing_owner_ids:
                owner_mismatch = True

        row = conn.execute(
            sql("SELECT id, version, name, owner_user_id, created_at FROM agents WHERE id = ? AND version = ?"),
            (normalized["id"], normalized["version"]),
        ).fetchone()
        if row is not None:
            would_conflict = True
            existing_meta = {
                "agent_id": row["id"],
                "version": row["version"],
                "name": row["name"],
                "owner_user_id": row["owner_user_id"],
                "created_at": row["created_at"],
            }

    would_register = not would_conflict and not owner_mismatch
    return {
        "would_register": would_register,
        "would_conflict": would_conflict,
        "owner_mismatch": owner_mismatch,
        "normalized": {
            "agent_id": normalized["id"],
            "version": normalized["version"],
            "name": normalized["name"],
        },
        "existing": existing_meta,
    }


def list_agents(
    *,
    q: Optional[str] = None,
    primitive: Optional[str] = None,
    supports_memory: Optional[bool] = None,
    latest_only: bool = True,
    include_archived: bool = False,
) -> List[Dict[str, Any]]:
    init_registry_db()

    clauses: List[str] = []
    params: List[Any] = []

    if q:
        q_like = f"%{q.lower()}%"
        clauses.append("(LOWER(name) LIKE ? OR LOWER(description) LIKE ? OR LOWER(id) LIKE ?)")
        params.extend([q_like, q_like, q_like])
    if primitive:
        clauses.append("primitive = ?")
        params.append(primitive)
    if supports_memory is not None:
        clauses.append("supports_memory = ?")
        params.append(supports_memory if is_postgres() else (1 if supports_memory else 0))
    if not include_archived:
        clauses.append("archived = ?")
        params.append(False if is_postgres() else 0)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    if latest_only:
        order_by = "a.created_at DESC, a.rowid DESC" if not is_postgres() else "a.created_at DESC"
        query = f"""
            SELECT *
            FROM (
                SELECT a.*, ROW_NUMBER() OVER (
                    PARTITION BY a.id
                    ORDER BY {order_by}
                ) AS rn
                FROM agents a
                {where_sql}
            )
            WHERE rn = 1
            ORDER BY id
        """
    else:
        order_by = "id, created_at DESC, rowid DESC" if not is_postgres() else "id, created_at DESC"
        query = f"""
            SELECT *
            FROM agents
            {where_sql}
            ORDER BY {order_by}
        """

    with connect() as conn:
        rows = conn.execute(sql(query), params).fetchall()

    agents: List[Dict[str, Any]] = []
    for row in rows:
        tags = None
        if row["tags"]:
            try:
                tags = json.loads(row["tags"])
            except Exception:
                tags = None
        credits = None
        try:
            spec = json.loads(row["spec_json"]) if row["spec_json"] else {}
            if isinstance(spec, dict):
                credits_val = spec.get("credits")
                if isinstance(credits_val, dict) and credits_val.get("name"):
                    credits = {
                        "name": str(credits_val.get("name")).strip(),
                    }
                    url_val = credits_val.get("url")
                    if url_val:
                        credits["url"] = str(url_val).strip()
        except Exception:
            credits = None
        agents.append(
            {
                "id": row["id"],
                "version": row["version"],
                "name": row["name"],
                "description": row["description"],
                "primitive": row["primitive"],
                "supports_memory": bool(row["supports_memory"]),
                "tags": tags,
                "created_at": row["created_at"],
                "archived": bool(row["archived"]),
                "credits": credits,
            }
        )
    return agents


def list_agents_by_owner(owner_user_id: str, *, include_archived: bool = False) -> List[Dict[str, Any]]:
    init_registry_db()
    order_by = "id, created_at DESC, rowid DESC" if not is_postgres() else "id, created_at DESC"
    with connect() as conn:
        rows = conn.execute(
            sql(
                f"""
            SELECT *
            FROM agents
            WHERE owner_user_id = ?
            {"AND archived = 0" if not include_archived and not is_postgres() else ""}
            {"AND archived = FALSE" if not include_archived and is_postgres() else ""}
            ORDER BY {order_by}
            """
            ),
            (owner_user_id,),
        ).fetchall()

    agents: List[Dict[str, Any]] = []
    for row in rows:
        tags = None
        if row["tags"]:
            try:
                tags = json.loads(row["tags"])
            except Exception:
                tags = None
        credits = None
        try:
            spec = json.loads(row["spec_json"]) if row["spec_json"] else {}
            if isinstance(spec, dict):
                credits_val = spec.get("credits")
                if isinstance(credits_val, dict) and credits_val.get("name"):
                    credits = {
                        "name": str(credits_val.get("name")).strip(),
                    }
                    url_val = credits_val.get("url")
                    if url_val:
                        credits["url"] = str(url_val).strip()
        except Exception:
            credits = None
        agents.append(
            {
                "id": row["id"],
                "version": row["version"],
                "name": row["name"],
                "description": row["description"],
                "primitive": row["primitive"],
                "supports_memory": bool(row["supports_memory"]),
                "tags": tags,
                "created_at": row["created_at"],
                "archived": bool(row["archived"]),
                "credits": credits,
            }
        )
    return agents


class AgentNotFound(RegistryError):
    """Raised when agent id/version does not exist."""


class AgentNotOwner(RegistryError):
    """Raised when attempting to modify agent not owned by caller."""


def archive_agent(
    agent_id: str,
    *,
    version: Optional[str] = None,
    owner_user_id: Optional[str] = None,
) -> Tuple[str, Optional[str]]:
    init_registry_db()
    with connect() as conn:
        if owner_user_id:
            if version:
                res = conn.execute(
                    sql(
                        "UPDATE agents SET archived = ? WHERE id = ? AND version = ? AND owner_user_id = ?"
                    ),
                    (True if is_postgres() else 1, agent_id, version, owner_user_id),
                )
            else:
                res = conn.execute(
                    sql("UPDATE agents SET archived = ? WHERE id = ? AND owner_user_id = ?"),
                    (True if is_postgres() else 1, agent_id, owner_user_id),
                )
        else:
            if version:
                res = conn.execute(
                    sql("UPDATE agents SET archived = ? WHERE id = ? AND version = ?"),
                    (True if is_postgres() else 1, agent_id, version),
                )
            else:
                res = conn.execute(
                    sql("UPDATE agents SET archived = ? WHERE id = ?"),
                    (True if is_postgres() else 1, agent_id),
                )
        conn.commit()
        if res.rowcount == 0:
            # Either not found, or not owned by caller.
            if owner_user_id:
                raise AgentNotOwner("Agent not found or not owned by user")
            raise AgentNotFound(f"Agent not found: {agent_id}")
    _touch_registry_version()
    return agent_id, version


def unarchive_agent(
    agent_id: str,
    *,
    version: Optional[str] = None,
    owner_user_id: Optional[str] = None,
) -> Tuple[str, Optional[str]]:
    init_registry_db()
    with connect() as conn:
        if owner_user_id:
            if version:
                res = conn.execute(
                    sql(
                        "UPDATE agents SET archived = ? WHERE id = ? AND version = ? AND owner_user_id = ?"
                    ),
                    (False if is_postgres() else 0, agent_id, version, owner_user_id),
                )
            else:
                res = conn.execute(
                    sql("UPDATE agents SET archived = ? WHERE id = ? AND owner_user_id = ?"),
                    (False if is_postgres() else 0, agent_id, owner_user_id),
                )
        else:
            if version:
                res = conn.execute(
                    sql("UPDATE agents SET archived = ? WHERE id = ? AND version = ?"),
                    (False if is_postgres() else 0, agent_id, version),
                )
            else:
                res = conn.execute(
                    sql("UPDATE agents SET archived = ? WHERE id = ?"),
                    (False if is_postgres() else 0, agent_id),
                )
        conn.commit()
        if res.rowcount == 0:
            if owner_user_id:
                raise AgentNotOwner("Agent not found or not owned by user")
            raise AgentNotFound(f"Agent not found: {agent_id}")
    _touch_registry_version()
    return agent_id, version


def _get_row(agent_id: str, version: Optional[str]) -> Optional[Any]:
    init_registry_db()
    with connect() as conn:
        if version:
            return conn.execute(
                sql("SELECT * FROM agents WHERE id = ? AND version = ?"),
                (agent_id, version),
            ).fetchone()
        return conn.execute(
            sql(
                "SELECT * FROM agents WHERE id = ? ORDER BY created_at DESC"
                + (", rowid DESC" if not is_postgres() else "")
                + " LIMIT 1"
            ),
            (agent_id,),
        ).fetchone()


def get_agent(agent_id: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
    row = _get_row(agent_id, version)
    if row is None:
        return None
    spec = json.loads(row["spec_json"])
    spec["created_at"] = row["created_at"]
    spec["archived"] = bool(row["archived"])
    return spec


def spec_to_stored_agent(spec: Dict[str, Any], created_at: float = 0.0) -> StoredAgent:
    """Build a StoredAgent view from a spec dict and created_at (e.g. from get_agent)."""
    tools = list(spec.get("allowed_tools") or spec.get("additional_tools") or [])
    if isinstance(tools, list):
        tools = [str(t) for t in tools if t]
    else:
        tools = []
    eval_cases = spec.get("eval_cases")
    if not isinstance(eval_cases, list):
        eval_cases = []
    return StoredAgent(
        agent_id=str(spec.get("id", "")),
        name=str(spec.get("name", "")),
        description=str(spec.get("description", "")),
        bundle_id=spec.get("bundle_id") and str(spec["bundle_id"]).strip() or None,
        tools=tools,
        eval_cases=eval_cases,
        repo_owner=spec.get("repo_owner") and str(spec["repo_owner"]).strip() or None,
        repo_name=spec.get("repo_name") and str(spec["repo_name"]).strip() or None,
        created_at=float(created_at),
    )


def get_agent_as_stored(agent_id: str, version: Optional[str] = None) -> Optional[StoredAgent]:
    """Return the agent as a StoredAgent model, or None if not found."""
    raw = get_agent(agent_id, version)
    if raw is None:
        return None
    created_at = raw.get("created_at")
    if created_at is None:
        created_at = 0.0
    try:
        created_at = float(created_at)
    except (TypeError, ValueError):
        created_at = 0.0
    return spec_to_stored_agent(raw, created_at)


def get_agent_schema(agent_id: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
    row = _get_row(agent_id, version)
    if row is None:
        return None
    spec = json.loads(row["spec_json"])
    return {
        "agent": spec.get("id"),
        "version": spec.get("version"),
        "primitive": spec.get("primitive"),
        "input_schema": spec.get("input_schema"),
        "output_schema": spec.get("output_schema"),
    }


def count_agents() -> int:
    init_registry_db()
    with connect() as conn:
        row = conn.execute("SELECT COUNT(1) AS c FROM agents").fetchone()
        return int(row["c"]) if row and row["c"] is not None else 0


def seed_from_presets(presets_dir: Path) -> int:
    """
    Seed the registry from preset YAML files if agents table is empty.
    Returns number of seeded agents.
    """
    if count_agents() > 0:
        return 0
    if not presets_dir.exists():
        return 0

    seeded = 0
    for preset_path in presets_dir.glob("*.yaml"):
        if not preset_path.is_file():
            continue
        try:
            with preset_path.open("r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            if not isinstance(raw, dict):
                raise AgentSpecInvalid("Preset YAML must deserialize to a mapping")
            register_agent(raw)
            seeded += 1
        except AgentVersionExists:
            continue
        except AgentSpecInvalid as exc:
            logger.warning("Skipping preset %s: %s", preset_path.name, exc)
        except Exception as exc:
            logger.warning("Skipping preset %s: %s", preset_path.name, exc)
    return seeded
