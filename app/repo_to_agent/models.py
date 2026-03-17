from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .repo_tool_discovery import DiscoveredRepoTool


class WrappedRepoTool(BaseModel):
    """
    Structured executable tool definition produced by wrapping a discovered repo tool.
    Deterministic, rule-based only. Used to surface tools to the user and optionally
    expose low-risk ones to the agent runtime.
    """

    name: str
    tool_type: str  # e.g. "script" | "make_target" | "python_script" | "code_tool" | "mcp_code_tool" | "http_route" | ...
    command: Optional[str] = None
    description: Optional[str] = None
    source_path: str = ""
    wrapper_kind: str  # "command" | "http_api_spec" | "mcp_server_reference" | "code_reference"
    args_schema: Dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}, "additionalProperties": False})
    safe_to_auto_expose: bool = False
    risk_level: str = "medium"  # "low" | "medium" | "high"
    confidence: float = 1.0


class RepoScoutOutput(BaseModel):
    """High-level repo scouting summary based on lightweight inspection."""

    repo_summary: str
    important_files: List[str] = Field(default_factory=list)
    language_hints: List[str] = Field(default_factory=list)
    framework_hints: List[str] = Field(default_factory=list)


class RepoArchitectureOutput(BaseModel):
    """Structured view of the repo's architecture and surface area."""

    languages: List[str] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    services: List[str] = Field(default_factory=list)
    entrypoints: List[str] = Field(default_factory=list)
    integrations: List[str] = Field(default_factory=list)
    key_paths: List[str] = Field(default_factory=list)


class AgentDraftOutput(BaseModel):
    """Draft agent design derived from repo analysis."""

    recommended_bundle: str
    recommended_additional_tools: List[str] = Field(default_factory=list)
    draft_agent_spec: Dict[str, Any] = Field(default_factory=dict)
    starter_eval_cases: List[Dict[str, Any]] = Field(default_factory=list)


class AgentReviewOutput(BaseModel):
    """Review and risk analysis for a proposed agent design."""

    review_notes: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)


class StepTelemetry(BaseModel):
    """Per-step execution telemetry for repo-to-agent runs."""

    step_name: str = ""
    backend_used: str = "internal"  # "openai" | "internal"
    fallback_triggered: bool = False
    tool_calls_count: Optional[int] = None
    duration_ms: int = 0


class RunTelemetry(BaseModel):
    """Aggregate telemetry for a full repo-to-agent run."""

    steps: List[StepTelemetry] = Field(default_factory=list)
    repo_size_hint: Dict[str, Any] = Field(default_factory=dict)
    total_duration_ms: int = 0


class RepoToAgentResult(BaseModel):
    """
    Aggregated result of repo-to-agent analysis, suitable for persistence
    and user-facing review/edit flows.
    """

    repo_summary: str
    architecture: RepoArchitectureOutput
    important_files: List[str] = Field(default_factory=list)
    recommended_bundle: str
    recommended_additional_tools: List[str] = Field(default_factory=list)
    draft_agent_spec: Dict[str, Any] = Field(default_factory=dict)
    starter_eval_cases: List[Dict[str, Any]] = Field(default_factory=list)
    review_notes: List[str] = Field(default_factory=list)
    discovered_repo_tools: List[DiscoveredRepoTool] = Field(default_factory=list)
    wrapped_repo_tools: List[WrappedRepoTool] = Field(default_factory=list)
    # Optional split for reporting: manifest/file-based vs code-defined (before merge).
    discovered_manifest_tools: List[DiscoveredRepoTool] = Field(default_factory=list)
    discovered_code_tools: List[DiscoveredRepoTool] = Field(default_factory=list)
    telemetry: Optional[RunTelemetry] = None

