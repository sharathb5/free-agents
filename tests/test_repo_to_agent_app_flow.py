"""
Tests for repo-to-agent app flow (run_repo_to_agent).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.repo_to_agent.app_flow import run_repo_to_agent
from app.repo_to_agent.exceptions import StepTimeoutError
from app.repo_to_agent.models import RepoArchitectureOutput, RepoScoutOutput, RepoToAgentResult
from app.repo_to_agent.templates import (
    AGENT_DESIGNER_TEMPLATE,
    AGENT_REVIEWER_TEMPLATE,
    REPO_ARCHITECT_TEMPLATE,
    REPO_SCOUT_TEMPLATE,
)


@patch("app.repo_to_agent.app_flow.run_specialist_with_internal_runner")
def test_run_repo_to_agent_internal_returns_result(mock_runner: object) -> None:
    """run_repo_to_agent(..., execution_backend='internal') returns RepoToAgentResult."""
    def fake_runner(template: object, input_payload: object, step_telemetry: object | None = None) -> dict:
        tid = getattr(template, "id", "")
        if tid == "repo_scout":
            return {
                "repo_summary": "Fake repo.",
                "important_files": ["README.md"],
                "language_hints": ["Python"],
                "framework_hints": [],
            }
        if tid == "repo_architect":
            return {
                "languages": ["Python"],
                "frameworks": [],
                "services": [],
                "entrypoints": [],
                "integrations": [],
                "key_paths": [],
            }
        if tid == "agent_designer":
            return {
                "recommended_bundle": "repo_to_agent",
                "recommended_additional_tools": [],
                "draft_agent_spec": {"id": "draft", "version": "0.1.0", "name": "Draft", "description": "", "primitive": "transform", "input_schema": {}, "output_schema": {}, "prompt": ""},
                "starter_eval_cases": [],
            }
        if tid == "agent_reviewer":
            return {"review_notes": [], "risks": [], "open_questions": []}
        return {}

    mock_runner.side_effect = fake_runner

    result = run_repo_to_agent({"owner": "o", "repo": "r"}, execution_backend="internal")

    assert isinstance(result, RepoToAgentResult)
    assert result.repo_summary == "Fake repo."
    assert result.recommended_bundle == "repo_to_agent"
    assert result.draft_agent_spec.get("id") == "draft"


def test_run_repo_to_agent_unsupported_backend_raises() -> None:
    """Unsupported execution_backend raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported execution_backend"):
        run_repo_to_agent({"owner": "o", "repo": "r"}, execution_backend="bogus")


@patch("app.repo_to_agent.app_flow.generate_agent_from_repo")
@patch("app.repo_to_agent.app_flow.run_specialist_with_openai_agent")
@patch("app.repo_to_agent.app_flow.run_specialist_with_internal_runner")
def test_run_repo_to_agent_openai_hybrid_uses_openai_for_scout_architect_and_designer(
    mock_internal: object,
    mock_openai: object,
    mock_generate: object,
) -> None:
    """execution_backend='openai' uses OpenAI for repo_scout+repo_architect+agent_designer and internal for reviewer."""
    import app.repo_to_agent.app_flow as flow

    # Capture the runner passed into the service.
    captured = {}

    def fake_generate(repo_input, runner):
        captured["runner"] = runner
        # Return a minimal valid RepoToAgentResult without running workflow.
        return RepoToAgentResult(
            repo_summary="x",
            architecture=RepoArchitectureOutput(),
            important_files=[],
            recommended_bundle="repo_to_agent",
            recommended_additional_tools=[],
            draft_agent_spec={},
            starter_eval_cases=[],
            review_notes=[],
        )

    mock_generate.side_effect = fake_generate
    mock_openai.return_value = {"repo_summary": "ok", "important_files": [], "language_hints": [], "framework_hints": []}
    mock_internal.return_value = {"languages": [], "frameworks": [], "services": [], "entrypoints": [], "integrations": [], "key_paths": []}

    # Avoid importing real OpenAI client in tests.
    class FakeAsyncOpenAI:
        def __init__(self) -> None:
            pass

    flow._import_async_openai_client = lambda: FakeAsyncOpenAI  # type: ignore[assignment]

    run_repo_to_agent({"owner": "o", "repo": "r"}, execution_backend="openai")

    runner = captured["runner"]
    mock_openai.reset_mock()
    mock_internal.reset_mock()

    # repo_scout -> OpenAI
    runner(REPO_SCOUT_TEMPLATE, {"owner": "o", "repo": "r"})
    assert mock_openai.called
    assert not mock_internal.called

    mock_openai.reset_mock()
    mock_internal.reset_mock()

    # repo_architect -> OpenAI
    runner(REPO_ARCHITECT_TEMPLATE, {"owner": "o", "repo": "r", "scout_summary": {}})
    assert mock_openai.called
    assert not mock_internal.called

    mock_openai.reset_mock()
    mock_internal.reset_mock()

    # agent_designer -> OpenAI
    runner(AGENT_DESIGNER_TEMPLATE, {"owner": "o", "repo": "r", "scout": {}, "architecture": {}})
    assert mock_openai.called
    assert not mock_internal.called

    mock_openai.reset_mock()
    mock_internal.reset_mock()

    # agent_reviewer -> internal
    runner(AGENT_REVIEWER_TEMPLATE, {"owner": "o", "repo": "r", "scout": {}, "architecture": {}, "draft": {}})
    assert mock_internal.called
    assert not mock_openai.called


@patch("app.repo_to_agent.app_flow.run_specialist_with_internal_runner")
@patch("app.repo_to_agent.app_flow.run_specialist_with_openai_agent")
@patch("app.repo_to_agent.app_flow.generate_agent_from_repo")
def test_openai_runner_falls_back_to_internal_on_max_turns(
    mock_generate: MagicMock,
    mock_openai: MagicMock,
    mock_internal: MagicMock,
) -> None:
    """repo_scout/architect should fall back to internal on MaxTurnsExceeded-like errors."""
    import app.repo_to_agent.app_flow as flow

    class MaxTurnsExceeded(Exception):
        pass

    MaxTurnsExceeded.__module__ = "agents.runtime"

    captured = {}

    def fake_generate(repo_input, runner):
        captured["runner"] = runner
        # Minimal valid result; we only care about telemetry/review_notes shape.
        scout = RepoScoutOutput(repo_summary="s", important_files=[], language_hints=[], framework_hints=[])
        arch = RepoArchitectureOutput()
        return RepoToAgentResult(
            repo_summary=scout.repo_summary,
            architecture=arch,
            important_files=scout.important_files,
            recommended_bundle="repo_to_agent",
            recommended_additional_tools=[],
            draft_agent_spec={},
            starter_eval_cases=[],
            review_notes=[],
        )

    mock_generate.side_effect = fake_generate

    def raising_openai(*_args, **_kwargs):
        raise MaxTurnsExceeded("max turns exceeded")

    mock_openai.side_effect = raising_openai
    mock_internal.return_value = {
        "repo_summary": "fallback",
        "important_files": [],
        "language_hints": [],
        "framework_hints": [],
    }

    class FakeAsyncOpenAI:
        def __init__(self) -> None:
            pass

    flow._import_async_openai_client = lambda: FakeAsyncOpenAI  # type: ignore[assignment]

    result = run_repo_to_agent({"owner": "o", "repo": "r"}, execution_backend="openai")
    assert isinstance(result, RepoToAgentResult)

    runner = captured["runner"]
    step_telemetry: dict = {
        "step_name": "repo_scout",
        "backend_used": "openai",
        "fallback_triggered": False,
        "tool_calls_count": None,
        "duration_ms": 0,
    }
    out, notes = runner(REPO_SCOUT_TEMPLATE, {"owner": "o", "repo": "r"}, step_telemetry)  # type: ignore[misc]
    assert mock_internal.called
    assert out["repo_summary"] == "fallback"
    assert step_telemetry["backend_used"] == "internal"
    assert step_telemetry["fallback_triggered"] is True
    assert any("used internal fallback" in n for n in notes)


@patch("app.repo_to_agent.app_flow.run_specialist_with_internal_runner")
@patch("app.repo_to_agent.app_flow.run_specialist_with_openai_agent")
@patch("app.repo_to_agent.app_flow.generate_agent_from_repo")
def test_large_repo_routing_uses_internal_for_architect(
    mock_generate: MagicMock,
    mock_openai: MagicMock,
    mock_internal: MagicMock,
) -> None:
    """Large-repo routing rule should bypass OpenAI for repo_architect."""
    import app.repo_to_agent.app_flow as flow

    captured = {}

    def fake_generate(repo_input, runner):
        captured["runner"] = runner
        scout = RepoScoutOutput(
            repo_summary="large",
            important_files=[f"file_{i}.py" for i in range(0, 205)],
            language_hints=["Python"] * 1,
            framework_hints=[],
        )
        arch = RepoArchitectureOutput()
        return RepoToAgentResult(
            repo_summary=scout.repo_summary,
            architecture=arch,
            important_files=scout.important_files,
            recommended_bundle="repo_to_agent",
            recommended_additional_tools=[],
            draft_agent_spec={},
            starter_eval_cases=[],
            review_notes=[],
        )

    mock_generate.side_effect = fake_generate
    mock_openai.return_value = {}
    mock_internal.return_value = {
        "languages": [],
        "frameworks": [],
        "services": [],
        "entrypoints": [],
        "integrations": [],
        "key_paths": [],
    }

    class FakeAsyncOpenAI:
        def __init__(self) -> None:
            pass

    flow._import_async_openai_client = lambda: FakeAsyncOpenAI  # type: ignore[assignment]

    run_repo_to_agent({"owner": "o", "repo": "r"}, execution_backend="openai")
    runner = captured["runner"]

    step_telemetry: dict = {
        "step_name": "repo_architect",
        "backend_used": "openai",
        "fallback_triggered": False,
        "tool_calls_count": None,
        "duration_ms": 0,
    }
    scout_summary = {
        "repo_summary": "large",
        "important_files": [f"file_{i}.py" for i in range(0, 205)],
        "language_hints": ["Python"],
        "framework_hints": [],
    }
    out, notes = runner(
        REPO_ARCHITECT_TEMPLATE,
        {"owner": "o", "repo": "r", "scout_summary": scout_summary},
        step_telemetry,
    )  # type: ignore[misc]

    assert mock_internal.called
    assert not mock_openai.called
    assert isinstance(out, dict)
    assert step_telemetry["backend_used"] == "internal"
    assert step_telemetry["fallback_triggered"] is False
    assert any("large repo routing rule" in n for n in notes)
