from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pytest
from pydantic import ValidationError

from app.repo_to_agent.workflow import (
    build_repo_workflow,
    run_repo_to_agent_workflow,
)
from app.repo_to_agent.templates import AgentTemplate


def test_build_repo_workflow_returns_expected_step_order() -> None:
    plan = build_repo_workflow({"owner": "openai", "repo": "agent-toolbox"})
    assert plan.owner == "openai"
    assert plan.repo == "agent-toolbox"
    assert plan.steps == [
        "repo_scout",
        "repo_architect",
        "repo_tool_discovery",
        "code_tool_discovery",
        "repo_tool_wrapper",
        "agent_designer",
        "agent_reviewer",
    ]


class RecordingRunner:
    """
    Fake runner that records calls and returns canned outputs.
    """

    def __init__(self) -> None:
        self.calls: List[Tuple[str, Dict[str, Any]]] = []

    def __call__(self, template: AgentTemplate, input_payload: Dict[str, Any], step_telemetry: Dict[str, Any] | None = None) -> Dict[str, Any]:
        self.calls.append((template.id, dict(input_payload)))

        if template.id == "repo_scout":
            return {
                "repo_summary": "A test repo.",
                "important_files": ["README.md", "src/main.py"],
                "language_hints": ["Python"],
                "framework_hints": ["FastAPI"],
            }

        if template.id == "repo_architect":
            return {
                "languages": ["Python"],
                "frameworks": ["FastAPI"],
                "services": ["api"],
                "entrypoints": ["src/main.py"],
                "integrations": ["postgres"],
                "key_paths": ["src/app"],
            }

        if template.id == "repo_tool_discovery":
            return {
                "discovered_tools": [
                    {"name": "main", "tool_type": "cli", "command": "mycli", "description": None, "source_path": "pyproject.toml", "confidence": 0.9},
                ],
            }

        if template.id == "code_tool_discovery":
            return {"code_tools": []}

        if template.id == "agent_designer":
            return {
                "recommended_bundle": "repo_to_agent",
                "recommended_additional_tools": ["http_request", "github_repo_read"],
                "draft_agent_spec": {
                    "id": "agent_from_repo",
                    "version": "1.0.0",
                    "name": "Agent From Repo",
                    "description": "Draft agent for the test repo.",
                    "primitive": "transform",
                    "input_schema": {"type": "object", "properties": {}},
                    "output_schema": {"type": "object", "properties": {}},
                    "prompt": "You are an agent for the test repo.",
                },
                "starter_eval_cases": [{"name": "case1"}],
            }

        if template.id == "agent_reviewer":
            return {
                "review_notes": ["Looks good overall."],
                "risks": ["Limited eval coverage"],
                "open_questions": ["Should we add auth tests?"],
            }

        raise ValueError(f"Unexpected template id: {template.id}")


def test_run_repo_to_agent_workflow_aggregates_outputs_and_passes_inputs_correctly() -> None:
    plan = build_repo_workflow({"owner": "openai", "repo": "agent-toolbox"})
    runner = RecordingRunner()

    result = run_repo_to_agent_workflow(plan, runner)

    # Aggregated result checks
    assert result.repo_summary == "A test repo."
    assert result.architecture.languages == ["Python"]
    assert result.important_files == ["README.md", "src/main.py"]
    assert result.recommended_bundle == "repo_to_agent"
    assert result.draft_agent_spec.get("id") == "openai_agent_toolbox"
    assert result.draft_agent_spec.get("version") == "1.0.0-ed36d8da2e"
    # Workflow filters recommended_additional_tools: github_repo_read is in bundle so removed; http_request remains.
    assert result.recommended_additional_tools == ["http_request"]
    assert "Looks good overall." in result.review_notes
    assert any("Removed redundant tools already in bundle" in n for n in result.review_notes)
    assert len(result.discovered_repo_tools) == 1
    assert result.discovered_repo_tools[0].name == "main"
    assert result.discovered_repo_tools[0].tool_type == "cli"

    # Wrapped tools: one discovered (main/cli) -> one wrapped (medium risk, not safe_to_auto_expose)
    assert len(result.wrapped_repo_tools) == 1
    assert result.wrapped_repo_tools[0].name == "main"
    assert result.wrapped_repo_tools[0].wrapper_kind == "command"
    assert result.wrapped_repo_tools[0].args_schema is not None

    # Runner call order and input payload propagation (repo_tool_wrapper is in-process, no call)
    call_ids = [cid for cid, _ in runner.calls]
    assert call_ids == [
        "repo_scout",
        "repo_architect",
        "repo_tool_discovery",
        "code_tool_discovery",
        "agent_designer",
        "agent_reviewer",
    ]

    # repo_scout gets only repo coordinates (+optional ref)
    _, scout_input = runner.calls[0]
    assert scout_input["owner"] == "openai"
    assert scout_input["repo"] == "agent-toolbox"
    assert set(scout_input.keys()) == {"owner", "repo"}

    # repo_architect gets coords + scout_summary
    _, architect_input = runner.calls[1]
    assert architect_input["owner"] == "openai"
    assert architect_input["repo"] == "agent-toolbox"
    assert "scout_summary" in architect_input
    assert architect_input["scout_summary"]["repo_summary"] == "A test repo."

    # repo_tool_discovery gets coords + scout + architecture
    _, discovery_input = runner.calls[2]
    assert discovery_input["owner"] == "openai"
    assert discovery_input["repo"] == "agent-toolbox"
    assert "scout" in discovery_input
    assert "architecture" in discovery_input

    # agent_designer gets coords + scout + architecture + discovered_repo_tools + wrapped_repo_tools
    _, designer_input = runner.calls[4]
    assert designer_input["owner"] == "openai"
    assert designer_input["repo"] == "agent-toolbox"
    assert "scout" in designer_input
    assert "architecture" in designer_input
    assert "discovered_repo_tools" in designer_input
    assert "wrapped_repo_tools" in designer_input
    assert len(designer_input["wrapped_repo_tools"]) == 1
    assert designer_input["architecture"]["languages"] == ["Python"]

    # agent_reviewer gets coords + scout + architecture + draft
    _, reviewer_input = runner.calls[5]
    assert reviewer_input["owner"] == "openai"
    assert reviewer_input["repo"] == "agent-toolbox"
    assert "scout" in reviewer_input
    assert "architecture" in reviewer_input
    assert "draft" in reviewer_input
    assert reviewer_input["draft"]["recommended_bundle"] == "repo_to_agent"


def test_workflow_normalizes_invalid_bundle_to_catalog_fallback_and_records_in_review_notes() -> None:
    """
    When agent_designer returns a recommended_bundle not in the bundles catalog,
    workflow replaces it with a fallback (repo_to_agent or no_tools_writer) and
    appends a review_note.
    """
    plan = build_repo_workflow({"owner": "x", "repo": "y"})

    def runner(template: AgentTemplate, input_payload: Dict[str, Any], step_telemetry: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if template.id == "repo_scout":
            return {
                "repo_summary": "Summary.",
                "important_files": ["README.md"],
                "language_hints": [],
                "framework_hints": [],
            }
        if template.id == "repo_architect":
            return {
                "languages": ["Python"],
                "frameworks": [],
                "services": [],
                "entrypoints": [],
                "integrations": [],
                "key_paths": [],
            }
        if template.id == "repo_tool_discovery":
            return {"discovered_tools": []}
        if template.id == "code_tool_discovery":
            return {"code_tools": []}
        if template.id == "agent_designer":
            return {
                "recommended_bundle": "not_in_catalog_bundle",
                "recommended_additional_tools": [],
                "draft_agent_spec": {
                    "id": "a",
                    "version": "1.0.0",
                    "name": "A",
                    "description": "D",
                    "primitive": "transform",
                    "input_schema": {"type": "object", "properties": {}},
                    "output_schema": {"type": "object", "properties": {}},
                    "prompt": "P",
                },
                "starter_eval_cases": [{"name": "e1", "input": {}, "expected": "X"}],
            }
        if template.id == "agent_reviewer":
            return {"review_notes": [], "risks": [], "open_questions": []}
        raise ValueError(template.id)

    result = run_repo_to_agent_workflow(plan, runner)

    assert result.recommended_bundle in ("repo_to_agent", "no_tools_writer")
    assert any("Normalized recommended_bundle" in n and "not_in_catalog_bundle" in n for n in result.review_notes)


def test_workflow_filters_invalid_and_redundant_tools_and_records_in_review_notes() -> None:
    """
    Workflow filtering: agent_designer returns valid + invalid + bundle tool;
    invalid and bundle tools are removed, only valid non-bundle tool remains;
    review_notes record both removals.
    """
    plan = build_repo_workflow({"owner": "x", "repo": "y"})

    def runner(template: AgentTemplate, input_payload: Dict[str, Any], step_telemetry: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if template.id == "repo_scout":
            return {
                "repo_summary": "Summary.",
                "important_files": ["README.md"],
                "language_hints": [],
                "framework_hints": [],
            }
        if template.id == "repo_architect":
            return {
                "languages": ["Python"],
                "frameworks": [],
                "services": [],
                "entrypoints": [],
                "integrations": [],
                "key_paths": [],
            }
        if template.id == "repo_tool_discovery":
            return {"discovered_tools": []}
        if template.id == "code_tool_discovery":
            return {"code_tools": []}
        if template.id == "agent_designer":
            # Valid catalog tool (http_request), invalid (made_up_tool), already in bundle (github_repo_read)
            return {
                "recommended_bundle": "repo_to_agent",
                "recommended_additional_tools": ["http_request", "made_up_tool", "github_repo_read"],
                "draft_agent_spec": {
                    "id": "a",
                    "version": "1.0.0",
                    "name": "A",
                    "description": "D",
                    "primitive": "transform",
                    "input_schema": {},
                    "output_schema": {},
                    "prompt": "P",
                },
                "starter_eval_cases": [{"name": "e1", "input": {}, "expected": "X"}],
            }
        if template.id == "agent_reviewer":
            return {"review_notes": [], "risks": [], "open_questions": []}
        raise ValueError(template.id)

    result = run_repo_to_agent_workflow(plan, runner)

    assert result.recommended_additional_tools == ["http_request"]
    assert any("Removed invalid tool IDs" in n and "made_up_tool" in n for n in result.review_notes)
    assert any("Removed redundant tools already in bundle" in n and "github_repo_read" in n for n in result.review_notes)


def test_malformed_specialist_output_raises_validation_error() -> None:
    plan = build_repo_workflow({"owner": "openai", "repo": "agent-toolbox"})

    def bad_runner(template: AgentTemplate, input_payload: Dict[str, Any], step_telemetry: Dict[str, Any] | None = None) -> Dict[str, Any]:
        # repo_scout returns valid output
        if template.id == "repo_scout":
            return {
                "repo_summary": "A test repo.",
                "important_files": ["README.md"],
                "language_hints": ["Python"],
                "framework_hints": [],
            }
        # repo_architect returns malformed output (languages should be a list)
        if template.id == "repo_architect":
            return {
                "languages": "Python",  # invalid type
                "frameworks": [],
                "services": [],
                "entrypoints": [],
                "integrations": [],
                "key_paths": [],
            }
        if template.id == "repo_tool_discovery":
            return {"discovered_tools": []}
        if template.id == "code_tool_discovery":
            return {"code_tools": []}
        return {}

    with pytest.raises(ValidationError):
        run_repo_to_agent_workflow(plan, bad_runner)


def test_malformed_repo_scout_output_raises_validation_error() -> None:
    plan = build_repo_workflow({"owner": "openai", "repo": "agent-toolbox"})

    def bad_runner(template: AgentTemplate, input_payload: Dict[str, Any], step_telemetry: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if template.id == "repo_scout":
            return {
                "repo_summary": "A test repo.",
                "important_files": "README.md",  # invalid type (should be list[str])
                "language_hints": ["Python"],
                "framework_hints": [],
            }
        return {}

    with pytest.raises(ValidationError):
        run_repo_to_agent_workflow(plan, bad_runner)


def test_malformed_agent_designer_output_raises_validation_error() -> None:
    plan = build_repo_workflow({"owner": "openai", "repo": "agent-toolbox"})

    def bad_runner(template: AgentTemplate, input_payload: Dict[str, Any], step_telemetry: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if template.id == "repo_scout":
            return {
                "repo_summary": "A test repo.",
                "important_files": ["README.md"],
                "language_hints": ["Python"],
                "framework_hints": [],
            }
        if template.id == "repo_architect":
            return {
                "languages": ["Python"],
                "frameworks": [],
                "services": [],
                "entrypoints": [],
                "integrations": [],
                "key_paths": [],
            }
        if template.id == "repo_tool_discovery":
            return {"discovered_tools": []}
        if template.id == "code_tool_discovery":
            return {"code_tools": []}
        if template.id == "agent_designer":
            # recommended_bundle must be a string; use wrong type to trigger validation error.
            return {
                "recommended_bundle": ["not-a-string"],
                "recommended_additional_tools": [],
                "draft_agent_spec": {},
                "starter_eval_cases": [],
            }
        return {}

    with pytest.raises(ValidationError):
        run_repo_to_agent_workflow(plan, bad_runner)

