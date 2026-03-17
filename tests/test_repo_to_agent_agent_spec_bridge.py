"""
Tests for repo-to-agent agent spec bridge (normalize + validate for registry).
"""

from __future__ import annotations

import pytest

from app.repo_to_agent.agent_spec_bridge import (
    normalize_draft_agent_spec,
    validate_draft_agent_spec_for_registry,
)
from app.storage.registry_store import AgentSpecInvalid


def test_normalize_draft_agent_spec_fills_defaults() -> None:
    """Normalize fills missing required fields with defaults."""
    draft = {"id": "my-agent", "name": "My Agent"}
    out = normalize_draft_agent_spec(draft)
    assert out["id"] == "my-agent"
    assert out["version"] == "0.1.0"
    assert out["name"] == "My Agent"
    assert out["description"] == ""
    assert out["primitive"] == "transform"
    assert out["prompt"] == "You are an agent."
    assert out["input_schema"]["type"] == "object"
    assert out["output_schema"]["type"] == "object"
    assert out["supports_memory"] is False


def test_normalize_draft_agent_spec_preserves_valid_schema() -> None:
    """Normalize preserves valid input/output schemas."""
    draft = {
        "id": "x",
        "version": "1.0",
        "name": "X",
        "description": "d",
        "primitive": "transform",
        "prompt": "p",
        "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}},
        "output_schema": {"type": "object", "properties": {"result": {"type": "string"}}},
    }
    out = normalize_draft_agent_spec(draft)
    assert out["input_schema"]["properties"]["q"] == {"type": "string"}
    assert out["output_schema"]["properties"]["result"] == {"type": "string"}


def test_normalize_draft_agent_spec_coerces_id_to_valid_pattern() -> None:
    """Normalize coerces invalid id (e.g. too short) to draft-agent."""
    out = normalize_draft_agent_spec({"name": "Test", "id": "9"})  # id must be 2+ chars
    assert out["id"] == "draft-agent"


def test_validate_draft_agent_spec_for_registry_returns_normalized() -> None:
    """Validate returns normalized spec when structurally valid."""
    draft = {
        "id": "valid-agent",
        "version": "1.0.0",
        "name": "Valid",
        "description": "Desc",
        "primitive": "transform",
        "prompt": "Do things.",
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {}},
    }
    out = validate_draft_agent_spec_for_registry(draft)
    assert out["id"] == "valid-agent"
    assert out["name"] == "Valid"


def test_validate_draft_agent_spec_for_registry_normalizes_uppercase_id() -> None:
    """Validate normalizes id (e.g. lowercases) and returns valid spec."""
    draft = {
        "id": "UPPERCASE",
        "version": "1.0",
        "name": "N",
        "description": "",
        "primitive": "transform",
        "prompt": "p",
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {}},
    }
    out = validate_draft_agent_spec_for_registry(draft)
    assert out["id"] == "uppercase"


def test_validate_draft_agent_spec_for_registry_raises_on_prompt_too_long() -> None:
    """Validate raises when prompt exceeds max length."""
    draft = {
        "id": "x",
        "version": "1.0",
        "name": "N",
        "description": "",
        "primitive": "transform",
        "prompt": "x" * (20_001),
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {}},
    }
    with pytest.raises(AgentSpecInvalid, match="Prompt too long"):
        validate_draft_agent_spec_for_registry(draft)


def test_normalize_rejects_non_dict() -> None:
    """Normalize raises when draft_agent_spec is not a dict."""
    with pytest.raises(AgentSpecInvalid, match="must be an object"):
        normalize_draft_agent_spec([])
