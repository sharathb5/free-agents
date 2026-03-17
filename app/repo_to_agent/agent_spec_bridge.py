"""
Bridge between repo-to-agent draft agent specs and the Free-Agents registry.

Normalizes and validates AgentDraftOutput.draft_agent_spec into the shape
expected by the registry. No persistence or catalog resolution here; see TODOs
for where final persistence hooks should go.
"""

from __future__ import annotations

import re
from typing import Any, Dict

from jsonschema import Draft7Validator, SchemaError

from app.storage.registry_store import AgentSpecInvalid

# Align with registry_store constraints (no catalog dependency).
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")
_MAX_VERSION_LEN = 32
_MAX_PROMPT_CHARS = 20_000
_MAX_SCHEMA_DEPTH = 50


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


def _validate_schema_structure(schema: Any, *, field_name: str) -> Dict[str, Any]:
    """Validate schema is a Draft7 object root; same rules as registry_store."""
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
        raise AgentSpecInvalid(
            f"{field_name} is not a valid Draft7 JSON schema",
            details={"message": str(exc)},
        ) from exc
    return schema


def normalize_draft_agent_spec(draft_agent_spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a draft agent spec (e.g. from AgentDraftOutput) into registry-compatible shape.

    Fills defaults for missing required fields and coerces types. Does not run
    catalog resolution or persistence.

    TODO: When persisting, call registry_store.register_agent(normalized) after
    catalog resolution; resolution may add allowed_tools, tool_policies, etc.
    """
    if not isinstance(draft_agent_spec, dict):
        raise AgentSpecInvalid("draft_agent_spec must be an object")

    raw = dict(draft_agent_spec)
    agent_id = str(raw.get("id") or "draft-agent").strip().lower()
    agent_id = re.sub(r"[^a-z0-9_-]", "-", agent_id)[:63] or "draft-agent"
    if not _ID_RE.match(agent_id):
        agent_id = "draft-agent"

    version = str(raw.get("version") or "0.1.0").strip()[:_MAX_VERSION_LEN]
    name = str(raw.get("name") or agent_id).strip() or agent_id
    description = str(raw.get("description") or "").strip()
    primitive = str(raw.get("primitive") or "transform").strip()
    prompt = str(raw.get("prompt") or "You are an agent.").strip()

    input_schema = raw.get("input_schema")
    if not isinstance(input_schema, dict) or input_schema.get("type") != "object":
        input_schema = {"type": "object", "properties": {}, "additionalProperties": True}
    output_schema = raw.get("output_schema")
    if not isinstance(output_schema, dict) or output_schema.get("type") != "object":
        output_schema = {"type": "object", "properties": {}, "additionalProperties": True}

    normalized: Dict[str, Any] = {
        "id": agent_id,
        "version": version,
        "name": name,
        "description": description,
        "primitive": primitive,
        "prompt": prompt,
        "input_schema": input_schema,
        "output_schema": output_schema,
        "supports_memory": bool(raw.get("supports_memory", False)),
    }
    if raw.get("memory_policy") is not None and isinstance(raw["memory_policy"], dict):
        normalized["memory_policy"] = dict(raw["memory_policy"])
    if isinstance(raw.get("tags"), list):
        normalized["tags"] = [str(t) for t in raw["tags"] if t]
    if isinstance(raw.get("bundle_id"), str) and raw["bundle_id"].strip():
        normalized["bundle_id"] = raw["bundle_id"].strip()
    if isinstance(raw.get("additional_tools"), list):
        normalized["additional_tools"] = [str(t).strip() for t in raw["additional_tools"] if t]
    if isinstance(raw.get("http_allowed_domains"), list):
        normalized["http_allowed_domains"] = [str(d).strip() for d in raw["http_allowed_domains"] if d]
    return normalized


def validate_draft_agent_spec_for_registry(draft_agent_spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize and structurally validate a draft spec for registry compatibility.

    Returns the normalized spec dict. Raises AgentSpecInvalid if the spec
    fails structural checks (id format, version length, prompt length, schema validity).
    Does not perform catalog resolution or persistence.

    TODO: Final persistence should call registry_store.register_agent() which
    runs full _normalize_spec (including resolve_spec_tools). Use this helper
    for pre-submit validation only.
    """
    normalized = normalize_draft_agent_spec(draft_agent_spec)

    if not _ID_RE.match(normalized["id"]):
        raise AgentSpecInvalid("Agent id must match ^[a-z0-9][a-z0-9_-]{1,62}$")
    if len(normalized["version"]) > _MAX_VERSION_LEN:
        raise AgentSpecInvalid(f"Version too long (max {_MAX_VERSION_LEN} chars)")
    if len(normalized["prompt"]) > _MAX_PROMPT_CHARS:
        raise AgentSpecInvalid("Prompt too long")

    _validate_schema_structure(normalized["input_schema"], field_name="input_schema")
    _validate_schema_structure(normalized["output_schema"], field_name="output_schema")

    return normalized
