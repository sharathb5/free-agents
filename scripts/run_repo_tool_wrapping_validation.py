#!/usr/bin/env python3
"""
Run repo-to-agent pipeline (discovery + wrapping) on selected public repos.

Prints repo summary, discovered repo tools, wrapped repo tools, risk levels,
and auto-exposable tools. Does not fail the whole run if persistence or
network fails; discovery/wrapping success is reported separately from
persistence failure.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Tuple

from app.repo_to_agent.app_flow import run_repo_to_agent
from app.repo_to_agent.persistence import persist_if_valid
from app.repo_to_agent.validation import ValidationResult, validate_repo_to_agent_result

# Repos to validate: (owner, repo). Default: OpenAI SDK (repo_scout, repo_architect, agent_designer). Override with REPO_VALIDATION_BACKEND=internal.
# MCP / LangChain / agent-related repos for discovery + wrapping testing.
VALIDATION_REPOS: List[Tuple[str, str]] = [
    ("esakrissa", "langchain-mcp"),
    ("Azure-Samples", "mcp-agent-langchainjs"),
    ("kabir12345", "Agent-Experiments"),
    ("aws-samples", "langchain-agents"),
    ("nngabe", "langchain_agents"),
    ("langchain-ai", "agents-from-scratch"),
    ("langchain-ai", "deepagents"),
    ("langchain-ai", "langchain-mcp-adapters"),
    ("egor-baranov", "mcp-agent-langchain"),
    ("langchain-ai", "langgraph"),
    ("mcp-use", "mcp-use"),
    ("punkpeye", "awesome-mcp-servers"),
    ("wong2", "awesome-mcp-servers"),
    ("heilcheng", "awesome-agent-skills"),
    ("NirDiamant", "agents-towards-production"),
]


def _print_section(title: str) -> None:
    print(title)
    print("-" * min(len(title), 60))


def _print_discovery_and_wrapping(owner: str, repo: str, result: Any) -> None:
    """Print discovered tools, wrapped tools, risk levels, auto-exposable."""
    _print_section("DISCOVERED REPO TOOLS")
    discovered = getattr(result, "discovered_repo_tools", None) or []
    if not discovered:
        print("  (none)")
    else:
        for t in discovered:
            name = getattr(t, "name", t.get("name", "")) if not isinstance(t, dict) else t.get("name", "")
            tool_type = getattr(t, "tool_type", t.get("tool_type", "")) if not isinstance(t, dict) else t.get("tool_type", "")
            cmd = getattr(t, "command", None) or (t.get("command") if isinstance(t, dict) else None)
            path = getattr(t, "source_path", "") or (t.get("source_path", "") if isinstance(t, dict) else "")
            print(f"  [{tool_type}] {name}" + (f"  command={cmd!r}" if cmd else "") + f"  source={path!r}")

    _print_section("WRAPPED REPO TOOLS")
    wrapped = getattr(result, "wrapped_repo_tools", None) or []
    if not wrapped:
        print("  (none)")
    else:
        for w in wrapped:
            name = getattr(w, "name", w.get("name", "")) if not isinstance(w, dict) else w.get("name", "")
            risk = getattr(w, "risk_level", w.get("risk_level", "")) if not isinstance(w, dict) else w.get("risk_level", "")
            safe = getattr(w, "safe_to_auto_expose", False) if not isinstance(w, dict) else w.get("safe_to_auto_expose", False)
            kind = getattr(w, "wrapper_kind", w.get("wrapper_kind", "")) if not isinstance(w, dict) else w.get("wrapper_kind", "")
            cmd = getattr(w, "command", None) or (w.get("command") if isinstance(w, dict) else None)
            print(f"  {name}  risk={risk}  safe_to_auto_expose={safe}  wrapper_kind={kind}" + (f"  command={cmd!r}" if cmd else ""))

    _print_section("AUTO-EXPOSABLE (low-risk)")
    auto = [w for w in wrapped if (getattr(w, "safe_to_auto_expose", False) if not isinstance(w, dict) else w.get("safe_to_auto_expose", False))]
    if not auto:
        print("  (none)")
    else:
        for w in auto:
            name = getattr(w, "name", w.get("name", "")) if not isinstance(w, dict) else w.get("name", "")
            print(f"  {name}")

    _print_section("HIGHER-RISK (require review)")
    higher = [w for w in wrapped if (getattr(w, "risk_level", "") in ("medium", "high") if not isinstance(w, dict) else w.get("risk_level") in ("medium", "high"))]
    if not higher:
        print("  (none)")
    else:
        for w in higher:
            name = getattr(w, "name", w.get("name", "")) if not isinstance(w, dict) else w.get("name", "")
            risk = getattr(w, "risk_level", w.get("risk_level", "")) if not isinstance(w, dict) else w.get("risk_level", "")
            print(f"  {name}  risk={risk}")


def main() -> int:
    backend = os.environ.get("REPO_VALIDATION_BACKEND", "openai")
    if backend == "openai":
        os.environ.setdefault("REPO_TO_AGENT_OPENAI_MODEL", "gpt-4o-mini")

    discovery_ok: List[Tuple[str, str]] = []
    discovery_fail: List[Tuple[str, str, str]] = []
    persistence_ok: List[Tuple[str, str]] = []
    persistence_fail: List[Tuple[str, str, str]] = []
    any_repo_had_tools = False

    for owner, repo in VALIDATION_REPOS:
        print("\n" + "=" * 60)
        print(f"Repo: {owner}/{repo}")
        print("=" * 60)

        try:
            result = run_repo_to_agent({"owner": owner, "repo": repo}, execution_backend=backend)
        except Exception as e:
            print("ERROR (discovery/wrapping or pipeline):", repr(e))
            discovery_fail.append((owner, repo, str(e)))
            continue

        discovery_ok.append((owner, repo))
        if getattr(result, "discovered_repo_tools", None) and len(result.discovered_repo_tools) > 0:
            any_repo_had_tools = True

        # Print discovery + wrapping output
        _print_discovery_and_wrapping(owner, repo, result)

        # Validation
        vr: ValidationResult = validate_repo_to_agent_result(result, owner=owner, repo=repo)
        _print_section("VALIDATION")
        print("status:", vr.status)
        for e in vr.errors:
            print("  error:", e)
        for w in vr.warnings:
            print("  warning:", w)

        # Persistence (do not fail run on persistence failure)
        _print_section("PERSISTENCE")
        try:
            persisted = persist_if_valid(result, owner, repo)
            if persisted:
                agent_id, version = persisted
                print(f"stored: yes (agent_id={agent_id} version={version})")
                persistence_ok.append((owner, repo))
            else:
                print("stored: no (validation failed or spec invalid)")
                persistence_fail.append((owner, repo, "validation failed or spec invalid"))
        except Exception as e:
            print("stored: no (exception)", repr(e))
            persistence_fail.append((owner, repo, str(e)))

    # Summary
    _print_section("SUMMARY")
    print("Discovery/wrapping success:", len(discovery_ok), discovery_ok)
    print("Discovery/wrapping failure:", len(discovery_fail), [(o, r) for o, r, _ in discovery_fail])
    print("Persistence success:", len(persistence_ok), persistence_ok)
    print("Persistence failure (does not fail run):", len(persistence_fail), [(o, r) for o, r, _ in persistence_fail])
    if discovery_ok and not any_repo_had_tools:
        print()
        print("Note: No tools were discovered in any repo. File content fetches may be failing (e.g. GitHub")
        print("rate limit without token). Set GITHUB_TOKEN for higher limits and retry.")
    # Exit 1 only if discovery/wrapping failed for at least one repo
    return 1 if discovery_fail else 0


if __name__ == "__main__":
    sys.exit(main())
