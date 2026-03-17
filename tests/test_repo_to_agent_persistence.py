"""
Tests for repo-to-agent persistence handoff (prepare_repo_to_agent_persistence_payload,
persist_if_valid, persist_validated_agent) and registry storage of generated agents.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from app.repo_to_agent.models import RepoArchitectureOutput, RepoToAgentResult
from app.repo_to_agent.persistence import (
    persist_if_valid,
    persist_validated_agent,
    prepare_repo_to_agent_persistence_payload,
)


def test_prepare_payload_includes_repo_analysis_and_normalized_spec() -> None:
    """Payload contains repo_analysis and normalized_draft_agent_spec."""
    result = RepoToAgentResult(
        repo_summary="A Python API.",
        architecture=RepoArchitectureOutput(
            languages=["Python"],
            frameworks=["FastAPI"],
            services=[],
            entrypoints=[],
            integrations=[],
            key_paths=[],
        ),
        important_files=["README.md", "main.py"],
        recommended_bundle="repo_to_agent",
        recommended_additional_tools=["github_repo_read"],
        draft_agent_spec={
            "id": "my-draft",
            "name": "My Draft",
            "version": "0.1.0",
            "description": "Desc",
            "primitive": "transform",
            "prompt": "Do it.",
        },
        starter_eval_cases=[{"name": "case1", "input": {}}],
        review_notes=[],
    )

    payload = prepare_repo_to_agent_persistence_payload(result)

    assert "repo_analysis" in payload
    assert payload["repo_analysis"]["repo_summary"] == "A Python API."
    assert payload["repo_analysis"]["recommended_bundle"] == "repo_to_agent"
    assert payload["repo_analysis"]["important_files"] == ["README.md", "main.py"]

    assert "normalized_draft_agent_spec" in payload
    spec = payload["normalized_draft_agent_spec"]
    assert spec["id"] == "my-draft"
    assert spec["name"] == "My Draft"
    assert "input_schema" in spec
    assert "output_schema" in spec

    assert payload["starter_eval_cases"] == [{"name": "case1", "input": {}}]


@patch("app.repo_to_agent.persistence.normalize_draft_agent_spec")
def test_prepare_payload_handles_normalization_failure_gracefully(mock_normalize: object) -> None:
    """When normalization raises, payload falls back to raw draft_agent_spec."""
    mock_normalize.side_effect = ValueError("normalize failed")
    result = RepoToAgentResult(
        repo_summary="x",
        architecture=RepoArchitectureOutput(
            languages=[],
            frameworks=[],
            services=[],
            entrypoints=[],
            integrations=[],
            key_paths=[],
        ),
        important_files=[],
        recommended_bundle="repo_to_agent",
        recommended_additional_tools=[],
        draft_agent_spec={"id": "draft", "name": "Draft"},
        starter_eval_cases=[],
        review_notes=[],
    )

    payload = prepare_repo_to_agent_persistence_payload(result)

    assert payload["repo_analysis"]["repo_summary"] == "x"
    assert payload["normalized_draft_agent_spec"] == {"id": "draft", "name": "Draft"}
    assert payload["starter_eval_cases"] == []


def _valid_result_for_registry(agent_id: str) -> RepoToAgentResult:
    """Build a RepoToAgentResult that passes validation and registry normalization."""
    return RepoToAgentResult(
        repo_summary="A Python library.",
        architecture=RepoArchitectureOutput(
            languages=["Python"],
            frameworks=[],
            services=[],
            entrypoints=[],
            integrations=[],
            key_paths=["src/__init__.py"],
        ),
        important_files=["README.md"],
        recommended_bundle="no_tools_writer",
        recommended_additional_tools=[],
        draft_agent_spec={
            "id": agent_id,
            "name": "Test Agent",
            "description": "Helps with the repo.",
            "primitive": "transform",
            "prompt": "You are an agent.",
        },
        starter_eval_cases=[
            {"name": "eval1", "input": {"task": "Do X"}, "expected": "Should do X."}
        ],
        review_notes=[],
    )


def test_persist_if_valid_stores_agent_and_can_retrieve() -> None:
    """When validation passes, persist_if_valid stores the agent; get_agent returns it."""
    from app.storage.registry_store import get_agent, get_agent_as_stored, init_registry_db

    init_registry_db()
    agent_id = "repo_persist_" + uuid.uuid4().hex[:8]
    result = _valid_result_for_registry(agent_id)
    owner, repo = "test_owner", "test_repo"

    out = persist_if_valid(result, owner, repo)
    assert out is not None
    reg_id, version = out
    assert reg_id == agent_id
    assert isinstance(version, str) and len(version) > 0

    spec = get_agent(agent_id)
    assert spec is not None
    assert spec.get("repo_owner") == owner
    assert spec.get("repo_name") == repo
    assert spec.get("eval_cases") == result.starter_eval_cases
    assert spec.get("name") == "Test Agent"

    stored = get_agent_as_stored(agent_id)
    assert stored is not None
    assert stored.agent_id == agent_id
    assert stored.name == "Test Agent"
    assert stored.repo_owner == owner
    assert stored.repo_name == repo
    assert stored.eval_cases == result.starter_eval_cases
    assert stored.created_at > 0


def test_persist_if_valid_does_not_store_when_validation_fails() -> None:
    """When validation fails, persist_if_valid returns None and does not register."""
    from app.storage.registry_store import init_registry_db

    init_registry_db()
    # Result that fails validation: empty draft name
    result = _valid_result_for_registry("repo_persist_fail_" + uuid.uuid4().hex[:8])
    result = RepoToAgentResult(
        **{
            **result.model_dump(),
            "draft_agent_spec": {
                **result.draft_agent_spec,
                "name": "",
                "description": "Has desc but no name",
            },
        }
    )
    out = persist_if_valid(result, "o", "r")
    assert out is None


def test_stored_agent_retrieval_via_get_agent_as_stored() -> None:
    """get_agent_as_stored returns StoredAgent with agent_id, name, description, tools, eval_cases, repo_owner, repo_name, created_at."""
    from app.storage.registry_store import get_agent_as_stored, init_registry_db

    init_registry_db()
    agent_id = "repo_persist_stored_" + uuid.uuid4().hex[:8]
    result = _valid_result_for_registry(agent_id)
    persist_validated_agent(result, "my_org", "my_repo")

    stored = get_agent_as_stored(agent_id)
    assert stored is not None
    assert stored.agent_id == agent_id
    assert stored.name == "Test Agent"
    assert stored.description == "Helps with the repo."
    assert stored.bundle_id == "no_tools_writer"
    assert stored.repo_owner == "my_org"
    assert stored.repo_name == "my_repo"
    assert len(stored.eval_cases) == 1
    assert stored.eval_cases[0]["name"] == "eval1"
    assert stored.created_at > 0
