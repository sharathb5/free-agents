"""Tests for repo-based tool discovery (discover_tools_from_repo)."""

from __future__ import annotations

import pytest

from app.repo_to_agent.models import RepoArchitectureOutput, RepoScoutOutput
from app.repo_to_agent.tool_discovery import discover_tools_from_repo


def test_discover_tools_code_repo_default_bundle() -> None:
    """Code repo with languages and entrypoints gets repo_to_agent or github_reader."""
    scout = {"repo_summary": "A Python API.", "important_files": ["src/main.py"], "language_hints": ["Python"], "framework_hints": []}
    arch = {"languages": ["Python"], "frameworks": [], "services": ["api"], "entrypoints": ["main.py"], "integrations": [], "key_paths": ["src/"]}
    out = discover_tools_from_repo(scout, arch)
    assert out["bundle_id"] in ("repo_to_agent", "github_reader")
    assert "rationale" in out
    assert isinstance(out["additional_tools"], list)


def test_discover_tools_no_code_signals_uses_no_tools_writer() -> None:
    """Repo with no code signals gets no_tools_writer."""
    scout = {"repo_summary": "Docs only.", "important_files": ["README.md"], "language_hints": [], "framework_hints": []}
    arch = {"languages": [], "frameworks": [], "services": [], "entrypoints": [], "integrations": [], "key_paths": []}
    out = discover_tools_from_repo(scout, arch)
    assert out["bundle_id"] == "no_tools_writer"
    assert out["additional_tools"] == []


def test_discover_tools_http_api_adds_http_request() -> None:
    """Repo with HTTP/API signals gets http_request in additional_tools (if not in bundle)."""
    scout = {"repo_summary": "HTTP client lib.", "important_files": ["requests/api.py", "client.py"], "language_hints": ["Python"], "framework_hints": []}
    arch = {"languages": ["Python"], "frameworks": [], "services": [], "entrypoints": [], "integrations": ["REST", "webhook"], "key_paths": ["requests/"]}
    out = discover_tools_from_repo(scout, arch)
    assert out["bundle_id"] in ("repo_to_agent", "github_reader")
    assert "http_request" in out["additional_tools"]


def test_discover_tools_accepts_pydantic_models() -> None:
    """discover_tools_from_repo accepts RepoScoutOutput and RepoArchitectureOutput."""
    scout = RepoScoutOutput(
        repo_summary="Test repo",
        important_files=["main.py"],
        language_hints=["Python"],
        framework_hints=[],
    )
    arch = RepoArchitectureOutput(
        languages=["Python"],
        frameworks=[],
        services=[],
        entrypoints=["main.py"],
        integrations=[],
        key_paths=[],
    )
    out = discover_tools_from_repo(scout, arch)
    assert out["bundle_id"] in ("repo_to_agent", "github_reader")
    assert "additional_tools" in out
    assert "rationale" in out


def test_discover_tools_internal_runner_agent_designer_uses_discovery() -> None:
    """Internal runner agent_designer uses discovery for bundle and additional_tools."""
    from app.repo_to_agent.internal_runner import run_specialist_with_internal_runner
    from app.repo_to_agent.templates import AGENT_DESIGNER_TEMPLATE

    # HTTP-heavy repo -> should get http_request as additional tool
    input_payload = {
        "owner": "encode",
        "repo": "httpx",
        "scout": {
            "repo_summary": "HTTP client.",
            "important_files": ["httpx/api.py", "client.py"],
            "language_hints": ["Python"],
            "framework_hints": [],
        },
        "architecture": {
            "languages": ["Python"],
            "frameworks": [],
            "services": [],
            "entrypoints": ["httpx/__main__.py"],
            "integrations": ["http", "api"],
            "key_paths": ["httpx/"],
        },
    }
    result = run_specialist_with_internal_runner(AGENT_DESIGNER_TEMPLATE, input_payload)
    assert result["recommended_bundle"] in ("repo_to_agent", "github_reader")
    assert "http_request" in result["recommended_additional_tools"]
