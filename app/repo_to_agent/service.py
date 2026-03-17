from __future__ import annotations

from typing import Any, Callable, Dict

from .models import RepoToAgentResult
from .templates import AgentTemplate
from .workflow import RepoWorkflowPlan, build_repo_workflow, run_repo_to_agent_workflow


def generate_agent_from_repo(
    repo_input: Dict[str, Any],
    runner: Callable[[AgentTemplate, Dict[str, Any]], Dict[str, Any]],
) -> RepoToAgentResult:
    """
    Thin service-layer entrypoint for the repo-to-agent workflow.

    This function:
      1. Normalizes the repo input into a RepoWorkflowPlan via build_repo_workflow.
      2. Executes the workflow via run_repo_to_agent_workflow using the provided runner.
      3. Returns the resulting RepoToAgentResult unchanged.

    It is SDK-agnostic and does not call any tools directly.
    """
    plan: RepoWorkflowPlan = build_repo_workflow(repo_input)
    return run_repo_to_agent_workflow(plan, runner)

