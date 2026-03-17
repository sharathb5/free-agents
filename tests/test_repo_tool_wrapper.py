"""Tests for repo_tool_wrapper: wrapping, risk classification, safe_to_auto_expose."""

from __future__ import annotations

import pytest

from app.repo_to_agent.models import WrappedRepoTool
from app.repo_to_agent.repo_tool_discovery import DiscoveredRepoTool
from app.repo_to_agent.repo_tool_wrapper import (
    RECOGNIZED_WRAPPER_KINDS,
    classify_tool_risk,
    is_safe_to_auto_expose,
    wrap_discovered_tools,
)


def test_wrap_cli_tool() -> None:
    discovered = DiscoveredRepoTool(
        name="mycli",
        tool_type="cli",
        command="mycli",
        description="CLI from pyproject",
        source_path="pyproject.toml",
        confidence=0.9,
    )
    wrapped = wrap_discovered_tools([discovered])
    assert len(wrapped) == 1
    assert wrapped[0].name == "mycli"
    assert wrapped[0].tool_type == "script"
    assert wrapped[0].command == "mycli"
    assert wrapped[0].wrapper_kind == "command"
    assert wrapped[0].args_schema == {"type": "object", "properties": {}, "additionalProperties": False}
    assert wrapped[0].source_path == "pyproject.toml"


def test_wrap_npm_script() -> None:
    discovered = DiscoveredRepoTool(
        name="test",
        tool_type="script",
        command="npm run test",
        description="npm script",
        source_path="package.json",
        confidence=0.9,
    )
    wrapped = wrap_discovered_tools([discovered])
    assert len(wrapped) == 1
    assert wrapped[0].name == "test"
    assert wrapped[0].command == "npm run test"
    assert wrapped[0].wrapper_kind == "command"
    assert wrapped[0].risk_level == "low"
    assert wrapped[0].safe_to_auto_expose is True


def test_wrap_openapi_tool() -> None:
    discovered = DiscoveredRepoTool(
        name="openapi_api",
        tool_type="http_api",
        command="HTTP API from OpenAPI spec",
        description="OpenAPI spec",
        source_path="openapi.yaml",
        confidence=0.95,
    )
    wrapped = wrap_discovered_tools([discovered])
    assert len(wrapped) == 1
    assert wrapped[0].wrapper_kind == "http_api_spec"
    assert wrapped[0].safe_to_auto_expose is False


def test_wrap_mcp_tool() -> None:
    discovered = DiscoveredRepoTool(
        name="mcp_server",
        tool_type="mcp_server",
        command=None,
        description="MCP config",
        source_path="mcp.json",
        confidence=0.9,
    )
    wrapped = wrap_discovered_tools([discovered])
    assert len(wrapped) == 1
    assert wrapped[0].wrapper_kind == "mcp_server_reference"
    assert wrapped[0].safe_to_auto_expose is False


def test_wrap_code_tool() -> None:
    discovered = DiscoveredRepoTool(
        name="search_docs",
        tool_type="code_tool",
        command=None,
        description="Code-defined tool",
        source_path="tools.py",
        confidence=0.9,
    )
    wrapped = wrap_discovered_tools([discovered])
    assert len(wrapped) == 1
    assert wrapped[0].name == "search_docs"
    assert wrapped[0].wrapper_kind == "code_reference"
    assert wrapped[0].command is None
    assert wrapped[0].safe_to_auto_expose is False
    assert wrapped[0].risk_level == "medium"
    assert wrapped[0].args_schema.get("additionalProperties") is True


def test_wrap_mcp_code_tool() -> None:
    discovered = DiscoveredRepoTool(
        name="mcp_server_code_tools",
        tool_type="mcp_code_tool",
        command=None,
        description="MCP tool registration in code",
        source_path="server.py",
        confidence=0.7,
    )
    wrapped = wrap_discovered_tools([discovered])
    assert len(wrapped) == 1
    assert wrapped[0].wrapper_kind == "mcp_server_reference"
    assert wrapped[0].safe_to_auto_expose is False


def test_wrap_make_target() -> None:
    discovered = DiscoveredRepoTool(
        name="build",
        tool_type="make_target",
        command="make build",
        description="Makefile target",
        source_path="Makefile",
        confidence=0.85,
    )
    wrapped = wrap_discovered_tools([discovered])
    assert len(wrapped) == 1
    assert wrapped[0].tool_type == "make_target"
    assert wrapped[0].command == "make build"
    assert wrapped[0].wrapper_kind == "command"


def test_wrap_python_script() -> None:
    discovered = DiscoveredRepoTool(
        name="run_script",
        tool_type="python_script",
        command="python scripts/run_script.py",
        description="Python script",
        source_path="scripts/run_script.py",
        confidence=0.9,
    )
    wrapped = wrap_discovered_tools([discovered])
    assert len(wrapped) == 1
    assert wrapped[0].tool_type == "python_script"
    assert wrapped[0].wrapper_kind == "command"


def test_wrap_container_command() -> None:
    discovered = DiscoveredRepoTool(
        name="docker_build",
        tool_type="container_command",
        command="docker build",
        description="Dockerfile",
        source_path="Dockerfile",
        confidence=0.9,
    )
    wrapped = wrap_discovered_tools([discovered])
    assert len(wrapped) == 1
    assert wrapped[0].safe_to_auto_expose is False


def test_classify_tool_risk_low() -> None:
    for name in ("test", "lint", "check", "docs", "build"):
        t = DiscoveredRepoTool(name=name, tool_type="script", command=f"npm run {name}", source_path="package.json")
        assert classify_tool_risk(t) == "low"


def test_classify_tool_risk_medium() -> None:
    for name in ("format", "migrate", "seed", "codegen", "start"):
        t = DiscoveredRepoTool(name=name, tool_type="script", command=f"npm run {name}", source_path="package.json")
        assert classify_tool_risk(t) == "medium"


def test_classify_tool_risk_high() -> None:
    for name in ("deploy", "publish", "release"):
        t = DiscoveredRepoTool(name=name, tool_type="script", command=f"npm run {name}", source_path="package.json")
        assert classify_tool_risk(t) == "high"
    t = DiscoveredRepoTool(name="push", tool_type="script", command="docker push", source_path=".")
    assert classify_tool_risk(t) == "high"
    t = DiscoveredRepoTool(name="prod", tool_type="script", command="run prod", source_path="scripts/prod.sh")
    assert classify_tool_risk(t) == "high"


def test_is_safe_to_auto_expose_low_risk_only() -> None:
    low = DiscoveredRepoTool(name="test", tool_type="script", command="npm run test", source_path="package.json")
    assert is_safe_to_auto_expose(low) is True
    high = DiscoveredRepoTool(name="deploy", tool_type="script", command="npm run deploy", source_path="package.json")
    assert is_safe_to_auto_expose(high) is False
    mcp = DiscoveredRepoTool(name="mcp_server", tool_type="mcp_server", source_path="mcp.json")
    assert is_safe_to_auto_expose(mcp) is False


def test_result_schema_serialization() -> None:
    """WrappedRepoTool and list serialize to dict/JSON-friendly shape."""
    w = WrappedRepoTool(
        name="test",
        tool_type="script",
        command="npm run test",
        description="Run tests",
        source_path="package.json",
        wrapper_kind="command",
        args_schema={"type": "object", "properties": {}, "additionalProperties": False},
        safe_to_auto_expose=True,
        risk_level="low",
        confidence=0.92,
    )
    d = w.model_dump()
    assert d["name"] == "test"
    assert d["risk_level"] == "low"
    assert d["safe_to_auto_expose"] is True
    assert "args_schema" in d


def test_recognized_wrapper_kinds() -> None:
    assert "command" in RECOGNIZED_WRAPPER_KINDS
    assert "http_api_spec" in RECOGNIZED_WRAPPER_KINDS
    assert "mcp_server_reference" in RECOGNIZED_WRAPPER_KINDS
    assert "code_reference" in RECOGNIZED_WRAPPER_KINDS


def test_wrap_empty_list() -> None:
    assert wrap_discovered_tools([]) == []


def test_wrap_multiple_mixed() -> None:
    discovered = [
        DiscoveredRepoTool(name="test", tool_type="script", command="npm run test", source_path="package.json"),
        DiscoveredRepoTool(name="deploy", tool_type="script", command="npm run deploy", source_path="package.json"),
    ]
    wrapped = wrap_discovered_tools(discovered)
    assert len(wrapped) == 2
    by_name = {w.name: w for w in wrapped}
    assert by_name["test"].safe_to_auto_expose is True
    assert by_name["deploy"].safe_to_auto_expose is False
    assert by_name["deploy"].risk_level == "high"
