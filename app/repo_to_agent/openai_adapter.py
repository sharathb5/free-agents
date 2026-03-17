from __future__ import annotations

import json
import os
from typing import Any, Dict, Generic, Tuple, Type, TypeVar

# Model for repo-to-agent specialists; override via REPO_TO_AGENT_OPENAI_MODEL (e.g. gpt-4o-mini for higher TPM).
DEFAULT_OPENAI_MODEL = "gpt-4.1"
# Specialists (scout/architect) make many tool calls per repo; SDK default is 10.
# Override via REPO_TO_AGENT_MAX_TURNS env.
REPO_TO_AGENT_MAX_TURNS = 120
# Step-level wall-clock timeout (seconds). Override via REPO_TO_AGENT_STEP_TIMEOUT_SECONDS.
REPO_TO_AGENT_STEP_TIMEOUT_SECONDS = 300

from app.preset_loader import Preset
from app.runtime.tools.registry import DefaultToolRegistry, RunContext, build_run_context

from .templates import AgentTemplate
from .templates import AGENT_DESIGNER_TEMPLATE, REPO_ARCHITECT_TEMPLATE, REPO_SCOUT_TEMPLATE
from .models import AgentDraftOutput, RepoArchitectureOutput, RepoScoutOutput

T = TypeVar("T")

try:  # The Agents SDK uses this to exclude ctx from tool schema.
    from agents import RunContextWrapper as AgentsRunContextWrapper  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - used in environments without the SDK
    class AgentsRunContextWrapper(Generic[T]):  # type: ignore[no-redef]
        pass

try:
    # Optional: used to enable/disable strict JSON schema for output types.
    from agents import AgentOutputSchema as _AgentOutputSchema  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - used in environments without the SDK
    _AgentOutputSchema = None

AgentOutputSchema = _AgentOutputSchema


def _import_agents_sdk() -> Tuple[Any, Any, Any, Any, Any]:
    """
    Import OpenAI Agents SDK pieces (lazy import for testability).

    Returns: (Agent, Runner, function_tool, RunContextWrapper, OpenAIResponsesModel)
    """
    from agents import Agent, Runner, RunContextWrapper, function_tool  # type: ignore[import-not-found]
    from agents.models.openai_responses import OpenAIResponsesModel  # type: ignore[import-not-found]

    return Agent, Runner, function_tool, RunContextWrapper, OpenAIResponsesModel


def _template_to_preset(template: AgentTemplate) -> Preset:
    """Build a minimal Preset from an AgentTemplate for run context."""
    return Preset(
        id=template.id,
        version="openai",
        name=template.role,
        description=template.description or "",
        primitive=template.role,
        input_schema=template.input_schema,
        output_schema=template.output_schema,
        prompt=template.prompt,
        supports_memory=False,
        memory_policy=None,
        allowed_tools=list(template.allowed_tools),
        http_allowed_domains=None,
        tool_policies={
            # Repo-to-agent specialists can be very tool-heavy on large repos;
            # keep per-call payloads conservative to reduce TPM impact.
            "github_repo_read": {
                "max_entries": 200,
                "max_file_chars": 8000,
            }
        }
        if "github_repo_read" in (template.allowed_tools or [])
        else None,
        resolved_execution_limits=None,
    )


def _build_github_repo_read_tool(
    *,
    registry: DefaultToolRegistry,
    run_context: RunContext,
) -> Any:
    """
    Build a `github_repo_read` function tool that routes through our existing runtime registry.

    This preserves tool policies/behavior and avoids any second GitHub integration path.
    """
    Agent, Runner, function_tool, RunContextWrapper, OpenAIResponsesModel = _import_agents_sdk()

    @function_tool(name_override="github_repo_read")
    def github_repo_read(  # type: ignore[no-redef]
        ctx: AgentsRunContextWrapper[Any],
        owner: str,
        repo: str,
        mode: str,
        ref: str | None = None,
        path: str | None = None,
        max_entries: int | None = None,
        max_file_chars: int | None = None,
    ) -> Dict[str, Any]:
        """Read-only GitHub repo inspection (overview/tree/file/sample)."""
        args: Dict[str, Any] = {"owner": owner, "repo": repo, "mode": mode}
        if ref is not None:
            args["ref"] = ref
        if path is not None:
            args["path"] = path
        if max_entries is not None:
            args["max_entries"] = max_entries
        if max_file_chars is not None:
            args["max_file_chars"] = max_file_chars
        return registry.execute("github_repo_read", args, run_context)

    return github_repo_read


SUPPORTED_OPENAI_TEMPLATES: set[str] = {
    REPO_SCOUT_TEMPLATE.id,
    REPO_ARCHITECT_TEMPLATE.id,
    AGENT_DESIGNER_TEMPLATE.id,
}


def _output_model_for_template_id(template_id: str) -> Type[Any]:
    if template_id == REPO_SCOUT_TEMPLATE.id:
        return RepoScoutOutput
    if template_id == REPO_ARCHITECT_TEMPLATE.id:
        return RepoArchitectureOutput
    if template_id == AGENT_DESIGNER_TEMPLATE.id:
        return AgentDraftOutput
    raise NotImplementedError(f"OpenAI runner does not support template_id={template_id!r}")


def build_openai_agent_from_template(
    template: AgentTemplate,
    client: Any,
    *,
    model_name: str | None = None,
) -> Any:
    """
    Build a real OpenAI Agents SDK Agent from an AgentTemplate.

    Supported: `repo_scout`, `repo_architect`, `agent_designer`.
    """
    if template.id not in SUPPORTED_OPENAI_TEMPLATES:
        raise NotImplementedError(f"OpenAI runner does not support template_id={template.id!r}")

    if model_name is None:
        model_name = os.environ.get("REPO_TO_AGENT_OPENAI_MODEL", DEFAULT_OPENAI_MODEL)

    Agent, Runner, function_tool, RunContextWrapper, OpenAIResponsesModel = _import_agents_sdk()

    preset = _template_to_preset(template)
    run_id = f"repo_to_agent_openai_{template.id}"
    run_context = build_run_context(run_id=run_id, preset=preset)
    registry = DefaultToolRegistry()

    tools: list[Any] = []
    if "github_repo_read" in (template.allowed_tools or []):
        tools.append(_build_github_repo_read_tool(registry=registry, run_context=run_context))

    model = OpenAIResponsesModel(model=model_name, openai_client=client)
    base_output_type = _output_model_for_template_id(template.id)

    # When available, wrap the Pydantic model in AgentOutputSchema with strict_json_schema disabled
    # so it can still be used as an output_type under the Agents SDK's strict mode.
    if AgentOutputSchema is not None:
        output_type = AgentOutputSchema(base_output_type, strict_json_schema=False)
    else:
        output_type = base_output_type

    return Agent(
        name=template.role or template.id,
        instructions=template.prompt,
        tools=tools,
        model=model,
        output_type=output_type,
    )


def _fill_tool_calls_from_result(result: Any, step_telemetry: Dict[str, Any]) -> None:
    """Set step_telemetry['tool_calls_count'] from SDK result when available."""
    steps = getattr(result, "steps", None)
    if steps is not None and isinstance(steps, (list, tuple)):
        count = sum(1 for s in steps if getattr(s, "type", None) == "tool_call" or getattr(s, "step_type", None) == "tool_call")
        if count > 0:
            step_telemetry["tool_calls_count"] = count
        return
    messages = getattr(result, "messages", None)
    if messages is not None and isinstance(messages, (list, tuple)):
        count = sum(1 for m in messages if getattr(m, "type", None) == "tool_call" or getattr(getattr(m, "message", m), "type", None) == "tool_call")
        if count > 0:
            step_telemetry["tool_calls_count"] = count


def run_specialist_with_openai_agent(
    template: AgentTemplate,
    input_payload: Dict[str, Any],
    client: Any,
    step_telemetry: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Execute a single specialist agent via the OpenAI Agents SDK.

    - Supports `repo_scout`, `repo_architect`, and `agent_designer`.
    - Exposes `github_repo_read` as a function tool routed through DefaultToolRegistry.
    - Returns a plain dict matching the template's output shape.

    Validation against the full Pydantic model still happens in the workflow layer.

    TODO: Add agent_designer / agent_reviewer support.
    """
    if template.id not in SUPPORTED_OPENAI_TEMPLATES:
        raise NotImplementedError(f"OpenAI runner does not support template_id={template.id!r}")

    if step_telemetry is not None:
        step_telemetry["backend_used"] = "openai"

    Agent, Runner, function_tool, RunContextWrapper, OpenAIResponsesModel = _import_agents_sdk()

    agent = build_openai_agent_from_template(template, client)
    output_type = _output_model_for_template_id(template.id)
    prompt = (
        f"Run the {template.id} specialist.\n\n"
        "Input JSON:\n"
        f"{json.dumps(input_payload, indent=2, sort_keys=True)}\n\n"
        f"Return ONLY a JSON object matching the {output_type.__name__} schema."
    )
    max_turns = int(os.environ.get("REPO_TO_AGENT_MAX_TURNS", REPO_TO_AGENT_MAX_TURNS))
    result = Runner.run_sync(agent, prompt, max_turns=max_turns)

    if step_telemetry is not None:
        _fill_tool_calls_from_result(result, step_telemetry)

    final_out = getattr(result, "final_output", None)

    if isinstance(final_out, output_type):
        return final_out.model_dump()
    if isinstance(final_out, dict):
        return final_out
    if isinstance(final_out, str):
        try:
            parsed = json.loads(final_out)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"OpenAI Agents SDK returned non-JSON final_output string for template_id={template.id!r}"
            ) from exc
        if not isinstance(parsed, dict):
            raise ValueError(
                f"OpenAI Agents SDK returned JSON that is not an object for template_id={template.id!r}"
            )
        return parsed

    raise TypeError(
        f"OpenAI Agents SDK final_output must be a dict, JSON string, or {output_type.__name__} "
        f"(template_id={template.id!r})"
    )

