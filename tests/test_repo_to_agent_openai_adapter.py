from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pytest

from pydantic import ValidationError

from app.repo_to_agent.models import AgentDraftOutput, RepoArchitectureOutput, RepoScoutOutput
from app.repo_to_agent.openai_adapter import build_openai_agent_from_template, run_specialist_with_openai_agent
from app.repo_to_agent.templates import AGENT_DESIGNER_TEMPLATE, REPO_ARCHITECT_TEMPLATE, REPO_SCOUT_TEMPLATE


class FakeTool:
    def __init__(self, fn: Any, *, name_override: Optional[str] = None) -> None:
        self.fn = fn
        self.name = name_override or getattr(fn, "__name__", "tool")

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.fn(*args, **kwargs)


class FakeAgent:
    def __init__(self, *, name: str, instructions: str, tools: List[Any], model: Any, output_type: Any) -> None:
        self.name = name
        self.instructions = instructions
        self.tools = tools
        self.model = model
        self.output_type = output_type


class FakeRunResult:
    def __init__(self, final_output: Any) -> None:
        self.final_output = final_output


class FakeRunner:
    calls: List[Tuple[Any, str]] = []
    next_final_output: Any = None

    @classmethod
    def run_sync(cls, agent: Any, prompt: str) -> FakeRunResult:
        cls.calls.append((agent, prompt))
        return FakeRunResult(final_output=cls.next_final_output)


def fake_function_tool(*, name_override: Optional[str] = None, **kwargs: Any):
    def decorator(fn: Any) -> FakeTool:
        return FakeTool(fn, name_override=name_override)
    return decorator


class FakeOpenAIResponsesModel:
    def __init__(self, *, model: str, openai_client: Any) -> None:
        self.model = model
        self.openai_client = openai_client


def test_build_openai_agent_from_template_builds_repo_scout_agent_and_tool_routes_registry(monkeypatch) -> None:
    """
    Build a real SDK agent shape (mocked) and ensure github_repo_read is exposed and routed
    through our existing DefaultToolRegistry.execute path.
    """
    import app.repo_to_agent.openai_adapter as adapter

    # Patch SDK import boundary.
    monkeypatch.setattr(
        adapter,
        "_import_agents_sdk",
        lambda: (FakeAgent, FakeRunner, fake_function_tool, object, FakeOpenAIResponsesModel),
    )

    # Patch runtime tool registry so we can assert routing.
    execute_calls: List[Tuple[str, Dict[str, Any], Any]] = []

    class FakeRegistry:
        def execute(self, tool_name: str, args: Dict[str, Any], run_context: Any) -> Dict[str, Any]:
            execute_calls.append((tool_name, dict(args), run_context))
            return {"mode": "overview", "repo": {"name": "x"}}

    monkeypatch.setattr(adapter, "DefaultToolRegistry", FakeRegistry)
    monkeypatch.setattr(adapter, "build_run_context", lambda run_id, preset: {"run_id": run_id, "preset": preset})
    # Disable AgentOutputSchema wrapping so output_type is the raw Pydantic model in this test.
    monkeypatch.setattr(adapter, "AgentOutputSchema", None)

    client = object()
    agent = build_openai_agent_from_template(REPO_SCOUT_TEMPLATE, client)

    assert isinstance(agent, FakeAgent)
    assert agent.instructions == REPO_SCOUT_TEMPLATE.prompt
    assert agent.output_type is RepoScoutOutput

    tool_names = [t.name for t in agent.tools]
    assert "github_repo_read" in tool_names

    # Call the function tool directly; it should route through registry.execute.
    github_tool = next(t for t in agent.tools if t.name == "github_repo_read")
    out = github_tool(None, owner="o", repo="r", mode="overview", ref=None, path=None)
    assert out == {"mode": "overview", "repo": {"name": "x"}}
    assert execute_calls
    tool_name, args, run_context = execute_calls[0]
    assert tool_name == "github_repo_read"
    assert args["owner"] == "o"
    assert args["repo"] == "r"
    assert args["mode"] == "overview"


def test_build_openai_agent_from_template_builds_repo_architect_agent(monkeypatch) -> None:
    """repo_architect builds an OpenAI agent with github_repo_read tool and correct output type."""
    import app.repo_to_agent.openai_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "_import_agents_sdk",
        lambda: (FakeAgent, FakeRunner, fake_function_tool, object, FakeOpenAIResponsesModel),
    )
    monkeypatch.setattr(adapter, "DefaultToolRegistry", lambda: object())
    monkeypatch.setattr(adapter, "build_run_context", lambda run_id, preset: object())
    monkeypatch.setattr(adapter, "AgentOutputSchema", None)

    agent = build_openai_agent_from_template(REPO_ARCHITECT_TEMPLATE, client=object())

    assert isinstance(agent, FakeAgent)
    assert agent.instructions == REPO_ARCHITECT_TEMPLATE.prompt
    assert agent.output_type is RepoArchitectureOutput
    assert [t.name for t in agent.tools] == ["github_repo_read"]


def test_build_openai_agent_from_template_builds_agent_designer_agent_without_tools(monkeypatch) -> None:
    """agent_designer builds an OpenAI agent with no tools and AgentDraftOutput output type."""
    import app.repo_to_agent.openai_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "_import_agents_sdk",
        lambda: (FakeAgent, FakeRunner, fake_function_tool, object, FakeOpenAIResponsesModel),
    )
    monkeypatch.setattr(adapter, "DefaultToolRegistry", lambda: object())
    monkeypatch.setattr(adapter, "build_run_context", lambda run_id, preset: object())
    monkeypatch.setattr(adapter, "AgentOutputSchema", None)

    agent = build_openai_agent_from_template(AGENT_DESIGNER_TEMPLATE, client=object())

    assert isinstance(agent, FakeAgent)
    assert agent.instructions == AGENT_DESIGNER_TEMPLATE.prompt
    assert agent.output_type is AgentDraftOutput
    # agent_designer has allowed_tools=[], so no tools should be attached.
    assert agent.tools == []


def test_run_specialist_with_openai_agent_calls_runner_and_returns_dict(monkeypatch) -> None:
    """run_specialist_with_openai_agent uses Runner.run_sync and returns plain dict output."""
    import app.repo_to_agent.openai_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "_import_agents_sdk",
        lambda: (FakeAgent, FakeRunner, fake_function_tool, object, FakeOpenAIResponsesModel),
    )
    monkeypatch.setattr(adapter, "DefaultToolRegistry", lambda: object())
    monkeypatch.setattr(adapter, "build_run_context", lambda run_id, preset: object())

    FakeRunner.calls = []
    FakeRunner.next_final_output = {
        "repo_summary": "A test repo.",
        "important_files": ["README.md"],
        "language_hints": ["Python"],
        "framework_hints": [],
    }

    result = run_specialist_with_openai_agent(
        REPO_SCOUT_TEMPLATE,
        {"owner": "openai", "repo": "agent-toolbox"},
        client=object(),
    )

    assert RepoScoutOutput.model_validate(result)
    assert len(FakeRunner.calls) == 1
    _, prompt = FakeRunner.calls[0]
    assert "Input JSON" in prompt


def test_run_specialist_with_openai_agent_non_supported_template_raises(monkeypatch) -> None:
    """Non-supported templates raise NotImplementedError."""
    class DummyTemplate:
        id = "totally_unknown"

    with pytest.raises(NotImplementedError, match="does not support"):
        run_specialist_with_openai_agent(DummyTemplate(), {}, client=object())


def test_run_specialist_with_openai_agent_repo_architect_returns_dict(monkeypatch) -> None:
    """repo_architect path returns dict that validates as RepoArchitectureOutput."""
    import app.repo_to_agent.openai_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "_import_agents_sdk",
        lambda: (FakeAgent, FakeRunner, fake_function_tool, object, FakeOpenAIResponsesModel),
    )
    monkeypatch.setattr(adapter, "DefaultToolRegistry", lambda: object())
    monkeypatch.setattr(adapter, "build_run_context", lambda run_id, preset: object())

    FakeRunner.calls = []
    FakeRunner.next_final_output = {
        "languages": ["Python"],
        "frameworks": [],
        "services": [],
        "entrypoints": [],
        "integrations": [],
        "key_paths": [],
    }

    result = run_specialist_with_openai_agent(
        REPO_ARCHITECT_TEMPLATE,
        {"owner": "openai", "repo": "agent-toolbox", "scout_summary": {"repo_summary": "x"}},
        client=object(),
    )

    assert RepoArchitectureOutput.model_validate(result)
    assert len(FakeRunner.calls) == 1


def test_run_specialist_with_openai_agent_agent_designer_returns_dict(monkeypatch) -> None:
    """agent_designer path returns dict that validates as AgentDraftOutput."""
    import app.repo_to_agent.openai_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "_import_agents_sdk",
        lambda: (FakeAgent, FakeRunner, fake_function_tool, object, FakeOpenAIResponsesModel),
    )
    monkeypatch.setattr(adapter, "DefaultToolRegistry", lambda: object())
    monkeypatch.setattr(adapter, "build_run_context", lambda run_id, preset: object())

    FakeRunner.calls = []
    FakeRunner.next_final_output = {
        "recommended_bundle": "repo_to_agent",
        "recommended_additional_tools": ["http_request"],
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

    result = run_specialist_with_openai_agent(
        AGENT_DESIGNER_TEMPLATE,
        {
            "owner": "openai",
            "repo": "agent-toolbox",
            "scout": {"repo_summary": "x"},
            "architecture": {"languages": ["Python"]},
        },
        client=object(),
    )

    assert AgentDraftOutput.model_validate(result)
    assert len(FakeRunner.calls) == 1


def test_repo_architect_schema_violation_still_fails_validation() -> None:
    """If OpenAI returns wrong types, workflow-level validation should fail."""
    with pytest.raises(ValidationError):
        RepoArchitectureOutput.model_validate(
            {
                "languages": "Python",  # invalid type
                "frameworks": [],
                "services": [],
                "entrypoints": [],
                "integrations": [],
                "key_paths": [],
            }
        )

