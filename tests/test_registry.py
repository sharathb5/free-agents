"""
Model 1 — Agent Registry + Deploy (Register Spec) — Registry tests.

SOURCE OF TRUTH: docs/model1-agent-registry-deploy-progress.md (§2 T1–T10).

Contract summary (for these tests only):
- POST /agents/register accepts {"spec": <YAML string>} OR {"spec": <JSON object>}
  and returns 200 with { ok, agent_id, version, status } for valid specs.
- Duplicate (id, version) returns 409 with AGENT_VERSION_EXISTS envelope.
- GET /agents supports latest_only (default true), filters q / primitive / supports_memory.
- "Latest" means most recent created_at, NOT semver order.
- GET /agents/{id} (optionally ?version=) returns latest or exact version.
- GET /agents/{id}/schema matches stored schemas for that agent+version.
- Invalid specs (bad id, missing fields, invalid JSON Schema, oversize spec, too-deep schema)
  return 400 with error.code == AGENT_SPEC_INVALID.

These tests intentionally do NOT implement backend logic; they define the
expected external behaviour so the backend agent can implement to pass them.
"""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    """FastAPI app from the runtime."""
    from app.main import app as fastapi_app  # type: ignore

    return fastapi_app


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


@pytest.fixture
def gateway_db_path() -> str:
    """
    Temporary DB path for registry + sessions (DB_PATH, SESSION_DB_PATH).

    Each test gets its own file; backend is expected to use DB_PATH for
    the unified gateway database.
    """
    with tempfile.TemporaryDirectory(prefix="gateway_registry_") as tmp:
        yield str(Path(tmp) / "gateway.db")


@contextmanager
def env_vars(env: Dict[str, str]):
    """
    Temporarily set environment variables for a test.

    Restores previous values afterwards, even if the test fails.
    """
    old_values: Dict[str, Any] = {}
    for key, value in env.items():
        old_values[key] = os.environ.get(key)
        os.environ[key] = value
    try:
        yield
    finally:
        for key, old in old_values.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def _assert_error_envelope(resp_json: Dict[str, Any], expected_code: str):
    """Assert standard error envelope and code as per build_error_envelope."""
    assert "error" in resp_json, "Error responses must include 'error' envelope"
    assert "meta" in resp_json, "Error responses must include 'meta' envelope"

    error = resp_json["error"]
    meta = resp_json["meta"]

    assert error.get("code") == expected_code
    assert "message" in error
    # Minimal meta contract: request_id present.
    assert isinstance(meta.get("request_id"), str)


def _make_valid_spec(
    agent_id: str,
    version: str,
    *,
    primitive: str = "transform",
    supports_memory: bool = True,
) -> Dict[str, Any]:
    """
    Construct a minimal valid agent spec JSON object for registration tests.

    Shape follows existing Preset/Preset-like config:
    - id, version, name, description, primitive
    - input_schema, output_schema (Draft7-valid, root type=object)
    - prompt (short)
    - supports_memory, memory_policy when supports_memory is True
    """
    spec: Dict[str, Any] = {
        "id": agent_id,
        "version": version,
        "name": f"{agent_id} name",
        "description": f"{agent_id} description",
        "primitive": primitive,
        "input_schema": {
            "type": "object",
            "required": ["text"],
            "properties": {
                "text": {"type": "string", "title": "Text input"},
            },
        },
        "output_schema": {
            "type": "object",
            "required": ["summary"],
            "properties": {
                "summary": {"type": "string", "title": "Summary text"},
            },
        },
        "prompt": "You are a helpful test agent.",
        "supports_memory": supports_memory,
    }
    if supports_memory:
        spec["memory_policy"] = {
            "mode": "last_n",
            "max_messages": 2,
            "max_chars": 8000,
        }
    return spec


def _register_spec_json(
    client: TestClient,
    *,
    spec: Dict[str, Any],
    gateway_db_path: str,
    auth_token: str = "",
) -> Dict[str, Any]:
    """
    Helper to POST /agents/register with a JSON-object spec.
    Returns parsed JSON body.
    """
    env = {
        "DB_PATH": gateway_db_path,
        # Keep compatibility with any legacy SESSION_DB_PATH usage.
        "SESSION_DB_PATH": gateway_db_path,
        "AUTH_TOKEN": auth_token,
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
    }
    with env_vars(env):
        resp = client.post("/agents/register", json={"spec": spec})
    return {"status_code": resp.status_code, "body": resp.json()}


def _register_spec_yaml(
    client: TestClient,
    *,
    yaml_spec: str,
    gateway_db_path: str,
    auth_token: str = "",
) -> Dict[str, Any]:
    """
    Helper to POST /agents/register with a YAML-string spec.
    """
    env = {
        "DB_PATH": gateway_db_path,
        "SESSION_DB_PATH": gateway_db_path,
        "AUTH_TOKEN": auth_token,
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
    }
    with env_vars(env):
        resp = client.post("/agents/register", json={"spec": yaml_spec})
    return {"status_code": resp.status_code, "body": resp.json()}


# --- T1: Register valid agent spec as YAML string ------------------------------


def test_register_valid_yaml_spec_returns_200(client: TestClient, gateway_db_path: str) -> None:
    """
    T1: Register valid agent spec as YAML string.

    Expect:
    - 200 OK
    - body { ok: true, agent_id, version, status }
    """
    spec = _make_valid_spec("yaml-agent", "1.0.0")
    # YAML-encode minimal spec; backend will parse via yaml.safe_load.
    import yaml

    yaml_spec = yaml.safe_dump(spec)
    result = _register_spec_yaml(client, yaml_spec=yaml_spec, gateway_db_path=gateway_db_path)

    assert result["status_code"] == 200
    body = result["body"]
    assert body.get("ok") is True
    assert body.get("agent_id") == "yaml-agent"
    assert body.get("version") == "1.0.0"
    assert "status" in body  # exact string left to backend (e.g. "registered")


# --- T2: Register valid agent spec as JSON object ------------------------------


def test_register_valid_json_spec_returns_200(client: TestClient, gateway_db_path: str) -> None:
    """
    T2: Register valid agent spec as JSON object.
    """
    spec = _make_valid_spec("json-agent", "1.0.0")
    result = _register_spec_json(client, spec=spec, gateway_db_path=gateway_db_path)

    assert result["status_code"] == 200
    body = result["body"]
    assert body.get("ok") is True
    assert body.get("agent_id") == "json-agent"
    assert body.get("version") == "1.0.0"


# --- T3: Duplicate (id, version) -> 409 AGENT_VERSION_EXISTS -------------------


def test_register_duplicate_id_version_returns_409_agent_version_exists(
    client: TestClient, gateway_db_path: str
) -> None:
    """
    T3: Re-register same (id, version) -> 409 AGENT_VERSION_EXISTS envelope.
    """
    spec = _make_valid_spec("dup-agent", "1.0.0")
    first = _register_spec_json(client, spec=spec, gateway_db_path=gateway_db_path)
    assert first["status_code"] == 200

    second = _register_spec_json(client, spec=spec, gateway_db_path=gateway_db_path)
    assert second["status_code"] == 409
    _assert_error_envelope(second["body"], expected_code="AGENT_VERSION_EXISTS")


# --- T4: List agents default latest_only=true ----------------------------------


def test_get_agents_default_latest_only_returns_one_version_per_id(
    client: TestClient, gateway_db_path: str
) -> None:
    """
    T4: List agents default latest_only=true returns one version per id.
    """
    base_id = "multi-ver-agent"
    # Register two versions for the same id.
    _ = _register_spec_json(
        client, spec=_make_valid_spec(base_id, "1.0.0"), gateway_db_path=gateway_db_path
    )
    _ = _register_spec_json(
        client, spec=_make_valid_spec(base_id, "2.0.0"), gateway_db_path=gateway_db_path
    )

    env = {
        "DB_PATH": gateway_db_path,
        "SESSION_DB_PATH": gateway_db_path,
        "AUTH_TOKEN": "",
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
    }
    with env_vars(env):
        resp = client.get("/agents")  # latest_only defaults to true per spec
    assert resp.status_code == 200
    agents = resp.json()["agents"]
    versions_for_id = [a["version"] for a in agents if a["id"] == base_id]
    assert len(versions_for_id) == 1, "latest_only=true must only expose one version per id"


# --- T5: “Latest” is by created_at, not semver ---------------------------------


def test_latest_is_by_created_at_not_semver(client: TestClient, gateway_db_path: str) -> None:
    """
    T5: Register v1 then v0.9 later; latest should be v0.9 (most recent registration),
    not by semver comparison.
    """
    base_id = "semver-agent"
    # First register v1.0.0
    _register_spec_json(
        client, spec=_make_valid_spec(base_id, "1.0.0"), gateway_db_path=gateway_db_path
    )
    # Then register v0.9.0 (created_at is later)
    _register_spec_json(
        client, spec=_make_valid_spec(base_id, "0.9.0"), gateway_db_path=gateway_db_path
    )

    env = {
        "DB_PATH": gateway_db_path,
        "SESSION_DB_PATH": gateway_db_path,
        "AUTH_TOKEN": "",
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
    }
    with env_vars(env):
        resp = client.get("/agents", params={"latest_only": "true"})
    assert resp.status_code == 200
    agents = resp.json()["agents"]
    latest = next(a for a in agents if a["id"] == base_id)
    assert latest["version"] == "0.9.0"


# --- T6: Filters: q / primitive / supports_memory ------------------------------


def test_get_agents_filters_q_primitive_supports_memory(
    client: TestClient, gateway_db_path: str
) -> None:
    """
    T6: Filters q / primitive / supports_memory.

    We register three agents with distinct descriptions and primitives, then
    assert each filter returns the expected subset.
    """
    a1 = _make_valid_spec("alpha", "1.0.0", primitive="transform", supports_memory=True)
    a1["description"] = "alpha description foo"
    a2 = _make_valid_spec("beta", "1.0.0", primitive="classify", supports_memory=False)
    a2["description"] = "beta description bar"
    a3 = _make_valid_spec("gamma", "1.0.0", primitive="extract", supports_memory=True)
    a3["description"] = "gamma baz description"

    for spec in (a1, a2, a3):
        _register_spec_json(client, spec=spec, gateway_db_path=gateway_db_path)

    base_env = {
        "DB_PATH": gateway_db_path,
        "SESSION_DB_PATH": gateway_db_path,
        "AUTH_TOKEN": "",
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
    }

    # q filter: match on description substring "foo"
    with env_vars(base_env):
        resp_q = client.get("/agents", params={"q": "foo"})
    assert resp_q.status_code == 200
    ids_q = {a["id"] for a in resp_q.json()["agents"]}
    assert "alpha" in ids_q
    assert "beta" not in ids_q and "gamma" not in ids_q

    # primitive filter: only classify
    with env_vars(base_env):
        resp_p = client.get("/agents", params={"primitive": "classify"})
    assert resp_p.status_code == 200
    agents_p = resp_p.json()["agents"]
    assert {a["id"] for a in agents_p} == {"beta"}
    assert all(a["primitive"] == "classify" for a in agents_p)

    # supports_memory filter: true
    with env_vars(base_env):
        resp_m = client.get("/agents", params={"supports_memory": "true"})
    assert resp_m.status_code == 200
    agents_m = resp_m.json()["agents"]
    ids_m = {a["id"] for a in agents_m}
    assert "alpha" in ids_m and "gamma" in ids_m
    assert "beta" not in ids_m
    assert all(a["supports_memory"] is True for a in agents_m)


# --- T7: GET /agents/{id} returns latest ---------------------------------------


def test_get_agent_by_id_returns_latest_version(client: TestClient, gateway_db_path: str) -> None:
    """
    T7: GET /agents/{id} without version returns latest by created_at.
    """
    base_id = "by-id-agent"
    _register_spec_json(
        client, spec=_make_valid_spec(base_id, "1.0.0"), gateway_db_path=gateway_db_path
    )
    _register_spec_json(
        client, spec=_make_valid_spec(base_id, "0.9.0"), gateway_db_path=gateway_db_path
    )

    env = {
        "DB_PATH": gateway_db_path,
        "SESSION_DB_PATH": gateway_db_path,
        "AUTH_TOKEN": "",
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
    }
    with env_vars(env):
        resp = client.get(f"/agents/{base_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == base_id
    assert data["version"] == "0.9.0"


# --- T8: GET /agents/{id}?version= returns exact -------------------------------


def test_get_agent_by_id_and_version_returns_exact_version(
    client: TestClient, gateway_db_path: str
) -> None:
    """
    T8: GET /agents/{id}?version= returns the exact requested version, not latest.
    """
    base_id = "by-id-version-agent"
    _register_spec_json(
        client, spec=_make_valid_spec(base_id, "1.0.0"), gateway_db_path=gateway_db_path
    )
    _register_spec_json(
        client, spec=_make_valid_spec(base_id, "0.9.0"), gateway_db_path=gateway_db_path
    )

    env = {
        "DB_PATH": gateway_db_path,
        "SESSION_DB_PATH": gateway_db_path,
        "AUTH_TOKEN": "",
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
    }
    with env_vars(env):
        resp = client.get(f"/agents/{base_id}", params={"version": "1.0.0"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == base_id
    assert data["version"] == "1.0.0"


# --- T9: GET /agents/{id}/schema matches stored schemas ------------------------


def test_get_agent_schema_matches_stored_spec_schemas(
    client: TestClient, gateway_db_path: str
) -> None:
    """
    T9: GET /agents/{id}/schema must return { agent, version, primitive, input_schema, output_schema }
    matching the stored spec for that agent+version.
    """
    base_id = "schema-agent"
    spec = _make_valid_spec(base_id, "1.0.0", primitive="transform")
    _register_spec_json(client, spec=spec, gateway_db_path=gateway_db_path)

    env = {
        "DB_PATH": gateway_db_path,
        "SESSION_DB_PATH": gateway_db_path,
        "AUTH_TOKEN": "",
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
    }
    with env_vars(env):
        resp = client.get(f"/agents/{base_id}/schema")
    assert resp.status_code == 200
    data = resp.json()
    for key in ("agent", "version", "primitive", "input_schema", "output_schema"):
        assert key in data
    assert data["agent"] == base_id
    assert data["version"] == "1.0.0"
    assert data["primitive"] == spec["primitive"]
    assert data["input_schema"] == spec["input_schema"]
    assert data["output_schema"] == spec["output_schema"]


# --- T10: Spec validation failures -> 400 AGENT_SPEC_INVALID -------------------


@pytest.mark.parametrize("case, spec_modifier", [
    ("bad_id", lambda s: s.update({"id": "Bad Id With Spaces"}) or s),
    ("missing_required_field", lambda s: (s.pop("prompt", None)) or s),
    ("invalid_schema", lambda s: s["input_schema"].update({"type": "not-a-valid-type"}) or s),
    ("oversize_spec", lambda s: s.update({"prompt": "x" * 400_000}) or s),
    (
        "too_deep_schema",
        lambda s: _make_too_deep_schema(s),
    ),
])
def test_register_invalid_spec_returns_400_agent_spec_invalid(
    client: TestClient,
    gateway_db_path: str,
    case: str,
    spec_modifier,
) -> None:
    """
    T10: Invalid specs (bad id, missing fields, invalid Draft7 schema, oversize spec,
    too-deep schema) must all result in 400 AGENT_SPEC_INVALID.
    """
    base = _make_valid_spec("invalid-agent", "1.0.0")
    spec = json.loads(json.dumps(base))  # deep copy via JSON roundtrip
    spec = spec_modifier(spec)

    result = _register_spec_json(client, spec=spec, gateway_db_path=gateway_db_path)
    assert result["status_code"] == 400, f"case={case}"
    _assert_error_envelope(result["body"], expected_code="AGENT_SPEC_INVALID")


def _make_too_deep_schema(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mutate spec to have an excessively deep input_schema.

    Backend is expected to reject schemas that exceed a reasonable depth bound.
    """
    depth = 60
    schema: Dict[str, Any] = {"type": "object", "properties": {}}
    current = schema
    for i in range(depth):
        nested: Dict[str, Any] = {"type": "object", "properties": {}}
        current["properties"][f"level_{i}"] = nested
        current = nested
    spec["input_schema"] = schema
    return spec
