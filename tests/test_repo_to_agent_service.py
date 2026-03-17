from __future__ import annotations

from typing import Any, Dict

import pytest

from app.repo_to_agent.models import RepoArchitectureOutput, RepoScoutOutput, RepoToAgentResult
from app.repo_to_agent.service import generate_agent_from_repo
from app.repo_to_agent.templates import AgentTemplate


def test_generate_agent_from_repo_builds_workflow_and_runs_runner(monkeypatch) -> None:
    calls: Dict[str, Any] = {}

    def fake_build_repo_workflow(repo_input: Dict[str, Any]) -> Any:
        from app.repo_to_agent.workflow import RepoWorkflowPlan

        calls["repo_input"] = dict(repo_input)
        return RepoWorkflowPlan(owner="openai", repo="agent-toolbox", steps=["repo_scout"])

    def fake_run_repo_to_agent_workflow(plan: Any, runner: Any) -> RepoToAgentResult:
        calls["plan"] = plan
        calls["runner"] = runner
        # Minimal but valid RepoToAgentResult for testing.
        scout = RepoScoutOutput(repo_summary="Summary", important_files=[], language_hints=[], framework_hints=[])
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

    monkeypatch.setattr("app.repo_to_agent.service.build_repo_workflow", fake_build_repo_workflow)
    monkeypatch.setattr("app.repo_to_agent.service.run_repo_to_agent_workflow", fake_run_repo_to_agent_workflow)

    def dummy_runner(template: AgentTemplate, input_payload: Dict[str, Any]) -> Dict[str, Any]:
        return {}

    repo_input = {"owner": "openai", "repo": "agent-toolbox"}
    result = generate_agent_from_repo(repo_input, dummy_runner)

    # Service should pass repo_input through to build_repo_workflow.
    assert calls["repo_input"] == repo_input
    # Service should pass the returned plan and runner into run_repo_to_agent_workflow.
    assert calls["plan"].owner == "openai"
    assert calls["plan"].repo == "agent-toolbox"
    assert calls["runner"] is dummy_runner

    # Result should be whatever run_repo_to_agent_workflow returned.
    assert isinstance(result, RepoToAgentResult)
    assert result.repo_summary == "Summary"
    assert result.recommended_bundle == "repo_to_agent"


def test_generate_agent_from_repo_invalid_input_surfaces_error() -> None:
    def dummy_runner(template: AgentTemplate, input_payload: Dict[str, Any]) -> Dict[str, Any]:
        return {}

    # Non-dict input should cause build_repo_workflow to raise a TypeError.
    with pytest.raises((TypeError, ValueError)):
        generate_agent_from_repo("not-a-dict", dummy_runner)  # type: ignore[arg-type]

