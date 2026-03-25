"""Tests for repo-based tool discovery (discover_tools_from_repo)."""

from __future__ import annotations

from typing import Any, Dict

from app.repo_to_agent.models import RepoArchitectureOutput, RepoScoutOutput
from app.repo_to_agent.tool_discovery import discover_tools_from_repo


def _max_execution_score(debug: Dict[str, Any]) -> float:
    exec_types = debug.get("inferred_execution_types") or {}
    scores = []
    for v in exec_types.values():
        if isinstance(v, dict):
            s = v.get("score")
            if isinstance(s, (int, float)):
                scores.append(float(s))
    return max(scores) if scores else 0.0


def test_discover_tools_github_release_prefers_repo_to_agent_or_github_reader() -> None:
    scout = {
        "repo_summary": "Changelog + release automation.",
        "important_files": [".github/workflows/release.yml", "CHANGELOG.md"],
        "language_hints": [],
        "framework_hints": [],
    }
    arch = {
        "languages": [],
        "frameworks": [],
        "services": [],
        "entrypoints": [],
        "integrations": [],
        "key_paths": [".github/workflows/release.yml", "CHANGELOG.md"],
    }
    out = discover_tools_from_repo(scout, arch)
    assert out["bundle_id"] in ("repo_to_agent", "github_reader")
    assert out["bundle_id"] != "research_basic"
    assert out["additional_tools"] == []

    debug = out["debug"]
    assert "release_workflow" in debug.get("detected_signals", {})
    assert debug["inferred_execution_types"]["cli_command"]["score"] > 0


def test_discover_tools_docs_heavy_dead_zone_avoids_empty_bundle() -> None:
    scout = {
        "repo_summary": "Docs-heavy project.",
        "important_files": ["README.md", "docs/usage.md", "docs/CONFIG.md"],
        "language_hints": [],
        "framework_hints": [],
    }
    arch = {
        "languages": [],
        "frameworks": [],
        "services": [],
        "entrypoints": [],
        "integrations": [],
        "key_paths": ["docs/", "README.md"],
    }
    out = discover_tools_from_repo(scout, arch)
    assert out["bundle_id"] == "repo_to_agent"
    assert "github_repo_read" in out["additional_tools"]

    debug = out["debug"]
    assert debug["inferred_capabilities"]["docs_editing"]["score"] > 0
    assert debug["inferred_execution_types"]["text_transform"]["score"] > 0


def test_discover_tools_script_heavy_prefers_repo_to_agent_or_github_reader() -> None:
    scout = {
        "repo_summary": "Automation scripts.",
        "important_files": ["scripts/generate_release.sh", "Makefile"],
        "language_hints": [],
        "framework_hints": [],
    }
    arch = {
        "languages": [],
        "frameworks": [],
        "services": [],
        "entrypoints": [],
        "integrations": [],
        "key_paths": ["scripts/", "Makefile", "generate-docs/"],
    }
    out = discover_tools_from_repo(scout, arch)
    assert out["bundle_id"] in ("repo_to_agent", "github_reader")

    debug = out["debug"]
    assert debug["inferred_capabilities"]["automation"]["score"] > 0
    assert debug["inferred_execution_types"]["cli_command"]["score"] > 0


def test_discover_tools_debug_has_repo_type_bias_fields() -> None:
    scout = {
        "repo_summary": "Automation scripts.",
        "important_files": ["scripts/run.py", "Makefile"],
        "language_hints": ["Python"],
        "framework_hints": [],
    }
    arch = {
        "languages": ["Python"],
        "frameworks": [],
        "services": [],
        "entrypoints": ["scripts/run.py"],
        "integrations": [],
        "key_paths": ["scripts/", "Makefile"],
    }
    out = discover_tools_from_repo(scout, arch)
    debug = out.get("debug") or {}
    assert "bundle_id_pre_repo_type_bias" in debug
    assert "bundle_id_post_repo_type_bias" in debug
    assert "bundle_repo_type_bias_applied" in debug
    assert "bundle_repo_type_bias_reason" in debug


def test_discover_tools_messy_low_signal_falls_back_to_no_tools_writer() -> None:
    scout = {
        "repo_summary": "Unknown / low-signal.",
        "important_files": ["notes.txt", "random.bin"],
        "language_hints": [],
        "framework_hints": [],
    }
    arch = {
        "languages": [],
        "frameworks": [],
        "services": [],
        "entrypoints": [],
        "integrations": [],
        "key_paths": [],
    }
    out = discover_tools_from_repo(scout, arch)
    assert out["bundle_id"] == "no_tools_writer"
    assert out["additional_tools"] == []

    debug = out["debug"]
    assert _max_execution_score(debug) == 0.0


def test_discover_tools_filesystem_code_navigation_prefers_repo_to_agent_or_github_reader() -> None:
    scout = {
        "repo_summary": "A tool that navigates repository structure.",
        "important_files": ["src/main.py", "lib/utils.js", "README.md"],
        "language_hints": ["Python"],
        "framework_hints": [],
    }
    arch = {
        "languages": ["Python"],
        "frameworks": [],
        "services": [],
        "entrypoints": ["src/main.py"],
        "integrations": [],
        "key_paths": ["src/", "lib/"],
    }
    out = discover_tools_from_repo(scout, arch)
    assert out["bundle_id"] in ("repo_to_agent", "github_reader")

    debug = out["debug"]
    assert debug["inferred_capabilities"]["file_search"]["score"] > 0
    assert debug["inferred_capabilities"]["code_navigation"]["score"] > 0


def test_discover_tools_accepts_pydantic_models() -> None:
    """discover_tools_from_repo accepts RepoScoutOutput and RepoArchitectureOutput."""
    scout = RepoScoutOutput(
        repo_summary="Test repo",
        important_files=["main.py"],
        language_hints=["Python"],
        framework_hints=[],
    )
    arch = RepoArchitectureOutput(
        languages=["Python"],
        frameworks=[],
        services=[],
        entrypoints=["main.py"],
        integrations=[],
        key_paths=[],
    )
    out = discover_tools_from_repo(scout, arch)
    assert out["bundle_id"] in ("repo_to_agent", "github_reader")
    assert "additional_tools" in out
    assert "rationale" in out
    assert "debug" in out


def test_discover_tools_internal_runner_agent_designer_uses_discovery() -> None:
    """Internal runner agent_designer uses discovery for bundle/tool selection and embeds debug."""
    from app.repo_to_agent.internal_runner import run_specialist_with_internal_runner
    from app.repo_to_agent.templates import AGENT_DESIGNER_TEMPLATE

    # HTTP-heavy repo -> should get http_request as additional tool
    input_payload = {
        "owner": "encode",
        "repo": "httpx",
        "scout": {
            "repo_summary": "HTTP client.",
            "important_files": ["httpx/api.py", "client.py"],
            "language_hints": ["Python"],
            "framework_hints": [],
        },
        "architecture": {
            "languages": ["Python"],
            "frameworks": [],
            "services": [],
            "entrypoints": ["httpx/__main__.py"],
            "integrations": ["http", "api"],
            "key_paths": ["httpx/"],
        },
    }
    result = run_specialist_with_internal_runner(AGENT_DESIGNER_TEMPLATE, input_payload)
    assert result["recommended_bundle"] in ("repo_to_agent", "github_reader")
    assert "http_request" in result["recommended_additional_tools"]

    debug = result["draft_agent_spec"].get("recommendation_debug") or {}
    assert debug.get("inferred_execution_types", {}).get("http_request", {}).get("score", 0.0) > 0
