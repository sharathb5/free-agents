#!/usr/bin/env python3
"""Run repo-to-agent on test repos, print validation and persistence results.

Env vars:
  REPO_VALIDATION_BACKEND     - "openai" (default) or "internal"
  REPO_VALIDATION_COOLDOWN    - Seconds between repos (default 45 for openai when running agent/section/single).
  REPO_VALIDATION_AGENT_ONLY  - If set, run only agent repos (no library repos).
  REPO_VALIDATION_REPO        - Single repo as "owner/repo" (overrides other list selection).
  REPO_VALIDATION_SECTION     - Run one section only: "1".."5" (agent/tool repos; use to avoid rate limits).
  REPO_VALIDATION_AGENT_REPOS - If set (and no SECTION/REPO), run TEST_REPOS + all agent repos.

Sections (run one at a time to avoid rate limits):
  1 - github/github-mcp-server          (MCP server, GitHub API tools)
  2 - modelcontextprotocol/servers      (MCP reference servers)
  3 - langchain-ai/agents-from-scratch (LangChain agents + tools)
  4 - langchain-ai/langgraph            (LangGraph workflows/tools)
  5 - langchain-ai/langchain-mcp-adapters (LangChain MCP adapters)

Run one section at a time (recommended for OpenAI to avoid rate limits):
  REPO_VALIDATION_SECTION=1 REPO_VALIDATION_COOLDOWN=60 python -m scripts.run_repo_validation   # github-mcp-server
  REPO_VALIDATION_SECTION=2 REPO_VALIDATION_COOLDOWN=60 python -m scripts.run_repo_validation   # MCP servers
  REPO_VALIDATION_SECTION=3 REPO_VALIDATION_COOLDOWN=60 python -m scripts.run_repo_validation   # agents-from-scratch
  REPO_VALIDATION_SECTION=4 REPO_VALIDATION_COOLDOWN=60 python -m scripts.run_repo_validation   # langgraph
  REPO_VALIDATION_SECTION=5 REPO_VALIDATION_COOLDOWN=60 python -m scripts.run_repo_validation   # langchain-mcp-adapters

Single repo: REPO_VALIDATION_REPO=owner/repo python -m scripts.run_repo_validation
"""
from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, List, Tuple

from app.repo_to_agent.app_flow import run_repo_to_agent
from app.repo_to_agent.persistence import persist_if_valid
from app.repo_to_agent.validation import ValidationResult, validate_repo_to_agent_result

# Default cooldown when not overridden by env (used for openai between repos).
DEFAULT_COOLDOWN = 20
# Default cooldown when running agent-only, section, or single repo (openai).
DEFAULT_AGENT_COOLDOWN = 45

TEST_REPOS: List[Tuple[str, str]] = [
    ("psf", "requests"),
    ("encode", "httpx"),
    ("pallets", "flask"),
]

# Agent/tool repos: real repos with agents, MCP, or tool definitions for code discovery.
AGENT_REPOS_FOR_CODE_DISCOVERY: List[Tuple[str, str]] = [
    ("github", "github-mcp-server"),
    ("modelcontextprotocol", "servers"),
    ("langchain-ai", "agents-from-scratch"),
    ("langchain-ai", "langgraph"),
    ("langchain-ai", "langchain-mcp-adapters"),
]

# Five sections for running one-at-a-time to avoid rate limits. Each section is one repo.
VALIDATION_SECTIONS: List[List[Tuple[str, str]]] = [
    [("github", "github-mcp-server")],           # 1: MCP server, GitHub API tools
    [("modelcontextprotocol", "servers")],       # 2: MCP reference servers
    [("langchain-ai", "agents-from-scratch")],   # 3: LangChain agents + tools
    [("langchain-ai", "langgraph")],             # 4: LangGraph workflows/tools
    [("langchain-ai", "langchain-mcp-adapters")], # 5: LangChain MCP adapters
]


def _print_section(title: str) -> None:
    print(title)
    print("-" * len(title))


def _bundle_posture_framing(bundle_id: str | None) -> str:
    """
    Intentional one-line framing for demo/validation output so multiple repos
    landing on the same bundle reads deliberate, not accidental.
    """
    bid = (bundle_id or "").strip()
    if bid == "repo_to_agent":
        return (
            "Bundle posture: inspection-first default for repos where reading structure/code "
            "is the most useful starting posture."
        )
    if bid == "github_reader":
        return "Bundle posture: lighter-weight read-only posture."
    if bid == "no_tools_writer":
        return "Bundle posture: no-tool explanatory posture."
    if bid == "research_basic":
        return "Bundle posture: web/research-oriented (HTTP) when sources matter more than repo inspection."
    if bid == "data_analysis":
        return "Bundle posture: data/analysis-oriented (catalog-defined)."
    return f"Bundle posture: see catalog for bundle_id={bid!r}."


def _print_repo_result(owner: str, repo: str, result: Any) -> None:
    print("\n" + "=" * 48)
    print(f"Repo: {owner}/{repo}")
    print("=" * 48 + "\n")

    # SCOUT SUMMARY
    _print_section("SCOUT SUMMARY")
    print(result.repo_summary)
    print("\nimportant_files:")
    for path in result.important_files:
        print(f"- {path}")
    print()

    # ARCHITECTURE
    _print_section("ARCHITECTURE")
    arch = result.architecture
    print("languages:", arch.languages)
    print("frameworks:", arch.frameworks)
    print("entrypoints:")
    for p in arch.entrypoints:
        print(f"- {p}")
    print("integrations:", arch.integrations)
    print("key_paths:")
    for p in arch.key_paths:
        print(f"- {p}")
    print()

    # AGENT DESIGN
    _print_section("AGENT DESIGN")
    print("recommended_bundle:", result.recommended_bundle)
    print(_bundle_posture_framing(getattr(result, "recommended_bundle", None)))
    print("recommended_additional_tools:", result.recommended_additional_tools)
    print()

    # MANIFEST/FILE-BASED DISCOVERED TOOLS
    _print_section("DISCOVERED TOOLS (manifest/file-based)")
    for t in getattr(result, "discovered_manifest_tools", []) or []:
        name = getattr(t, "name", t) if not isinstance(t, dict) else t.get("name", "")
        tool_type = getattr(t, "tool_type", t) if not isinstance(t, dict) else t.get("tool_type", "")
        cmd = getattr(t, "command", None) or (t.get("command") if isinstance(t, dict) else None)
        print(f"  {tool_type}: {name}" + (f" ({cmd})" if cmd else ""))
    if not getattr(result, "discovered_manifest_tools", None) or not result.discovered_manifest_tools:
        print("  (none)")
    print()

    # CODE-DEFINED DISCOVERED TOOLS
    _print_section("DISCOVERED TOOLS (code-defined)")
    for t in getattr(result, "discovered_code_tools", []) or []:
        name = getattr(t, "name", t) if not isinstance(t, dict) else t.get("name", "")
        tool_type = getattr(t, "tool_type", t) if not isinstance(t, dict) else t.get("tool_type", "")
        path = getattr(t, "source_path", None) or (t.get("source_path") if isinstance(t, dict) else None)
        print(f"  {tool_type}: {name}" + (f" @ {path}" if path else ""))
    if not getattr(result, "discovered_code_tools", None) or not result.discovered_code_tools:
        print("  (none)")
    print()

    # MERGED DISCOVERED REPO TOOLS
    _print_section("DISCOVERED REPO TOOLS (merged)")
    for t in getattr(result, "discovered_repo_tools", []) or []:
        name = getattr(t, "name", t) if not isinstance(t, dict) else t.get("name", "")
        tool_type = getattr(t, "tool_type", t) if not isinstance(t, dict) else t.get("tool_type", "")
        cmd = getattr(t, "command", None) or (t.get("command") if isinstance(t, dict) else None)
        print(f"  {tool_type}: {name}" + (f" ({cmd})" if cmd else ""))
    if not getattr(result, "discovered_repo_tools", None):
        print("  (none)")
    print()

    # WRAPPED REPO TOOLS
    _print_section("WRAPPED REPO TOOLS")
    for t in getattr(result, "wrapped_repo_tools", []) or []:
        w = t.model_dump() if hasattr(t, "model_dump") else (t if isinstance(t, dict) else {})
        name = w.get("name", "")
        wrapper_kind = w.get("wrapper_kind", "")
        print(f"  {wrapper_kind}: {name}")
    if not getattr(result, "wrapped_repo_tools", None) or not result.wrapped_repo_tools:
        print("  (none)")
    print()

    # DRAFT AGENT SPEC
    _print_section("DRAFT AGENT SPEC")
    spec: Dict[str, Any] = result.draft_agent_spec or {}
    print("name:", spec.get("name"))
    print("description:", spec.get("description"))
    print()

    # EVAL CASES
    _print_section("EVAL CASES")
    print(
        "Note: starter_eval_cases are minimal in the deterministic V1 path "
        "(satisfy validation; richer cases come from LLM-backed runs)."
    )
    for case in result.starter_eval_cases:
        print(case)
    print()


def _print_validation(vr: ValidationResult) -> None:
    _print_section("VALIDATION")
    print("status:", vr.status)
    if vr.errors:
        print("errors:")
        for e in vr.errors:
            print(f"  - {e}")
    if vr.warnings:
        print("warnings:")
        for w in vr.warnings:
            print(f"  - {w}")
    if not vr.errors and not vr.warnings:
        print("(no errors or warnings)")
    print()


def _get_repos_to_run() -> List[Tuple[str, str]]:
    """Resolve repo list from env: REPO_VALIDATION_REPO > SECTION > AGENT_ONLY > AGENT_REPOS > default."""
    single = os.environ.get("REPO_VALIDATION_REPO", "").strip()
    if single:
        parts = single.split("/", 1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            return [(parts[0].strip(), parts[1].strip())]
    section = os.environ.get("REPO_VALIDATION_SECTION", "").strip()
    if section.isdigit():
        idx = int(section)
        if 1 <= idx <= len(VALIDATION_SECTIONS):
            return list(VALIDATION_SECTIONS[idx - 1])
    if os.environ.get("REPO_VALIDATION_AGENT_ONLY"):
        return list(AGENT_REPOS_FOR_CODE_DISCOVERY)
    if os.environ.get("REPO_VALIDATION_AGENT_REPOS"):
        return list(TEST_REPOS) + list(AGENT_REPOS_FOR_CODE_DISCOVERY)
    return list(TEST_REPOS)


def _get_cooldown_seconds(backend: str, repos_to_run: List[Tuple[str, str]]) -> int:
    """Cooldown between repos. Env REPO_VALIDATION_COOLDOWN overrides. Default 45 for openai+agent/section/single."""
    raw = os.environ.get("REPO_VALIDATION_COOLDOWN", "").strip()
    if raw.isdigit():
        return int(raw)
    if backend == "openai":
        # Use longer default when running agent-only, a single section, or single repo.
        if len(repos_to_run) <= 1 or set(repos_to_run).issubset(set(AGENT_REPOS_FOR_CODE_DISCOVERY)):
            return DEFAULT_AGENT_COOLDOWN
    return DEFAULT_COOLDOWN


def main() -> int:
    results: List[Tuple[str, str, str, List[str], List[str]]] = []
    backend = os.environ.get("REPO_VALIDATION_BACKEND", "openai")
    if backend == "openai":
        os.environ.setdefault("REPO_TO_AGENT_OPENAI_MODEL", "gpt-4o-mini")
    repos_to_run = _get_repos_to_run()
    cooldown = _get_cooldown_seconds(backend, repos_to_run)
    # Print run mode so user knows what's being executed
    mode = "single repo" if len(repos_to_run) == 1 and os.environ.get("REPO_VALIDATION_REPO") else (
        f"section {os.environ.get('REPO_VALIDATION_SECTION', '')}" if os.environ.get("REPO_VALIDATION_SECTION") else
        "agent-only" if os.environ.get("REPO_VALIDATION_AGENT_ONLY") else
        "agent+library" if os.environ.get("REPO_VALIDATION_AGENT_REPOS") else "library repos"
    )
    print(f"Backend: {backend}  Mode: {mode}  Repos: {len(repos_to_run)}  Cooldown: {cooldown}s")
    print("Repos:", " ".join(f"{o}/{r}" for o, r in repos_to_run))
    print()
    for owner, repo in repos_to_run:
        try:
            result = run_repo_to_agent({"owner": owner, "repo": repo}, execution_backend=backend)
        except Exception as exc:  # pragma: no cover - manual validation helper
            print("\n" + "=" * 48)
            print(f"Repo: {owner}/{repo}")
            print("=" * 48)
            print("ERROR while running repo-to-agent:")
            print(repr(exc))
            print()
            results.append((owner, repo, "fail", [repr(exc)], []))
            # Do not fail the whole run: continue to next repo.
            if backend == "openai" and (owner, repo) != repos_to_run[-1]:
                print(f"(Waiting {cooldown}s before next repo...)")
                time.sleep(cooldown)
            continue

        _print_repo_result(owner, repo, result)
        vr = validate_repo_to_agent_result(result, owner=owner, repo=repo)
        _print_validation(vr)
        # Persist only when validation passes (pass or pass_with_warnings). Do not fail run if persist fails.
        _print_section("PERSISTENCE")
        try:
            persisted = persist_if_valid(result, owner, repo)
            if persisted:
                agent_id, version = persisted
                print(f"stored: yes (agent_id={agent_id} version={version})")
                print("Retrieve via: registry_store.get_agent(agent_id) or get_agent_as_stored(agent_id)")
            else:
                print("stored: no (validation failed or spec invalid)")
        except Exception as e:
            print(f"stored: no (persistence error: {e})")
        print()
        results.append((owner, repo, vr.status, vr.errors, vr.warnings))

        # Avoid OpenAI TPM rate limit: wait before next repo when using openai backend.
        if backend == "openai" and (owner, repo) != repos_to_run[-1]:
            print(f"(Waiting {cooldown}s before next repo to avoid rate limit...)")
            time.sleep(cooldown)

    # Final summary
    passed = sum(1 for _, _, s, _, _ in results if s == "pass")
    pass_warnings = sum(1 for _, _, s, _, _ in results if s == "pass_with_warnings")
    failed = sum(1 for _, _, s, _, _ in results if s == "fail")
    _print_section("SUMMARY")
    print(f"pass: {passed}, pass_with_warnings: {pass_warnings}, fail: {failed}")
    for owner, repo, status, _, _ in results:
        print(f"  {owner}/{repo}: {status}")
    print()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

