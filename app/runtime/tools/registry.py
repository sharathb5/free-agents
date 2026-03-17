"""
Tool registry: execute tools with policy checks (allowed_tools, max_tool_calls, domain allowlist).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.config import get_settings
from app.preset_loader import Preset

from .github_client import DefaultGithubClient
from .github_tool import GithubRepoReadPolicy, execute_github_repo_read
from .http_tool import HttpPolicy, ToolExecutionError, execute_http_request

logger = logging.getLogger("agent-gateway")

# Default policy for github_repo_read (catalog defaults).
GITHUB_REPO_READ_DEFAULT_MAX_ENTRIES = 50
GITHUB_REPO_READ_DEFAULT_MAX_FILE_CHARS = 12_000
GITHUB_REPO_READ_DEFAULT_MAX_SAMPLE_FILES = 5


@dataclass
class RunContext:
    """Context for a single run: policy and tool-call counter."""

    run_id: str
    preset: Preset
    tools_enabled: bool
    max_tool_calls: int
    tool_calls_used: int = 0
    # Resolved allowed tools for this agent (e.g. ["http_request"])
    allowed_tools: List[str] = field(default_factory=list)
    # Resolved HTTP allowed domains for this agent
    http_allowed_domains: List[str] = field(default_factory=list)
    # Per-tool policies (Part 5), e.g. http_request -> { http_timeout_seconds, http_max_response_chars }
    tool_policies: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class DefaultToolRegistry:
    """
    Registry that executes http_request and enforces policy.
    execute() checks tools_enabled, allowed_tools, max_tool_calls, and domain allowlist.
    """

    def execute(self, tool_name: str, args: Dict[str, Any], run_context: RunContext) -> Dict[str, Any]:
        if not run_context.tools_enabled:
            raise ToolExecutionError("tools are not enabled")
        if tool_name not in run_context.allowed_tools:
            raise ToolExecutionError(f"tool not allowed: {tool_name}")
        if run_context.tool_calls_used >= run_context.max_tool_calls:
            raise ToolExecutionError("max_tool_calls_exceeded")

        if tool_name == "http_request":
            settings = get_settings()
            tool_policy = run_context.tool_policies.get("http_request") or {}
            timeout_seconds = tool_policy.get("http_timeout_seconds")
            if timeout_seconds is None:
                timeout_seconds = settings.http_timeout_seconds
            else:
                timeout_seconds = int(timeout_seconds)
            max_response_chars = tool_policy.get("http_max_response_chars")
            if max_response_chars is None:
                max_response_chars = settings.http_max_response_chars
            else:
                max_response_chars = int(max_response_chars)
            policy = HttpPolicy(
                timeout_seconds=timeout_seconds,
                max_response_chars=max_response_chars,
                allowed_domains=run_context.http_allowed_domains or list(settings.http_allowed_domains_default),
                allow_localhost=bool(  # allow in tests when default domains are empty or localhost listed
                    "localhost" in (run_context.http_allowed_domains or settings.http_allowed_domains_default)
                    or "127.0.0.1" in (run_context.http_allowed_domains or settings.http_allowed_domains_default)
                ),
            )
            return execute_http_request(args, policy)

        if tool_name == "github_repo_read":
            tool_policy = run_context.tool_policies.get("github_repo_read") or {}
            max_entries = tool_policy.get("max_entries")
            if max_entries is None:
                max_entries = GITHUB_REPO_READ_DEFAULT_MAX_ENTRIES
            else:
                max_entries = int(max_entries)
            max_file_chars = tool_policy.get("max_file_chars")
            if max_file_chars is None:
                max_file_chars = GITHUB_REPO_READ_DEFAULT_MAX_FILE_CHARS
            else:
                max_file_chars = int(max_file_chars)
            max_sample_files = tool_policy.get("max_sample_files")
            if max_sample_files is None:
                max_sample_files = GITHUB_REPO_READ_DEFAULT_MAX_SAMPLE_FILES
            else:
                max_sample_files = int(max_sample_files)
            allowed_owners = tool_policy.get("allowed_owners")
            if allowed_owners is not None and not isinstance(allowed_owners, list):
                allowed_owners = None
            allowed_repos = tool_policy.get("allowed_repos")
            if allowed_repos is not None and not isinstance(allowed_repos, list):
                allowed_repos = None
            include_hidden_files = bool(tool_policy.get("include_hidden_files", False))
            policy = GithubRepoReadPolicy(
                max_entries=max_entries,
                max_file_chars=max_file_chars,
                max_sample_files=max_sample_files,
                allow_private_repos=True,
                allowed_owners=allowed_owners,
                allowed_repos=allowed_repos,
                include_hidden_files=include_hidden_files,
            )
            github_client = DefaultGithubClient()
            return execute_github_repo_read(args, policy, github_client)

        raise ToolExecutionError(f"unknown tool: {tool_name}")


def build_run_context(
    run_id: str,
    preset: Preset,
    tools_enabled: Optional[bool] = None,
    max_tool_calls: Optional[int] = None,
) -> RunContext:
    """Build RunContext from preset and settings. Uses resolved_execution_limits when present."""
    settings = get_settings()
    tools_enabled = tools_enabled if tools_enabled is not None else settings.tools_enabled
    limits = getattr(preset, "resolved_execution_limits", None) or {}
    if max_tool_calls is not None:
        effective_max_tool_calls = max_tool_calls
    elif limits.get("max_tool_calls") is not None:
        effective_max_tool_calls = int(limits["max_tool_calls"])
    else:
        effective_max_tool_calls = settings.max_tool_calls
    allowed_tools = getattr(preset, "allowed_tools", None) or []
    http_allowed_domains = getattr(preset, "http_allowed_domains", None)
    if http_allowed_domains is None:
        http_allowed_domains = list(settings.http_allowed_domains_default)
    tool_policies = getattr(preset, "tool_policies", None) or {}
    return RunContext(
        run_id=run_id,
        preset=preset,
        tools_enabled=tools_enabled,
        max_tool_calls=effective_max_tool_calls,
        tool_calls_used=0,
        allowed_tools=list(allowed_tools),
        http_allowed_domains=list(http_allowed_domains),
        tool_policies=dict(tool_policies),
    )
