"""
Internal runner for repo-to-agent specialists.

Concrete execution backend that does NOT use the OpenAI Agents SDK.
Uses github_repo_read as the primitive and reuses app.runtime.tools.
Deterministic/minimal backend with TODOs for real reasoning (LLM) integration.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Dict, List, Optional

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

_log = logging.getLogger(__name__)

_DEBUG_LOG_PATH = "/Users/sharath/agent-toolbox/agent-toolbox/.cursor/debug-db76a9.log"


def _debug_log(*, hypothesis_id: str, location: str, message: str, data: Dict[str, Any] | None = None) -> None:
    # #region agent log
    try:
        import json as _json
        import time as _time
        payload: Dict[str, Any] = {
            "sessionId": "db76a9",
            "timestamp": int(_time.time() * 1000),
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(_json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion agent log


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


def _strip_markdown(text: str) -> str:
    """Remove markdown syntax from text, leaving plain readable content."""
    # Strip image badges and standalone images: [![alt](img)](url) or ![alt](url)
    text = re.sub(r'!\[([^\]]*)\]\([^)]*\)', '', text)
    # Strip links, keeping the link text: [text](url)
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
    # Strip reference-style links: [text][ref] → text
    text = re.sub(r'\[([^\]]*)\]\[[^\]]*\]', r'\1', text)
    # Strip inline code backticks (single or triple), keeping inner text
    text = re.sub(r'```[a-zA-Z]*\n?', '', text)
    text = re.sub(r'`([^`]*)`', r'\1', text)
    # Strip bold and italic markers: ***text***, **text**, *text*, __text__, _text_
    text = re.sub(r'\*{1,3}([^*]*)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,2}([^_]*)_{1,2}', r'\1', text)
    # Strip HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Strip blockquote markers
    text = re.sub(r'^\s*>\s?', '', text, flags=re.MULTILINE)
    # Strip horizontal rules
    text = re.sub(r'^\s*[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    # Collapse leftover whitespace artifacts
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text


def _excerpt_for_repo_summary(text: str, *, max_chars: int = 900) -> str:
    """First substantive paragraph from markdown-ish text, bounded (deterministic)."""
    if not text or not isinstance(text, str):
        return ""
    text = _strip_markdown(text)
    t = text.strip()
    lines = t.splitlines()
    start = 0
    if lines and lines[0].startswith("#"):
        start = 1
        while start < len(lines) and not lines[start].strip():
            start += 1
    body = "\n".join(lines[start:]).strip()
    para = body.split("\n\n")[0] if body else ""
    para = " ".join(para.split())
    if len(para) > max_chars:
        para = para[: max_chars - 1].rsplit(" ", 1)[0] + "…"
    return para.strip()


def _build_grounded_repo_prompt(
    *,
    repo_label: str,
    summary_for_prompt: str,
    key_paths_txt: str,
    langs_txt: str,
    closing: str,
) -> str:
    """Shared prompt body for repo-grounded agent drafts (internal designer stub)."""
    prompt_parts = [
        f"You are an expert assistant for the {repo_label} repository.\n",
        f"Repository summary: {summary_for_prompt}\n",
    ]
    if key_paths_txt:
        prompt_parts.append("Key files and paths:\n" + key_paths_txt + "\n")
    if langs_txt:
        prompt_parts.append(langs_txt + "\n")
    prompt_parts.append("\n" + closing)
    return "".join(prompt_parts)


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
    # Base line from metadata; sample mode already fetched file bodies for top important files.
    summary_parts = [f"Repository: {name}"]
    if languages:
        summary_parts.append(f"Languages: {', '.join(languages)}")
    if frameworks:
        summary_parts.append(f"Frameworks: {', '.join(frameworks)}")
    excerpt_bits: List[str] = []
    for f in (sample or {}).get("files") or []:
        if not isinstance(f, dict):
            continue
        path = str(f.get("path") or "").strip()
        content = f.get("content")
        if not path or not isinstance(content, str) or not content.strip():
            continue
        pl = path.lower()
        ex_max = 850
        if pl.endswith((".toml", ".yaml", ".yml")) or pl.endswith("package.json") or pl.endswith("package-lock.json"):
            ex_max = 380
        ex = _excerpt_for_repo_summary(content, max_chars=ex_max)
        if ex:
            excerpt_bits.append(f"{path}: {ex}")
    if excerpt_bits:
        summary_parts.append(" ".join(excerpt_bits))
    repo_summary = ". ".join(summary_parts)
    if len(repo_summary) > 12_000:
        repo_summary = repo_summary[:11_999] + "…"
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
    # Ensure key structural signals are present even when the tree is large and we truncate.
    # Some classifiers rely on seeing packaging + module/test structure markers.
    paths_lower = [p.lower() for p in paths]
    priority: List[str] = []
    # Packaging/config files.
    for fname in ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "package.json"):
        if fname in paths_lower:
            # Recover original casing/path from `paths` deterministically.
            priority.append(paths[paths_lower.index(fname)])
    # Common structure directories.
    for d in ("src/", "tests/", "test/", "docs/", "examples/"):
        d_no = d.rstrip("/")
        if any(p.startswith(d) for p in paths_lower) or any(p == d_no for p in paths_lower):
            # Keep trailing slash so downstream heuristics match `startswith("tests/")`, etc.
            priority.append(d)
    # If there are any package initializers, surface a couple to prove module structure.
    init_paths = [p for p in paths_lower if p.endswith("/__init__.py") or p.endswith("__init__.py")]
    for p in init_paths[:5]:
        priority.append(paths[paths_lower.index(p)])
    # Also surface package directories (e.g. src/pvlib/) and a couple representative .py files
    # from src/ and tests/ so library repos aren't misrepresented as "setup.py only".
    package_dirs: List[str] = []
    for p in init_paths[:20]:
        orig = paths[paths_lower.index(p)]
        if "/__init__.py" in orig.lower():
            pkg_dir = orig.rsplit("/__init__.py", 1)[0].rstrip("/") + "/"
            package_dirs.append(pkg_dir)
    for d in package_dirs[:5]:
        priority.append(d)
    src_py = [paths[i] for i, pl in enumerate(paths_lower) if pl.startswith("src/") and pl.endswith(".py")]
    tests_py = [paths[i] for i, pl in enumerate(paths_lower) if (pl.startswith("tests/") or pl.startswith("test/")) and pl.endswith(".py")]
    for p in (src_py[:5] + tests_py[:5]):
        priority.append(p)
    # Build bounded key_paths with priority items first, then fill with tree paths.
    key_paths_out: List[str] = []
    seen: set[str] = set()
    for p in priority:
        pp = str(p).strip()
        if pp and pp not in seen:
            key_paths_out.append(pp)
            seen.add(pp)
    for p in paths:
        pp = str(p).strip()
        if pp and pp not in seen:
            key_paths_out.append(pp)
            seen.add(pp)
        if len(key_paths_out) >= 120:
            break
    return {
        "languages": languages,
        "frameworks": frameworks,
        "services": services,
        "entrypoints": entrypoints[:10],
        "integrations": [],
        # Keep more paths than the minimal stub; script-heavy repos need broader surface coverage.
        # Still bounded to avoid huge payloads.
        "key_paths": key_paths_out,
    }


def _stub_agent_designer(input_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic stub for agent_designer (no tools). Uses repo tool discovery for bundle + tools. TODO: replace with LLM."""
    scout = input_payload.get("scout") or {}
    architecture = input_payload.get("architecture") or {}
    discovered_repo_tools = input_payload.get("discovered_repo_tools") or []

    def _paths_from_payload() -> List[str]:
        paths: List[str] = []
        if isinstance(scout, dict):
            paths.extend([str(x) for x in (scout.get("important_files") or []) if str(x).strip()])
        if isinstance(architecture, dict):
            paths.extend([str(x) for x in (architecture.get("key_paths") or []) if str(x).strip()])
            paths.extend([str(x) for x in (architecture.get("entrypoints") or []) if str(x).strip()])
        return paths

    paths_lower = [p.strip().lower() for p in _paths_from_payload()]
    has_agent_json = ("agent.json" in paths_lower) or any(
        isinstance(t, dict) and str(t.get("source_path") or "").strip().lower() == "agent.json"
        for t in (discovered_repo_tools or [])
    )
    has_system_prompt = "prompts/system_prompt.md" in paths_lower

    # SINGLE source of truth: tool discovery computes repo_type using classify_repo_type,
    # and we use that same result for draft + debug to avoid inconsistencies.
    discovery = discover_tools_from_repo(
        scout,
        architecture,
        discovered_repo_tools=discovered_repo_tools if isinstance(discovered_repo_tools, list) else None,
    )
    bundle_id = discovery.get("bundle_id") or "repo_to_agent"
    additional_tools = discovery.get("additional_tools") or []
    recommendation_debug = discovery.get("debug") or {}
    repo_type = (
        recommendation_debug.get("repo_type")
        if isinstance(recommendation_debug, dict)
        else None
    ) or "unknown"
    repo_type_confidence = (
        float(recommendation_debug.get("repo_type_confidence") or 0.0)
        if isinstance(recommendation_debug, dict)
        else 0.0
    )

    repo_summary = scout.get("repo_summary", "") if isinstance(scout, dict) else getattr(scout, "repo_summary", "")
    name = (str(repo_summary) if repo_summary else "Agent from repo").strip()[:80]
    langs = (architecture.get("languages") if isinstance(architecture, dict) else []) or (scout.get("language_hints", []) if isinstance(scout, dict) else [])
    if not isinstance(langs, list):
        langs = []

    # Primitive mapping table (deterministic).
    primitive_by_repo_type = {
        "explicit_agent": "structured_agent",
        "agent_framework": "structured_agent",
        "automation_scripts": "extract",
        "docs_tutorial": "transform",
        "library_framework": "classify",
        "unknown": "transform",
    }
    primitive = primitive_by_repo_type.get(repo_type, "transform")

    # Description/prompt should reflect repo purpose (avoid generic fallback tone).
    langs_txt = f"Languages: {', '.join([str(x) for x in langs if str(x).strip()])}." if langs else ""
    _log.info(
        "internal_runner draft synthesis repo_type=%s confidence=%.2f bundle_id=%s",
        repo_type,
        repo_type_confidence,
        bundle_id,
    )
    repo_type_txt = f"Repo type: {repo_type}."
    if repo_type == "automation_scripts":
        desc = ("Automation assistant draft for running/utilizing repository scripts and commands. " + langs_txt + " " + repo_type_txt).strip()
        prompt = (
            "You are an automation assistant for this repository.\n"
            "Help the user discover and safely use the repo's scripts/commands and typical workflows.\n"
            "Prefer explaining what to run and why, and ask for clarification when the desired automation goal is ambiguous.\n"
        )
    elif repo_type in ("docs_tutorial", "library_framework", "agent_framework", "explicit_agent"):
        owner = str(input_payload.get("owner") or "").strip()
        repo = str(input_payload.get("repo") or "").strip()
        repo_label = f"{owner}/{repo}" if owner and repo else (repo or "this repository")

        arch_d = architecture if isinstance(architecture, dict) else {}
        key_paths = arch_d.get("key_paths") or []
        if not isinstance(key_paths, list):
            key_paths = []
        key_paths_txt = "\n".join(f"- {p}" for p in key_paths[:10] if str(p).strip())
        summary_for_prompt = str(repo_summary or "").strip()
        if len(summary_for_prompt) > 6000:
            summary_for_prompt = summary_for_prompt[:6000] + "…"

        desc_by_repo_type = {
            "docs_tutorial": (
                "Documentation/tutorial helper draft for explaining and summarizing repo content. "
                + langs_txt + " "
                + repo_type_txt
            ).strip(),
            "library_framework": (
                "Library/framework helper draft for understanding APIs, usage patterns, and architecture. "
                + langs_txt + " "
                + repo_type_txt
            ).strip(),
            "agent_framework": (
                "Agent/system repository draft focused on orchestration, tools, and workflows. " + langs_txt + " " + repo_type_txt
            ).strip(),
            "explicit_agent": (
                "Agent/system repository draft focused on orchestration, tools, and workflows. " + langs_txt + " " + repo_type_txt
            ).strip(),
        }
        desc = desc_by_repo_type.get(repo_type, desc_by_repo_type["docs_tutorial"])

        closing_by_repo_type = {
            "docs_tutorial": (
                "Help the user understand the codebase, explain architecture decisions, "
                "summarize sections, and answer questions grounded in the actual repo content."
            ),
            "library_framework": (
                "Help the user understand the API surface, common usage, and project structure; "
                "propose examples and integration guidance grounded in the repo."
            ),
            "agent_framework": (
                "Help the user understand what the agent system does, how it is structured, "
                "and how to extend or operate it, grounded in the repo."
            ),
            "explicit_agent": (
                "Help the user understand what the agent system does, how it is structured, "
                "and how to extend or operate it, grounded in the repo."
            ),
        }
        closing = closing_by_repo_type.get(repo_type, closing_by_repo_type["docs_tutorial"])
        prompt = _build_grounded_repo_prompt(
            repo_label=repo_label,
            summary_for_prompt=summary_for_prompt,
            key_paths_txt=key_paths_txt,
            langs_txt=langs_txt,
            closing=closing,
        )
    else:
        desc = (f"Draft agent for repo. {langs_txt} {repo_type_txt}".strip() if (langs_txt or repo_type_txt) else "Draft agent from repo analysis.")
        prompt = "You are an agent generated from repo analysis. Follow the user's request."

    return {
        "recommended_bundle": bundle_id,
        "recommended_additional_tools": additional_tools,
        "draft_agent_spec": {
            "id": "draft-from-repo",
            "version": "0.1.0",
            "name": name,
            "description": desc,
            "primitive": primitive,
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": True},
            "output_schema": {"type": "object", "properties": {}, "additionalProperties": True},
            "prompt": prompt,
            "recommendation_debug": {
                **{
                    k: v
                    for k, v in (recommendation_debug if isinstance(recommendation_debug, dict) else {}).items()
                    if k != "repo_type_confidence"
                },
                "repo_type": repo_type,
                "decision_summary": (
                    f"repo_type={repo_type}; primitive={primitive}; "
                    f"bundle={bundle_id}; additional_tools={','.join(additional_tools) if additional_tools else 'none'}"
                ),
            },
        },
        # Minimal in the deterministic V1 path: satisfies validation without implying
        # a full eval suite (LLM-backed designer can supply richer cases).
        "starter_eval_cases": [
            {
                "name": "minimal_v1_smoke",
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
    *,
    github_token: Optional[str] = None,
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
        run_context = build_run_context(run_id=run_id, preset=preset, github_access_token=github_token)
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
        run_context = build_run_context(run_id=run_id, preset=preset, github_access_token=github_token)
        registry = DefaultToolRegistry()
        overview = _run_github_repo_read(registry, run_context, owner, repo, ref, "overview")
        top_tree = _run_github_repo_read(registry, run_context, owner, repo, ref, "tree", path="")

        # Improve coverage for library repos by reading tree listings for a few likely
        # structural directories (still deterministic + bounded).
        try:
            top_entries = top_tree.get("entries") or []
            top_dir_names: List[str] = []
            for e in top_entries:
                p = (e.get("path") or "").strip()
                if not p:
                    continue
                first = p.split("/", 1)[0]
                e_type = str(e.get("type") or "").lower()
                if e_type in {"tree", "dir", "directory"}:
                    top_dir_names.append(first)
            top_dir_set = {d.lower() for d in top_dir_names if d}

            # pvlib-python package dir is `pvlib`; tests dir is `tests`.
            base_pkg = str(repo).split("-")[0].lower() if repo else ""
            extra_candidates: List[str] = []
            if "tests" in top_dir_set:
                extra_candidates.append("tests")
            elif "test" in top_dir_set:
                extra_candidates.append("test")
            if "src" in top_dir_set:
                extra_candidates.append("src")
            if base_pkg and base_pkg in top_dir_set:
                extra_candidates.append(base_pkg)
            extra_candidates = extra_candidates[:3]  # hard cap

            merged_entries = list(top_entries)
            merged_truncated = bool(top_tree.get("truncated"))
            seen_paths = {e.get("path") for e in merged_entries if e.get("path")}
            for cand in extra_candidates:
                try:
                    sub_tree = _run_github_repo_read(
                        registry, run_context, owner, repo, ref, "tree", path=cand
                    )
                    sub_entries = sub_tree.get("entries") or []
                    for se in sub_entries:
                        sp = se.get("path")
                        if sp and sp not in seen_paths:
                            merged_entries.append(se)
                            seen_paths.add(sp)
                    merged_truncated = merged_truncated or bool(sub_tree.get("truncated"))
                except Exception:
                    continue

            tree = dict(top_tree)
            tree["entries"] = merged_entries
            tree["truncated"] = merged_truncated
        except Exception:
            tree = top_tree

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
        _debug_log(
            hypothesis_id="H7",
            location="app/repo_to_agent/internal_runner.py:repo_tool_discovery",
            message="Paths to inspect",
            data={"stage": "manifest_discovery_input", "file_paths_count": len(file_paths), "file_paths": file_paths[:15], "folder_paths": folder_paths},
        )
        preset = _template_to_preset(template)
        run_id = f"internal-{uuid.uuid4().hex[:12]}"
        run_context = build_run_context(run_id=run_id, preset=preset, github_access_token=github_token)
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
                if folder == "tools":
                    for e in entries:
                        p = (e.get("path") or e.get("name") or "").strip()
                        if p and (e.get("type") or "file") == "file" and p.lower().endswith(".json"):
                            try:
                                out_f = _run_github_repo_read(registry, run_context, owner, repo, ref, "file", path=p)
                                content = out_f.get("content") or ""
                                if isinstance(content, str):
                                    file_contents[p] = content
                            except Exception:
                                pass
            except Exception:
                pass
        _debug_log(
            hypothesis_id="H7",
            location="app/repo_to_agent/internal_runner.py:repo_tool_discovery",
            message="Fetched file_contents and folder_listings",
            data={
                "stage": "manifest_discovery_fetched",
                "file_contents_keys": sorted(file_contents.keys()),
                "folder_listings_keys": sorted(folder_listings.keys()),
                "tools_entries_count": len(folder_listings.get("tools") or []),
                "tools_entries_sample": [
                    {"path": e.get("path"), "type": e.get("type")}
                    for e in (folder_listings.get("tools") or [])[:8]
                ],
                "has_agent_json": "agent.json" in file_contents,
                "agent_json_len": len(file_contents.get("agent.json") or ""),
            },
        )
        discovered = discover_repo_tools_from_repo(
            scout, architecture,
            file_contents=file_contents,
            folder_listings=folder_listings,
        )
        _debug_log(
            hypothesis_id="H7",
            location="app/repo_to_agent/internal_runner.py:repo_tool_discovery",
            message="Discovery result",
            data={"stage": "manifest_discovery_output", "discovered_count": len(discovered), "discovered_tools": [{"name": t.name, "tool_type": t.tool_type, "source_path": t.source_path} for t in discovered]},
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
        _debug_log(
            hypothesis_id="H7",
            location="app/repo_to_agent/internal_runner.py:code_tool_discovery",
            message="Code paths to inspect",
            data={"stage": "code_discovery_input", "code_paths_count": len(code_paths), "code_paths": code_paths[:20]},
        )
        file_contents: Dict[str, str] = {}
        preset = _template_to_preset(template)
        run_id = f"internal-{uuid.uuid4().hex[:12]}"
        run_context = build_run_context(run_id=run_id, preset=preset, github_access_token=github_token)
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
        _debug_log(
            hypothesis_id="H7",
            location="app/repo_to_agent/internal_runner.py:code_tool_discovery",
            message="Code discovery result",
            data={"stage": "code_discovery_output", "code_tools_count": len(code_tools), "code_tools": [{"name": t.name, "tool_type": t.tool_type, "source_path": t.source_path} for t in code_tools]},
        )
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
