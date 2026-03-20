from __future__ import annotations

from typing import Any, Dict, List

from fastapi.testclient import TestClient

from app.main import app as fastapi_app
from app.recommendations.tool_recommender import (
    CatalogBundle,
    CatalogTool,
    RecommendationInput,
    recommend_tools_for_agent,
)


def _catalog_tool(tool_id: str, category: str, description: str) -> CatalogTool:
    return CatalogTool(tool_id=tool_id, category=category, description=description)


def _filesystem_bundle(tools: List[str]) -> CatalogBundle:
    return CatalogBundle(
        bundle_id="filesystem_search",
        title="Filesystem & Search",
        description="Tools for file access and repo search.",
        category="Filesystem",
        tools=tools,
    )


def _github_bundle(tools: List[str]) -> CatalogBundle:
    return CatalogBundle(
        bundle_id="github_automation",
        title="GitHub Automation",
        description="Tools for GitHub releases, docs, and workflows.",
        category="GitHub",
        tools=tools,
    )


def _no_tools_bundle() -> CatalogBundle:
    return CatalogBundle(
        bundle_id="no_tools_writer",
        title="Writer (No Tools)",
        description="No tools attached.",
        category="writing",
        tools=[],
    )


def test_filesystem_search_agent_prefers_filesystem_bundle_and_tools() -> None:
    tools = [
        _catalog_tool("glob_search", "search_retrieval", "Search files by glob pattern."),
        _catalog_tool("grep_search", "search_retrieval", "Grep-like code search."),
        _catalog_tool("file_tool", "file_filesystem", "Read and write files."),
        _catalog_tool("shell_tool", "code_execution", "Run shell commands."),
        _catalog_tool("http_request", "Web & Research", "HTTP request tool."),
    ]
    bundles = [
        _filesystem_bundle(["glob_search", "grep_search", "file_tool", "shell_tool"]),
        _github_bundle(["github_repo_read"]),
        _no_tools_bundle(),
    ]
    agent = RecommendationInput(
        name="Repo helper",
        description="Agent that navigates code and searches files",
        primitive="chat",
        prompt="Use grep and file search to understand the repo.",
        extracted_tool_ids=[],
    )

    result = recommend_tools_for_agent(agent, tools, bundles)

    assert result.bundle_id == "filesystem_search"
    assert any(tid in result.additional_tool_ids for tid in ("glob_search", "grep_search", "file_tool", "shell_tool")) or result.additional_tool_ids == []
    assert any("filesystem" in r.lower() or "search" in r.lower() for r in result.rationale)
    assert result.debug is not None
    assert "file_search" in result.debug.inferred_capabilities
    assert result.debug.inferred_capabilities["file_search"].score > 0
    assert "file_operation" in result.debug.inferred_execution_types
    assert result.debug.inferred_execution_types["file_operation"].score > 0
    assert "file_search" in result.debug.detected_signals


def test_github_release_agent_prefers_github_bundle_and_tools() -> None:
    tools = [
        _catalog_tool("github_repo_read", "GitHub", "Read GitHub repos."),
        _catalog_tool("tag_release", "GitHub", "Tag a release."),
        _catalog_tool("generate_docs", "GitHub", "Generate docs from repo."),
    ]
    bundles = [
        _github_bundle(["github_repo_read", "tag_release"]),
        _no_tools_bundle(),
    ]
    agent = RecommendationInput(
        name="GitHub release manager",
        description="Manage GitHub releases and changelogs.",
        primitive="chat",
        prompt="Tag releases, update docs, and work with GitHub workflows.",
        extracted_tool_ids=["tag_release"],
    )

    result = recommend_tools_for_agent(agent, tools, bundles)

    assert result.bundle_id == "github_automation"
    assert "tag_release" in (result.additional_tool_ids + bundles[0].tools)
    assert any("github" in r.lower() or "release" in r.lower() for r in result.rationale)
    assert result.debug is not None
    assert result.debug.inferred_capabilities["release_workflow"].score > 0
    assert result.debug.inferred_execution_types["cli_command"].score > 0
    assert "release_workflow" in result.debug.detected_signals


def test_summarizer_transform_agent_avoids_heavy_bundles() -> None:
    tools = [
        _catalog_tool("http_request", "Web & Research", "HTTP request tool."),
        _catalog_tool("glob_search", "search_retrieval", "Search files by glob pattern."),
    ]
    bundles = [
        _filesystem_bundle(["glob_search"]),
        _no_tools_bundle(),
    ]
    agent = RecommendationInput(
        name="Report summarizer",
        description="Summarize long reports into short briefs.",
        primitive="transform",
        prompt="Summarize the provided text.",
        extracted_tool_ids=[],
    )

    result = recommend_tools_for_agent(agent, tools, bundles)

    assert result.bundle_id in (None, "no_tools_writer")
    assert len(result.additional_tool_ids) == 0 or all(
        tid in ("http_request", "glob_search") for tid in result.additional_tool_ids
    )
    assert any("summarize" in r.lower() or "transform" in r.lower() or "avoiding heavy" in r.lower() for r in result.rationale)
    assert result.debug is not None
    assert result.debug.inferred_capabilities["text_generation"].score > 0
    assert result.debug.inferred_execution_types["text_transform"].score > 0


def test_mcp_like_extracted_tools_are_preserved() -> None:
    tools = [
        _catalog_tool("mcp_fetch", "structured_data", "MCP fetch tool."),
        _catalog_tool("github_repo_read", "GitHub", "Read GitHub repos."),
    ]
    bundles = [
        _github_bundle(["github_repo_read"]),
        _no_tools_bundle(),
    ]
    agent = RecommendationInput(
        name="MCP integration agent",
        description="Integrates with a specific MCP server.",
        primitive="chat",
        prompt="Use the MCP server tools where appropriate.",
        extracted_tool_ids=["mcp_fetch"],
    )

    result = recommend_tools_for_agent(agent, tools, bundles)

    assert "mcp_fetch" in result.additional_tool_ids
    assert result.debug is not None
    assert result.debug.inferred_capabilities["mcp_tool"].score > 0
    assert result.debug.inferred_execution_types["mcp_tool"].score > 0


def test_no_match_fallback_behavior() -> None:
    tools: List[CatalogTool] = []
    bundles = [_no_tools_bundle()]
    agent = RecommendationInput(
        name="Generic agent",
        description="Does something unclear.",
        primitive="chat",
        prompt="Just talk to the user.",
        extracted_tool_ids=[],
    )

    result = recommend_tools_for_agent(agent, tools, bundles)

    assert result.bundle_id is None or result.bundle_id == "no_tools_writer"
    assert result.additional_tool_ids == []
    assert any("no bundle" in r.lower() or "conservative" in r.lower() for r in result.rationale)
    assert result.debug is not None
    # Low-signal agent should not produce strong capabilities/execution types.
    assert max(v.score for v in result.debug.inferred_capabilities.values()) == 0.0


def test_deterministic_output_for_same_input() -> None:
    tools = [
        _catalog_tool("glob_search", "search_retrieval", "Search files by glob pattern."),
        _catalog_tool("grep_search", "search_retrieval", "Grep-like code search."),
    ]
    bundles = [
        _filesystem_bundle(["glob_search", "grep_search"]),
        _no_tools_bundle(),
    ]
    agent = RecommendationInput(
        name="Deterministic agent",
        description="Searches code.",
        primitive="chat",
        prompt="Search code with grep.",
        extracted_tool_ids=[],
    )

    result1 = recommend_tools_for_agent(agent, tools, bundles)
    result2 = recommend_tools_for_agent(agent, tools, bundles)

    assert result1.bundle_id == result2.bundle_id
    assert result1.additional_tool_ids == result2.additional_tool_ids
    assert result1.rationale == result2.rationale


def test_post_catalog_recommend_tools_endpoint_basic() -> None:
    client = TestClient(fastapi_app)
    body: Dict[str, Any] = {
        "name": "Filesystem helper",
        "description": "Agent that searches files in a repo.",
        "primitive": "chat",
        "prompt": "Use file and search tools.",
        "repo_url": "https://github.com/example/repo",
        "extracted_tool_ids": [],
    }
    resp = client.post("/catalog/recommend-tools", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert "bundle_id" in data
    assert "additional_tool_ids" in data
    assert "rationale" in data
    assert isinstance(data["rationale"], list)
