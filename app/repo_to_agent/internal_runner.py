"""
Internal runner for repo-to-agent specialists.

Concrete execution backend that does NOT use the OpenAI Agents SDK.
Uses github_repo_read as the primitive and reuses app.runtime.tools.
Deterministic/minimal backend with TODOs for real reasoning (LLM) integration.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

from app.preset_loader import Preset
from app.runtime.tools.registry import (
    DefaultToolRegistry,
    RunContext,
    build_run_context,
)

from .code_tool_discovery import (
    discover_code_defined_tools,
    get_paths_to_inspect_for_code_tools,
)
from .repo_tool_discovery import (
    discover_tools_from_repo as discover_repo_tools_from_repo,
    get_paths_to_inspect_for_tools,
)
from .templates import (
    AGENT_DESIGNER_TEMPLATE,
    AGENT_REVIEWER_TEMPLATE,
    CODE_TOOL_DISCOVERY_TEMPLATE,
    REPO_ARCHITECT_TEMPLATE,
    REPO_SCOUT_TEMPLATE,
    REPO_TOOL_DISCOVERY_TEMPLATE,
    AgentTemplate,
)
from .tool_discovery import discover_tools_from_repo


def _template_to_preset(template: AgentTemplate) -> Preset:
    """Build a minimal Preset from an AgentTemplate for run context."""
    return Preset(
        id=template.id,
        version="internal",
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
        tool_policies=None,
        resolved_execution_limits=None,
    )


def _run_github_repo_read(
    registry: DefaultToolRegistry,
    run_context: RunContext,
    owner: str,
    repo: str,
    ref: str | None,
    mode: str,
    path: str | None = None,
) -> Dict[str, Any]:
    """Execute github_repo_read once; respects policy from run_context."""
    args: Dict[str, Any] = {
        "owner": owner,
        "repo": repo,
        "mode": mode,
    }
    if ref:
        args["ref"] = ref
    if path:
        args["path"] = path
    return registry.execute("github_repo_read", args, run_context)


def _synthesize_repo_scout(
    overview: Dict[str, Any],
    sample: Dict[str, Any],
) -> Dict[str, Any]:
    """Build RepoScoutOutput from overview + sample tool results."""
    hints = overview.get("hints") or {}
    important = overview.get("important_files") or []
    repo_out = overview.get("repo") or {}
    name = repo_out.get("name") or "repo"
    languages = hints.get("languages") or []
    frameworks = hints.get("frameworks") or []
    # Minimal deterministic summary; TODO: replace with LLM-generated summary when reasoning available.
    summary_parts = [f"Repository: {name}"]
    if languages:
        summary_parts.append(f"Languages: {', '.join(languages)}")
    if frameworks:
        summary_parts.append(f"Frameworks: {', '.join(frameworks)}")
    repo_summary = ". ".join(summary_parts)
    return {
        "repo_summary": repo_summary,
        "important_files": important,
        "language_hints": languages,
        "framework_hints": frameworks,
    }


def _synthesize_repo_architect(
    overview: Dict[str, Any],
    tree: Dict[str, Any],
) -> Dict[str, Any]:
    """Build RepoArchitectureOutput from overview + tree tool results."""
    hints = overview.get("hints") or {}
    languages = hints.get("languages") or []
    frameworks = hints.get("frameworks") or []
    entries = tree.get("entries") or []
    paths = [e.get("path") or "" for e in entries if e.get("path")]
    # Deterministic derivation; TODO: replace with LLM when reasoning available.
    services: List[str] = []
    if any("api" in p.lower() or "server" in p.lower() for p in paths):
        services.append("api")
    entrypoints: List[str] = []
    for p in paths:
        base = p.split("/")[-1].lower()
        if base in ("main.py", "app.py", "index.js", "server.py"):
            entrypoints.append(p)
    return {
        "languages": languages,
        "frameworks": frameworks,
        "services": services,
        "entrypoints": entrypoints[:10],
        "integrations": [],
        "key_paths": paths[:30],
    }


def _stub_agent_designer(input_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic stub for agent_designer (no tools). Uses repo tool discovery for bundle + tools. TODO: replace with LLM."""
    scout = input_payload.get("scout") or {}
    architecture = input_payload.get("architecture") or {}
    discovery = discover_tools_from_repo(scout, architecture)
    bundle_id = discovery.get("bundle_id") or "repo_to_agent"
    additional_tools = discovery.get("additional_tools") or []

    repo_summary = scout.get("repo_summary", "") if isinstance(scout, dict) else getattr(scout, "repo_summary", "")
    name = (str(repo_summary) if repo_summary else "Agent from repo").strip()[:80]
    langs = (architecture.get("languages") if isinstance(architecture, dict) else []) or (scout.get("language_hints", []) if isinstance(scout, dict) else [])
    if not isinstance(langs, list):
        langs = []
    desc = f"Draft agent for repo. Languages: {', '.join(langs)}" if langs else "Draft agent from repo analysis."
    return {
        "recommended_bundle": bundle_id,
        "recommended_additional_tools": additional_tools,
        "draft_agent_spec": {
            "id": "draft-from-repo",
            "version": "0.1.0",
            "name": name,
            "description": desc,
            "primitive": "transform",
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": True},
            "output_schema": {"type": "object", "properties": {}, "additionalProperties": True},
            "prompt": "You are an agent generated from repo analysis. Follow the user's request.",
        },
        "starter_eval_cases": [
            {
                "name": "placeholder_eval",
                "input": "Describe what this repo does.",
                "expected": "A short description of the repository and its purpose.",
            },
        ],
    }


def _stub_agent_reviewer(input_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic stub for agent_reviewer (no tools). TODO: replace with LLM."""
    return {
        "review_notes": ["Internal runner: no LLM review yet. Validate draft manually."],
        "risks": [],
        "open_questions": [],
    }


def run_specialist_with_internal_runner(
    template: AgentTemplate,
    input_payload: Dict[str, Any],
    step_telemetry: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Execute a single specialist using the internal (non-OpenAI) backend.

    - Respects template.allowed_tools; only github_repo_read is executed here.
    - For repo_scout: runs overview + sample, then synthesizes RepoScoutOutput.
    - For repo_architect: runs overview + tree, then synthesizes RepoArchitectureOutput.
    - For agent_designer / agent_reviewer: no tools; returns deterministic stubs.

    Workflow/model validation stays in the workflow layer; this returns a dict
    suitable for validation by run_repo_to_agent_workflow.

    TODO: When true reasoning is available, replace deterministic synthesis and
    stubs with an LLM step (or OpenAI Agents SDK) that uses the same tool primitive.
    """
    if step_telemetry is not None:
        step_telemetry["backend_used"] = "internal"
        step_telemetry.setdefault("tool_calls_count", 0)

    allowed = list(template.allowed_tools) if template.allowed_tools else []
    for t in allowed:
        if t != "github_repo_read":
            # Internal runner only supports github_repo_read; others are no-op or future.
            pass

    if template.id == REPO_SCOUT_TEMPLATE.id:
        owner = input_payload.get("owner") or ""
        repo = input_payload.get("repo") or ""
        ref = input_payload.get("ref")
        if not owner or not repo:
            raise ValueError("repo_scout input must include owner and repo")
        preset = _template_to_preset(template)
        run_id = f"internal-{uuid.uuid4().hex[:12]}"
        run_context = build_run_context(run_id=run_id, preset=preset)
        registry: DefaultToolRegistry = DefaultToolRegistry()
        overview = _run_github_repo_read(registry, run_context, owner, repo, ref, "overview")
        sample = _run_github_repo_read(registry, run_context, owner, repo, ref, "sample")
        return _synthesize_repo_scout(overview, sample)

    if template.id == REPO_ARCHITECT_TEMPLATE.id:
        owner = input_payload.get("owner") or ""
        repo = input_payload.get("repo") or ""
        ref = input_payload.get("ref")
        if not owner or not repo:
            raise ValueError("repo_architect input must include owner and repo")
        preset = _template_to_preset(template)
        run_id = f"internal-{uuid.uuid4().hex[:12]}"
        run_context = build_run_context(run_id=run_id, preset=preset)
        registry = DefaultToolRegistry()
        overview = _run_github_repo_read(registry, run_context, owner, repo, ref, "overview")
        tree = _run_github_repo_read(registry, run_context, owner, repo, ref, "tree", path="")
        return _synthesize_repo_architect(overview, tree)

    if template.id == REPO_TOOL_DISCOVERY_TEMPLATE.id:
        owner = input_payload.get("owner") or ""
        repo = input_payload.get("repo") or ""
        ref = input_payload.get("ref")
        scout = input_payload.get("scout") or {}
        architecture = input_payload.get("architecture") or {}
        if not owner or not repo:
            raise ValueError("repo_tool_discovery input must include owner and repo")
        file_paths, folder_paths = get_paths_to_inspect_for_tools(scout, architecture)
        preset = _template_to_preset(template)
        run_id = f"internal-{uuid.uuid4().hex[:12]}"
        run_context = build_run_context(run_id=run_id, preset=preset)
        registry: DefaultToolRegistry = DefaultToolRegistry()
        file_contents: Dict[str, str] = {}
        for path in file_paths:
            try:
                out = _run_github_repo_read(registry, run_context, owner, repo, ref, "file", path=path)
                content = out.get("content") or ""
                if isinstance(content, str):
                    file_contents[path] = content
            except Exception:
                pass
        folder_listings: Dict[str, List[Dict[str, Any]]] = {}
        for folder in folder_paths:
            try:
                out = _run_github_repo_read(registry, run_context, owner, repo, ref, "tree", path=folder)
                entries = out.get("entries") or []
                folder_listings[folder] = entries
            except Exception:
                pass
        discovered = discover_repo_tools_from_repo(
            scout, architecture,
            file_contents=file_contents,
            folder_listings=folder_listings,
        )
        return {"discovered_tools": [t.model_dump() for t in discovered]}

    if template.id == CODE_TOOL_DISCOVERY_TEMPLATE.id:
        owner = input_payload.get("owner") or ""
        repo = input_payload.get("repo") or ""
        ref = input_payload.get("ref")
        scout = input_payload.get("scout") or {}
        architecture = input_payload.get("architecture") or {}
        if not owner or not repo:
            raise ValueError("code_tool_discovery input must include owner and repo")
        code_paths = get_paths_to_inspect_for_code_tools(scout, architecture)
        file_contents: Dict[str, str] = {}
        preset = _template_to_preset(template)
        run_id = f"internal-{uuid.uuid4().hex[:12]}"
        run_context = build_run_context(run_id=run_id, preset=preset)
        registry = DefaultToolRegistry()
        for path in code_paths:
            try:
                out = _run_github_repo_read(registry, run_context, owner, repo, ref, "file", path=path)
                content = out.get("content") or ""
                if isinstance(content, str):
                    file_contents[path] = content
            except Exception:
                pass
        code_tools = discover_code_defined_tools(scout, architecture, file_contents=file_contents)
        return {"code_tools": [t.model_dump() for t in code_tools]}

    if template.id == AGENT_DESIGNER_TEMPLATE.id:
        return _stub_agent_designer(input_payload)

    if template.id == AGENT_REVIEWER_TEMPLATE.id:
        return _stub_agent_reviewer(input_payload)

    # Unknown template: return minimal output_schema-shaped dict if possible
    out_schema = template.output_schema or {}
    props = out_schema.get("properties") or {}
    result: Dict[str, Any] = {}
    for key in props:
        if isinstance(props[key], dict) and props[key].get("type") == "array":
            result[key] = []
        elif isinstance(props[key], dict) and props[key].get("type") == "string":
            result[key] = ""
        else:
            result[key] = None
    return result
