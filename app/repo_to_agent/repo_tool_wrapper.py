"""
Automatic wrapping of discovered repo tools into structured executable tool definitions.

Deterministic, rule-based only. No LLM. No execution. Produces WrappedRepoTool metadata
for the platform to surface to the user and optionally expose to the agent runtime.
"""

from __future__ import annotations

import re
from typing import List

from .models import WrappedRepoTool
from .repo_tool_discovery import DiscoveredRepoTool

# Risk classification: substrings in name/command/source_path (lowercased) that imply risk level.
HIGH_RISK_PATTERNS = (
    "deploy", "publish", "release", "terraform apply", "kubectl", "helm",
    "docker push", "prod", "production", "aws", "gcloud", "stripe", "supabase db push",
)
MEDIUM_RISK_PATTERNS = (
    "format", "migrate", "seed", "codegen", "start",
)
LOW_RISK_PATTERNS = (
    "test", "lint", "check", "fmt --check", "docs", "build",
)

# Wrapper kinds we recognize in validation.
RECOGNIZED_WRAPPER_KINDS = frozenset(
    ("command", "http_api_spec", "mcp_server_reference", "code_reference")
)

DEFAULT_ARGS_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}
# For code-defined tools: allow arbitrary args until schema is known.
CODE_REFERENCE_ARGS_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": True}


def classify_tool_risk(discovered_tool: DiscoveredRepoTool) -> str:
    """
    Classify risk level of a discovered tool from name, command, and source path.
    Returns "low", "medium", or "high".
    """
    name = (discovered_tool.name or "").strip().lower()
    command = (discovered_tool.command or "").strip().lower()
    source_path = (discovered_tool.source_path or "").strip().lower()
    combined = " ".join([name, command, source_path])

    for pattern in HIGH_RISK_PATTERNS:
        if pattern in combined:
            return "high"
    for pattern in MEDIUM_RISK_PATTERNS:
        if pattern in combined:
            return "medium"
    for pattern in LOW_RISK_PATTERNS:
        if pattern in combined:
            return "low"

    # Build without deploy/publish signals: treat as low risk
    if "build" in combined and not any(p in combined for p in ("deploy", "publish", "release")):
        return "low"

    # Default conservative
    return "medium"


def is_safe_to_auto_expose(discovered_tool: DiscoveredRepoTool) -> bool:
    """
    True only for low-risk tools. Medium/high risk must be surfaced but not auto-enabled.
    MCP, deploy, publish, migration, container orchestration, remote mutation are never safe.
    """
    risk = classify_tool_risk(discovered_tool)
    if risk != "low":
        return False
    # Extra guard: never auto-expose MCP or container commands
    tool_type = (discovered_tool.tool_type or "").strip().lower()
    if tool_type == "mcp_server":
        return False
    name = (discovered_tool.name or "").strip().lower()
    command = (discovered_tool.command or "").strip().lower()
    if "mcp" in name or "mcp" in command or "docker" in command or "compose" in command:
        return False
    return True


def wrap_discovered_tools(discovered_tools: List[DiscoveredRepoTool]) -> List[WrappedRepoTool]:
    """
    Convert discovered repo tools into structured wrapped tools (metadata only; no execution).
    """
    out: List[WrappedRepoTool] = []
    for t in discovered_tools:
        # Capabilities / likely_tools are *signals* from agent.json, not executable tools.
        # Keeping them out of wrapped_repo_tools makes the "Promoted repo tool metadata"
        # panel represent actually-wrapped (actionable) tools rather than duplicating
        # the raw extracted list.
        tool_type_raw = (t.tool_type or "").strip().lower()
        if tool_type_raw in {"capability", "likely_tool"}:
            continue

        risk = classify_tool_risk(t)
        safe = is_safe_to_auto_expose(t)

        tool_type = tool_type_raw
        name = (t.name or "").strip() or "unknown"
        command = (t.command or "").strip() or None
        description = (t.description or "").strip() or None
        source_path = (t.source_path or "").strip()
        confidence = float(t.confidence) if t.confidence is not None else 1.0

        if tool_type == "cli":
            out.append(
                WrappedRepoTool(
                    name=name,
                    tool_type="script",
                    command=command or name,
                    description=description,
                    source_path=source_path,
                    wrapper_kind="command",
                    args_schema=DEFAULT_ARGS_SCHEMA,
                    safe_to_auto_expose=safe,
                    risk_level=risk,
                    confidence=confidence,
                )
            )
        elif tool_type == "script":
            # npm scripts and folder scripts
            out.append(
                WrappedRepoTool(
                    name=name,
                    tool_type="script",
                    command=command,
                    description=description,
                    source_path=source_path,
                    wrapper_kind="command",
                    args_schema=DEFAULT_ARGS_SCHEMA,
                    safe_to_auto_expose=safe,
                    risk_level=risk,
                    confidence=confidence,
                )
            )
        elif tool_type == "make_target":
            out.append(
                WrappedRepoTool(
                    name=name,
                    tool_type="make_target",
                    command=command or f"make {name}",
                    description=description,
                    source_path=source_path,
                    wrapper_kind="command",
                    args_schema=DEFAULT_ARGS_SCHEMA,
                    safe_to_auto_expose=safe,
                    risk_level=risk,
                    confidence=confidence,
                )
            )
        elif tool_type == "python_script":
            out.append(
                WrappedRepoTool(
                    name=name,
                    tool_type="python_script",
                    command=command or f"python {source_path}" if source_path else None,
                    description=description,
                    source_path=source_path,
                    wrapper_kind="command",
                    args_schema=DEFAULT_ARGS_SCHEMA,
                    safe_to_auto_expose=safe,
                    risk_level=risk,
                    confidence=confidence,
                )
            )
        elif tool_type == "container_command":
            out.append(
                WrappedRepoTool(
                    name=name,
                    tool_type="container_command",
                    command=command,
                    description=description,
                    source_path=source_path,
                    wrapper_kind="command",
                    args_schema=DEFAULT_ARGS_SCHEMA,
                    safe_to_auto_expose=False,
                    risk_level=risk,
                    confidence=confidence,
                )
            )
        elif tool_type == "http_api":
            out.append(
                WrappedRepoTool(
                    name=name,
                    tool_type="http_api",
                    command=command or "HTTP API from OpenAPI spec",
                    description=description,
                    source_path=source_path,
                    wrapper_kind="http_api_spec",
                    args_schema=DEFAULT_ARGS_SCHEMA,
                    safe_to_auto_expose=False,
                    risk_level=risk,
                    confidence=confidence,
                )
            )
        elif tool_type == "mcp_server":
            out.append(
                WrappedRepoTool(
                    name=name,
                    tool_type="mcp_server",
                    command=command,
                    description=description,
                    source_path=source_path,
                    wrapper_kind="mcp_server_reference",
                    args_schema=DEFAULT_ARGS_SCHEMA,
                    safe_to_auto_expose=False,
                    risk_level=risk,
                    confidence=confidence,
                )
            )
        elif tool_type == "code_tool":
            # Code-defined tools: default medium risk (no execution; conservative).
            out.append(
                WrappedRepoTool(
                    name=name,
                    tool_type="code_tool",
                    command=None,
                    description=description,
                    source_path=source_path,
                    wrapper_kind="code_reference",
                    args_schema=CODE_REFERENCE_ARGS_SCHEMA,
                    safe_to_auto_expose=False,
                    risk_level="medium",
                    confidence=confidence,
                )
            )
        elif tool_type == "mcp_code_tool":
            out.append(
                WrappedRepoTool(
                    name=name,
                    tool_type="mcp_code_tool",
                    command=None,
                    description=description,
                    source_path=source_path,
                    wrapper_kind="mcp_server_reference",
                    args_schema=CODE_REFERENCE_ARGS_SCHEMA,
                    safe_to_auto_expose=False,
                    risk_level=risk if risk else "medium",
                    confidence=confidence,
                )
            )
        elif tool_type == "http_route":
            out.append(
                WrappedRepoTool(
                    name=name,
                    tool_type="http_route",
                    command=None,
                    description=description,
                    source_path=source_path,
                    wrapper_kind="code_reference",
                    args_schema=CODE_REFERENCE_ARGS_SCHEMA,
                    safe_to_auto_expose=False,
                    risk_level=risk if risk else "medium",
                    confidence=confidence,
                )
            )
        else:
            # Unknown type: wrap as command with conservative risk
            out.append(
                WrappedRepoTool(
                    name=name,
                    tool_type=tool_type or "script",
                    command=command,
                    description=description,
                    source_path=source_path,
                    wrapper_kind="command",
                    args_schema=DEFAULT_ARGS_SCHEMA,
                    safe_to_auto_expose=False,
                    risk_level=risk,
                    confidence=confidence,
                )
            )
    return out
