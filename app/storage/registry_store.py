"""
Registry store: SQLite-backed agent registry.

Agents table: (id, version, name, description, primitive, supports_memory, owner_user_id, tags, spec_json, created_at)
One connection per request; DB_PATH from env (default ./data/gateway.db).
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml
from jsonschema import Draft7Validator, SchemaError

from app.config import get_settings
from app.preset_loader import _coerce_memory_policy

logger = logging.getLogger("agent-gateway")

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


def _db_path() -> str:
    return get_settings().db_path


def _connect() -> sqlite3.Connection:
    path = _db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_registry_db() -> None:
    """
    Create agents table and indexes. Call at app startup.
    """
    with _connect() as conn:
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
                PRIMARY KEY (id, version)
            )
            """
        )
        try:
            conn.execute("ALTER TABLE agents ADD COLUMN owner_user_id TEXT")
        except sqlite3.OperationalError:
            # Column already exists.
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
    supports_memory_int = 1 if normalized.get("supports_memory") else 0

    with _connect() as conn:
        existing = conn.execute(
            "SELECT 1 FROM agents WHERE id = ? AND version = ?",
            (normalized["id"], normalized["version"]),
        ).fetchone()
        if existing is not None:
            raise AgentVersionExists(f"Agent version already exists: {normalized['id']}@{normalized['version']}")
        conn.execute(
            """
            INSERT INTO agents (
                id, version, name, description, primitive,
                supports_memory, owner_user_id, tags, spec_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized["id"],
                normalized["version"],
                normalized["name"],
                normalized["description"],
                normalized["primitive"],
                supports_memory_int,
                owner_user_id,
                tags_json,
                json.dumps(normalized),
                created_at,
            ),
        )
        conn.commit()
    return normalized["id"], normalized["version"]


def list_agents(
    *,
    q: Optional[str] = None,
    primitive: Optional[str] = None,
    supports_memory: Optional[bool] = None,
    latest_only: bool = True,
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
        params.append(1 if supports_memory else 0)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    if latest_only:
        sql = f"""
            SELECT *
            FROM (
                SELECT a.*, ROW_NUMBER() OVER (
                    PARTITION BY a.id
                    ORDER BY a.created_at DESC, a.rowid DESC
                ) AS rn
                FROM agents a
                {where_sql}
            )
            WHERE rn = 1
            ORDER BY id
        """
    else:
        sql = f"""
            SELECT *
            FROM agents
            {where_sql}
            ORDER BY id, created_at DESC, rowid DESC
        """

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    agents: List[Dict[str, Any]] = []
    for row in rows:
        tags = None
        if row["tags"]:
            try:
                tags = json.loads(row["tags"])
            except Exception:
                tags = None
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
            }
        )
    return agents


def list_agents_by_owner(owner_user_id: str) -> List[Dict[str, Any]]:
    init_registry_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM agents
            WHERE owner_user_id = ?
            ORDER BY id, created_at DESC, rowid DESC
            """,
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
            }
        )
    return agents


def _get_row(agent_id: str, version: Optional[str]) -> Optional[sqlite3.Row]:
    init_registry_db()
    with _connect() as conn:
        if version:
            return conn.execute(
                "SELECT * FROM agents WHERE id = ? AND version = ?",
                (agent_id, version),
            ).fetchone()
        return conn.execute(
            "SELECT * FROM agents WHERE id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (agent_id,),
        ).fetchone()


def get_agent(agent_id: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
    row = _get_row(agent_id, version)
    if row is None:
        return None
    spec = json.loads(row["spec_json"])
    spec["created_at"] = row["created_at"]
    return spec


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
    with _connect() as conn:
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
