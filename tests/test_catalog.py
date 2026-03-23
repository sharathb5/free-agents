"""
Part 5 catalog tests: loader validation, resolution precedence/dedup, normalize rejects unknown tools, recommendation keywords.
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from app.catalog.loader import load_bundles_catalog, load_tools_catalog, validate_catalogs
from app.catalog.recommendation import recommend_bundle
from app.catalog.resolution import MAX_EXTRA_TOOLS, ResolutionError, resolve_effective_tools, resolve_spec_tools
from app.storage.registry_store import AgentSpecInvalid, _normalize_spec


def _minimal_tools_catalog() -> Dict[str, Any]:
    return {
        "tools": [
            {
                "tool_id": "http_request",
                "category": "Web & Research",
                "description": "HTTP request",
                "safety_level": "network-read",
                "input_schema_ref": "built-in",
                "default_policy": {"http_timeout_seconds": 15, "http_max_response_chars": 50000},
            },
            {
                "tool_id": "github_repo_read",
                "category": "GitHub",
                "description": "Read repo",
                "safety_level": "oauth-read",
                "input_schema_ref": "built-in",
                "default_policy": {},
            },
        ]
    }


def _minimal_bundles_catalog() -> Dict[str, Any]:
    return {
        "bundles": [
            {
                "bundle_id": "research_basic",
                "title": "Research Basic",
                "description": "Web research",
                "category": "research",
                "tools": ["http_request"],
                "execution_limits": {"max_tool_calls": 3},
                "policy_overrides": {"http_request": {"http_timeout_seconds": 10}},
            },
            {
                "bundle_id": "no_tools_writer",
                "title": "Writer (No Tools)",
                "description": "No tools",
                "category": "writing",
                "tools": [],
                "policy_overrides": {},
            },
        ]
    }


def test_catalog_loader_validates_bundles_and_tools() -> None:
    """Load tools and bundles; assert bundle tool_ids exist in tools catalog; assert categories and policy structures."""
    tools_catalog = load_tools_catalog()
    bundles_catalog = load_bundles_catalog()
    validate_catalogs(tools_catalog, bundles_catalog)
    tool_ids = {t["tool_id"] for t in tools_catalog["tools"] if isinstance(t, dict) and t.get("tool_id")}
    assert "http_request" in tool_ids
    assert "github_repo_read" in tool_ids
    bundle_ids = {b["bundle_id"] for b in bundles_catalog["bundles"] if isinstance(b, dict) and b.get("bundle_id")}
    assert "research_basic" in bundle_ids
    assert "no_tools_writer" in bundle_ids
    assert "github_reader" in bundle_ids
    assert "data_analysis" in bundle_ids
    for b in bundles_catalog["bundles"]:
        if not isinstance(b, dict):
            continue
        assert isinstance(b.get("category"), str), f"bundle {b.get('bundle_id')} must have string category"
        for tid in b.get("tools") or []:
            assert tid in tool_ids, f"bundle references unknown tool_id: {tid}"


def test_resolution_merges_policies_in_correct_precedence() -> None:
    """Catalog default -> bundle override -> agent override; tool-specific only."""
    tools = _minimal_tools_catalog()
    bundles = _minimal_bundles_catalog()
    spec = {
        "bundle_id": "research_basic",
        "additional_tools": [],
        "tool_policies": {"http_request": {"http_timeout_seconds": 5}},
    }
    result = resolve_effective_tools(spec, tools, bundles)
    assert result["resolved_tool_policies"]["http_request"]["http_timeout_seconds"] == 5
    assert result["resolved_execution_limits"]["max_tool_calls"] == 3
    assert result["resolved_bundle_id"] == "research_basic"
    assert result["resolved_allowed_tools"] == ["http_request"]


def test_resolution_agent_execution_limits_override_bundle() -> None:
    """Agent execution_limits override bundle; merge order: settings -> bundle -> agent."""
    tools = _minimal_tools_catalog()
    bundles = _minimal_bundles_catalog()
    spec = {
        "bundle_id": "research_basic",
        "additional_tools": [],
        "execution_limits": {"max_tool_calls": 2},
    }
    result = resolve_effective_tools(spec, tools, bundles)
    assert result["resolved_execution_limits"]["max_tool_calls"] == 2


def test_resolve_spec_tools_matches_normalize_spec() -> None:
    """Preview resolution (resolve_spec_tools) and persistence (_normalize_spec) use same path."""
    base = {
        "id": "test_agent",
        "version": "1",
        "name": "Test",
        "description": "Test",
        "primitive": "transform",
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {}},
        "prompt": "Hello.",
    }
    spec = {
        **base,
        "bundle_id": "research_basic",
        "additional_tools": ["github_repo_read"],
        "tool_policies": {"http_request": {"http_timeout_seconds": 5}},
        "execution_limits": {"max_tool_calls": 2},
    }
    resolved, _ = resolve_spec_tools(spec)
    normalized = _normalize_spec(spec)
    assert normalized["allowed_tools"] == resolved["resolved_allowed_tools"]
    assert normalized["tool_policies"] == resolved["resolved_tool_policies"]
    assert normalized["resolved_execution_limits"] == resolved["resolved_execution_limits"]


def test_resolution_bundle_plus_additional_tools_dedupes_tools() -> None:
    """Bundle + additional_tools; resolved list sorted and deduped; MAX_EXTRA_TOOLS enforced."""
    tools = _minimal_tools_catalog()
    bundles = _minimal_bundles_catalog()
    spec = {
        "bundle_id": "research_basic",
        "additional_tools": ["github_repo_read"],
    }
    result = resolve_effective_tools(spec, tools, bundles)
    assert sorted(result["resolved_allowed_tools"]) == ["github_repo_read", "http_request"]
    spec2 = {"bundle_id": "research_basic", "additional_tools": ["http_request"]}
    result2 = resolve_effective_tools(spec2, tools, bundles)
    assert result2["resolved_allowed_tools"] == ["http_request"]
    too_many = ["github_repo_read"] * (MAX_EXTRA_TOOLS + 1)
    with pytest.raises(ResolutionError, match="must not exceed"):
        resolve_effective_tools({"bundle_id": "no_tools_writer", "additional_tools": too_many}, tools, bundles)


def test_normalize_spec_rejects_unknown_tool_ids() -> None:
    """Spec with allowed_tools or additional_tools containing unknown tool_id raises AgentSpecInvalid (400)."""
    base = {
        "id": "test_agent",
        "version": "1",
        "name": "Test",
        "description": "Test",
        "primitive": "transform",
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {}},
        "prompt": "Hello.",
    }
    with pytest.raises(AgentSpecInvalid, match="unknown|not in"):
        _normalize_spec({**base, "allowed_tools": ["unknown_tool"]})
    with pytest.raises(AgentSpecInvalid, match="unknown|additional_tools|exceed"):
        _normalize_spec({**base, "bundle_id": "no_tools_writer", "additional_tools": ["unknown_tool"]})
    from app.catalog.resolution import MAX_EXTRA_TOOLS
    with pytest.raises(AgentSpecInvalid):
        _normalize_spec({
            **base,
            "bundle_id": "no_tools_writer",
            "additional_tools": ["http_request"] * (MAX_EXTRA_TOOLS + 1),
        })


def test_recommendation_keywords_map_to_expected_bundle() -> None:
    """Keyword heuristic maps research -> research_basic, write/draft -> no_tools_writer, github -> github_reader."""
    r = recommend_bundle("I need to research articles on the web")
    assert r["bundle_id"] == "research_basic"
    assert 0 <= r["confidence"] <= 1
    assert r["rationale"]
    r2 = recommend_bundle("write email draft")
    assert r2["bundle_id"] == "no_tools_writer"
    r3 = recommend_bundle("read github repo")
    assert r3["bundle_id"] == "github_reader"
    assert "suggested_additional_tools" in r3


def test_catalog_tools_and_bundles_include_real_github_tool() -> None:
    """github_repo_read is a real catalog tool with default_policy; github_reader bundle includes it; recommendation maps to it."""
    tools_catalog = load_tools_catalog()
    bundles_catalog = load_bundles_catalog()
    validate_catalogs(tools_catalog, bundles_catalog)

    tool_ids = [t["tool_id"] for t in tools_catalog["tools"] if isinstance(t, dict) and t.get("tool_id")]
    assert "github_repo_read" in tool_ids, "catalog must include github_repo_read"

    github_tool = next(t for t in tools_catalog["tools"] if isinstance(t, dict) and t.get("tool_id") == "github_repo_read")
    assert github_tool.get("category") == "GitHub"
    assert github_tool.get("safety_level") == "oauth-read"
    default_policy = github_tool.get("default_policy")
    assert isinstance(default_policy, dict), "github_repo_read must have default_policy"
    assert default_policy.get("max_entries") == 50
    assert default_policy.get("max_file_chars") == 12000
    assert default_policy.get("max_sample_files") == 5

    bundle_ids = [b["bundle_id"] for b in bundles_catalog["bundles"] if isinstance(b, dict) and b.get("bundle_id")]
    assert "github_reader" in bundle_ids, "catalog must include github_reader bundle"

    github_reader_bundle = next(b for b in bundles_catalog["bundles"] if isinstance(b, dict) and b.get("bundle_id") == "github_reader")
    assert "github_repo_read" in (github_reader_bundle.get("tools") or []), "github_reader bundle must include github_repo_read"

    for keyword_phrase in ("github", "repo", "codebase"):
        rec = recommend_bundle(f"agent that uses {keyword_phrase}")
        assert rec["bundle_id"] == "github_reader", f"recommendation for '{keyword_phrase}' should map to github_reader"


# --- API tests (catalog router) ---

@pytest.fixture
def app():
    from app.main import app as fastapi_app  # type: ignore
    return fastapi_app


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient
    return TestClient(app)


def test_get_catalog_tools_returns_categories(client) -> None:
    """GET /catalog/tools returns 200 with categories and tools."""
    resp = client.get("/catalog/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert "categories" in data
    assert isinstance(data["categories"], list)
    assert any(c.get("name") and c.get("tools") for c in data["categories"])


def test_get_catalog_tools_stable_ordering(client) -> None:
    """GET /catalog/tools returns categories and tools in deterministic order."""
    resp1 = client.get("/catalog/tools")
    resp2 = client.get("/catalog/tools")
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    data1 = resp1.json()
    data2 = resp2.json()
    assert data1["categories"] == data2["categories"]
    for cat in data1["categories"]:
        tools = cat.get("tools") or []
        tool_ids = [t.get("tool_id") for t in tools]
        assert tool_ids == sorted(tool_ids), f"Tools in category {cat.get('name')} must be sorted by tool_id"


def test_post_catalog_recommend_returns_bundle(client) -> None:
    """POST /catalog/recommend returns bundle_id and rationale; confidence is server-log only."""
    resp = client.post("/catalog/recommend", json={"agent_idea": "Research web articles"})
    assert resp.status_code == 200
    data = resp.json()
    assert "bundle_id" in data
    assert "confidence" not in data
    assert "rationale" in data
    assert "suggested_additional_tools" in data
    assert data["bundle_id"] == "research_basic"
