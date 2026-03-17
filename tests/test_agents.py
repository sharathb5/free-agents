"""
Agent Registry API tests.

Spec: docs/target-functionality-spec.md
- R1: GET /agents → 200, body { "agents": [ ... ] }; each summary has id, name, description, primitive, supports_memory.
- R2: GET /agents/{id} → 200 with full details; 404 for unknown id with error envelope (NOT_FOUND).
- R3: Same error-envelope and request_id pattern as session routes.

Acceptance T1–T5: list returns 200 + agents array; at least one agent with required fields;
GET by id returns 200 for valid id with full fields; 404 for unknown id; memory_policy shape.
"""

from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    """FastAPI app from runtime. TestClient ensures lifespan runs and DB init if needed."""
    from app.main import app as fastapi_app  # type: ignore
    return fastapi_app


@pytest.fixture
def client(app):
    return TestClient(app)


# --- R1 / T1: GET /agents returns 200, body has key "agents", value is array ---

def test_get_agents_returns_200_with_agents_list(client: TestClient) -> None:
    """
    T1: GET /agents returns status 200 and body has key "agents" with value an array.
    """
    resp = client.get("/agents")
    assert resp.status_code == 200, (
        f"GET /agents expected 200, got {resp.status_code}. "
        "Ensure GET /agents route is implemented."
    )
    data = resp.json()
    assert "agents" in data
    assert isinstance(data["agents"], list)


# --- R1 / T2: GET /agents returns at least one agent; each has id, name, description, primitive, supports_memory ---

def test_get_agents_returns_at_least_one_agent_with_required_fields(client: TestClient) -> None:
    """
    T2: Length of agents >= 1; each element has id, name, description, primitive, supports_memory.
    """
    resp = client.get("/agents")
    assert resp.status_code == 200
    data = resp.json()
    agents = data["agents"]
    assert len(agents) >= 1, "GET /agents must return at least one agent (presets in app/presets/)"
    for agent in agents:
        _assert_agent_summary_shape(agent)


def _assert_agent_summary_shape(obj: Dict[str, Any]) -> None:
    """Assert object has agent summary fields: id, name, description, primitive, supports_memory."""
    for key in ("id", "name", "description", "primitive", "supports_memory"):
        assert key in obj, f"Agent summary must include '{key}'"
    assert isinstance(obj["id"], str)
    assert isinstance(obj["name"], str)
    assert isinstance(obj["description"], str)
    assert isinstance(obj["primitive"], str)
    assert isinstance(obj["supports_memory"], bool)


# --- R2 / T3: GET /agents/{id} returns 200 for valid id with full details ---

def test_get_agents_id_returns_200_for_valid_id(client: TestClient) -> None:
    """
    T3: For a known preset id (e.g. summarizer), GET /agents/{id} returns 200 and body has
    id, version, name, description, primitive, input_schema, output_schema, supports_memory, memory_policy.
    """
    preset_id = "summarizer"  # exists in app/presets/summarizer.yaml
    resp = client.get(f"/agents/{preset_id}")
    assert resp.status_code == 200, (
        f"GET /agents/{{id}} expected 200 for known id '{preset_id}', got {resp.status_code}."
    )
    data = resp.json()
    for key in (
        "id",
        "version",
        "name",
        "description",
        "primitive",
        "input_schema",
        "output_schema",
        "supports_memory",
        "memory_policy",
    ):
        assert key in data, f"GET /agents/{{id}} response must include '{key}'"
    assert data["id"] == preset_id
    assert isinstance(data["input_schema"], dict)
    assert isinstance(data["output_schema"], dict)
    assert isinstance(data["supports_memory"], bool)


# --- R2 / T4: GET /agents/{id} returns 404 for unknown id with error envelope ---

def test_get_agents_id_returns_404_for_unknown_id(client: TestClient) -> None:
    """
    T4: For id that does not exist, status 404; body has error code (e.g. NOT_FOUND) and message; R3 request_id in meta.
    """
    resp = client.get("/agents/nonexistent-preset-123")
    assert resp.status_code == 404
    data = resp.json()
    assert "error" in data
    assert "meta" in data
    error = data["error"]
    meta = data["meta"]
    assert error.get("code") == "NOT_FOUND"
    assert "message" in error
    assert isinstance(meta.get("request_id"), str), "R3: error envelope must include meta.request_id"


# --- R2 / T5: GET /agents/{id} memory_policy shape ---

def test_get_agents_id_memory_policy_shape_when_preset_has_memory_policy(client: TestClient) -> None:
    """
    T5 (with memory_policy): When preset has memory_policy (e.g. summarizer), response includes
    memory_policy with mode, max_messages, max_chars.
    """
    preset_id = "summarizer"  # has memory_policy in YAML
    resp = client.get(f"/agents/{preset_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "memory_policy" in data
    policy = data["memory_policy"]
    assert policy is not None
    assert isinstance(policy, dict)
    for key in ("mode", "max_messages", "max_chars"):
        assert key in policy, f"memory_policy must include '{key}' when preset has memory_policy"


def test_get_agents_id_memory_policy_null_or_omitted_when_preset_has_none(client: TestClient) -> None:
    """
    T5 (without memory_policy): When preset does not set memory_policy (e.g. classifier),
    response has memory_policy as null or omitted.
    """
    preset_id = "classifier"  # no memory_policy in YAML
    resp = client.get(f"/agents/{preset_id}")
    assert resp.status_code == 200
    data = resp.json()
    # Spec: "when not set, memory_policy is null or omitted"
    if "memory_policy" in data:
        assert data["memory_policy"] is None
