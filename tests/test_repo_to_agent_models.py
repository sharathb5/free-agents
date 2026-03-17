from __future__ import annotations

from typing import Any, Dict

import pytest
from pydantic import ValidationError

from app.repo_to_agent import (
    AgentDraftOutput,
    AgentReviewOutput,
    RepoArchitectureOutput,
    RepoScoutOutput,
    RepoToAgentResult,
)


def test_repo_scout_output_construction_and_defaults() -> None:
    model = RepoScoutOutput(
        repo_summary="A concise summary of the repo.",
        important_files=["README.md", "src/main.py"],
        language_hints=["Python"],
        framework_hints=["FastAPI"],
    )

    assert model.repo_summary == "A concise summary of the repo."
    assert model.important_files == ["README.md", "src/main.py"]
    assert model.language_hints == ["Python"]
    assert model.framework_hints == ["FastAPI"]

    dumped = model.model_dump()
    assert dumped["repo_summary"] == "A concise summary of the repo."
    assert "important_files" in dumped and isinstance(dumped["important_files"], list)


def test_repo_architecture_output_construction_and_defaults() -> None:
    model = RepoArchitectureOutput(
        languages=["Python"],
        frameworks=["FastAPI"],
        services=["api"],
        entrypoints=["src/main.py"],
        integrations=["postgres"],
        key_paths=["src/app"],
    )

    assert model.languages == ["Python"]
    assert model.frameworks == ["FastAPI"]
    assert model.services == ["api"]
    assert model.entrypoints == ["src/main.py"]
    assert model.integrations == ["postgres"]
    assert model.key_paths == ["src/app"]

    dumped = model.model_dump()
    assert dumped["languages"] == ["Python"]
    assert dumped["entrypoints"] == ["src/main.py"]


def test_agent_draft_output_construction_and_defaults() -> None:
    model = AgentDraftOutput(
        recommended_bundle="repo_to_agent",
        recommended_additional_tools=["http_request", "github_repo_read"],
        draft_agent_spec={"id": "agent_from_repo", "version": "1.0.0"},
        starter_eval_cases=[{"name": "happy_path"}],
    )

    assert model.recommended_bundle == "repo_to_agent"
    assert "http_request" in model.recommended_additional_tools
    assert model.draft_agent_spec["id"] == "agent_from_repo"
    assert model.starter_eval_cases[0]["name"] == "happy_path"

    dumped = model.model_dump()
    assert dumped["recommended_bundle"] == "repo_to_agent"
    assert isinstance(dumped["starter_eval_cases"], list)


def test_agent_review_output_construction_and_defaults() -> None:
    model = AgentReviewOutput(
        review_notes=["Looks reasonable"],
        risks=["Missing auth checks"],
        open_questions=["Should we add rate limiting?"],
    )

    assert model.review_notes == ["Looks reasonable"]
    assert model.risks == ["Missing auth checks"]
    assert model.open_questions == ["Should we add rate limiting?"]

    dumped = model.model_dump()
    assert dumped["review_notes"] == ["Looks reasonable"]
    assert "risks" in dumped and isinstance(dumped["risks"], list)

    # Defaults are lists when omitted
    default_model = AgentReviewOutput()
    assert default_model.review_notes == []
    assert default_model.risks == []
    assert default_model.open_questions == []


def test_repo_to_agent_result_nested_aggregation_and_serialization() -> None:
    architecture = RepoArchitectureOutput(
        languages=["Python"],
        frameworks=["FastAPI"],
        services=["api"],
        entrypoints=["src/main.py"],
        integrations=["postgres"],
        key_paths=["src/app"],
    )
    result = RepoToAgentResult(
        repo_summary="Repo summary here.",
        architecture=architecture,
        important_files=["README.md"],
        recommended_bundle="repo_to_agent",
        recommended_additional_tools=["http_request"],
        draft_agent_spec={"id": "agent_from_repo", "version": "1.0.0"},
        starter_eval_cases=[{"name": "case1"}],
        review_notes=["Initial draft"],
    )

    assert result.repo_summary == "Repo summary here."
    assert result.architecture.languages == ["Python"]
    assert result.important_files == ["README.md"]
    assert result.recommended_bundle == "repo_to_agent"
    assert result.draft_agent_spec["id"] == "agent_from_repo"
    assert result.review_notes == ["Initial draft"]

    dumped: Dict[str, Any] = result.model_dump()
    assert dumped["architecture"]["languages"] == ["Python"]
    assert dumped["important_files"] == ["README.md"]
    assert dumped["draft_agent_spec"]["id"] == "agent_from_repo"


def test_required_fields_validation() -> None:
    # RepoScoutOutput.repo_summary is required
    with pytest.raises(ValidationError):
        RepoScoutOutput(important_files=["README.md"])  # type: ignore[call-arg]

    # RepoToAgentResult requires repo_summary, architecture, and recommended_bundle
    architecture = RepoArchitectureOutput()
    with pytest.raises(ValidationError):
        RepoToAgentResult(  # type: ignore[call-arg]
            architecture=architecture,
            recommended_bundle="repo_to_agent",
        )

