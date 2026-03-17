"""
Tests for repo-to-agent internal runner.

Uses patched tool execution to avoid live GitHub API calls.
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import patch

import pytest

from app.repo_to_agent.internal_runner import run_specialist_with_internal_runner
from app.repo_to_agent.models import (
    AgentDraftOutput,
    RepoArchitectureOutput,
    RepoScoutOutput,
)
from app.repo_to_agent.templates import (
    AGENT_DESIGNER_TEMPLATE,
    AGENT_REVIEWER_TEMPLATE,
    REPO_ARCHITECT_TEMPLATE,
    REPO_SCOUT_TEMPLATE,
)


def _canned_overview() -> Dict[str, Any]:
    return {
        "mode": "overview",
        "repo": {"name": "test-repo", "owner": "test-owner", "default_branch": "main"},
        "top_level": [{"path": "README.md", "type": "file"}, {"path": "src", "type": "dir"}],
        "important_files": ["README.md", "src/main.py"],
        "hints": {"languages": ["Python"], "frameworks": ["FastAPI"]},
        "truncated": False,
    }


def _canned_sample() -> Dict[str, Any]:
    return {
        "mode": "sample",
        "repo": {"name": "test-repo", "owner": "test-owner"},
        "files": [{"path": "README.md", "content": "# Test", "truncated": False}],
        "important_files": ["README.md", "src/main.py"],
        "hints": {"languages": ["Python"], "frameworks": []},
    }


def _canned_tree() -> Dict[str, Any]:
    return {
        "mode": "tree",
        "repo": {"name": "test-repo"},
        "path": "/",
        "entries": [
            {"path": "README.md", "type": "file"},
            {"path": "src/main.py", "type": "file"},
            {"path": "src/app", "type": "dir"},
        ],
        "truncated": False,
    }


@patch("app.repo_to_agent.internal_runner.DefaultToolRegistry")
def test_run_specialist_repo_scout_returns_valid_scout_output(mock_registry_class: Any) -> None:
    """Internal runner repo_scout returns dict that validates as RepoScoutOutput."""
    mock_registry = mock_registry_class.return_value
    mock_registry.execute.side_effect = lambda name, args, ctx: (
        _canned_overview() if args.get("mode") == "overview" else _canned_sample()
    )

    result = run_specialist_with_internal_runner(
        REPO_SCOUT_TEMPLATE,
        {"owner": "test-owner", "repo": "test-repo"},
    )

    out = RepoScoutOutput.model_validate(result)
    assert "test-repo" in out.repo_summary
    assert out.important_files == ["README.md", "src/main.py"]
    assert "Python" in out.language_hints
    assert out.framework_hints == ["FastAPI"]


@patch("app.repo_to_agent.internal_runner.DefaultToolRegistry")
def test_run_specialist_repo_architect_returns_valid_architect_output(mock_registry_class: Any) -> None:
    """Internal runner repo_architect returns dict that validates as RepoArchitectureOutput."""
    mock_registry = mock_registry_class.return_value
    mock_registry.execute.side_effect = lambda name, args, ctx: (
        _canned_overview() if args.get("mode") == "overview" else _canned_tree()
    )

    result = run_specialist_with_internal_runner(
        REPO_ARCHITECT_TEMPLATE,
        {"owner": "test-owner", "repo": "test-repo"},
    )

    out = RepoArchitectureOutput.model_validate(result)
    assert "Python" in out.languages
    assert "FastAPI" in out.frameworks
    assert "src/main.py" in out.entrypoints or "src/main.py" in out.key_paths


def test_run_specialist_agent_designer_returns_valid_draft_without_tools() -> None:
    """Internal runner agent_designer uses repo tool discovery for bundle + additional_tools."""
    input_payload = {
        "scout": {"repo_summary": "A Python API repo.", "important_files": ["main.py"]},
        "architecture": {"languages": ["Python"], "frameworks": ["FastAPI"], "services": [], "entrypoints": [], "integrations": [], "key_paths": []},
    }
    result = run_specialist_with_internal_runner(AGENT_DESIGNER_TEMPLATE, input_payload)

    out = AgentDraftOutput.model_validate(result)
    assert out.recommended_bundle == "repo_to_agent"
    # github_repo_read is in the bundle; additional_tools only has extras (e.g. http_request when API signals present)
    assert out.recommended_additional_tools == []  # no HTTP/API signals in this payload
    assert out.draft_agent_spec.get("id") == "draft-from-repo"
    assert out.draft_agent_spec.get("version") == "0.1.0"
    assert "prompt" in out.draft_agent_spec


def test_run_specialist_agent_reviewer_returns_valid_review_stub() -> None:
    """Internal runner agent_reviewer (no tools) returns valid stub."""
    input_payload = {"draft": {"id": "draft-1", "recommended_bundle": "repo_to_agent"}}
    result = run_specialist_with_internal_runner(AGENT_REVIEWER_TEMPLATE, input_payload)

    assert "review_notes" in result
    assert isinstance(result["review_notes"], list)
    assert "risks" in result
    assert "open_questions" in result


def test_run_specialist_repo_scout_requires_owner_repo() -> None:
    """repo_scout with missing owner/repo raises."""
    with pytest.raises(ValueError, match="owner and repo"):
        run_specialist_with_internal_runner(REPO_SCOUT_TEMPLATE, {"owner": "x"})
    with pytest.raises(ValueError, match="owner and repo"):
        run_specialist_with_internal_runner(REPO_SCOUT_TEMPLATE, {"repo": "y"})
