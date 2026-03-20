"""
Layered deterministic mapping (Part 5): signals -> capabilities -> execution types -> recommendations.

This module is shared across:
- repo-to-agent tool discovery (repo signals inferred from scout/architecture)
- catalog tool recommendations (agent signals inferred from agent text + extracted tools)

Design goals:
- Deterministic, evidence-backed scoring
- Conservative tool inclusion via thresholds
- Stable ordering (tie-break by id)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# Canonical execution types (used in debug and scoring).
EXECUTION_TYPES: Dict[str, str] = {
    "http_request": "http_request",
    "cli_command": "cli_command",
    "file_operation": "file_operation",
    "text_transform": "text_transform",
    "python_function": "python_function",
    "mcp_tool": "mcp_tool",
}

# Compact capability set (initial MVP; can be extended).
CAPABILITIES: Dict[str, str] = {
    "repo_query": "repo_query",
    "release_workflow": "release_workflow",
    "docs_editing": "docs_editing",
    "file_search": "file_search",
    "api_integration": "api_integration",
    "data_analysis": "data_analysis",
    "structured_fetch": "structured_fetch",
    "code_navigation": "code_navigation",
    "text_generation": "text_generation",
    "automation": "automation",
    # Practical capability for extracted MCP tools.
    "mcp_tool": "mcp_tool",
}


MAX_DEFAULT_BUNDLE_SCORE = 10.0

# Thresholding (tuned for the small built-in catalog and unit tests).
DEFAULT_BUNDLE_THRESHOLD = 1.0
DEFAULT_TOOL_THRESHOLD = 1.0

# Conservative allowance: only promote http_request when api_integration or structured_fetch are strong.
HTTP_PROMOTION_CAP_THRESHOLD = 0.65


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out: List[str] = []
        for v in value:
            if v is None:
                continue
            s = str(v).strip()
            if s:
                out.append(s)
        return out
    s = str(value).strip()
    return [s] if s else []


def _get_attr_or_key(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _normalize_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _contains_any(haystack: str, needles: List[str]) -> Tuple[bool, List[str]]:
    matched: List[str] = []
    for n in needles:
        if n and n in haystack:
            matched.append(n)
    return (len(matched) > 0), matched


def _score_from_presence(has: bool, score: float, evidence: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "score": score if has else 0.0,
        "evidence": evidence or [],
    }


def _sorted_by_score_then_id(items: List[Tuple[str, float]]) -> List[str]:
    return [tid for tid, _ in sorted(items, key=lambda x: (-x[1], x[0]))]


def _infer_detected_signals_from_agent(agent_input: Any) -> Dict[str, List[str]]:
    """
    Stage 1: raw agent text -> detected signals evidence.
    """
    name = _normalize_str(_get_attr_or_key(agent_input, "name", ""))
    description = _normalize_str(_get_attr_or_key(agent_input, "description", ""))
    primitive = _normalize_str(_get_attr_or_key(agent_input, "primitive", ""))
    prompt = _normalize_str(_get_attr_or_key(agent_input, "prompt", ""))
    extracted_tool_ids = _as_list(_get_attr_or_key(agent_input, "extracted_tool_ids", []))

    haystack = " ".join([name, description, primitive, prompt]).strip()

    detected: Dict[str, List[str]] = {}

    def add(signal: str, evidence: List[str]) -> None:
        if not evidence:
            return
        detected.setdefault(signal, [])
        detected[signal].extend(evidence)

    # Filesystem / code navigation.
    filesystem_keywords = [
        "file",
        "filesystem",
        "grep",
        "search",
        "code navigation",
        "navigate code",
        "repo understanding",
        "repository understanding",
        "terminal",
        "shell",
        "glob",
        "code",
        "search retrieval",
    ]
    has_fs, match_fs = _contains_any(haystack, filesystem_keywords)
    if has_fs:
        add("file_search", match_fs)
        add("code_navigation", match_fs)

    # GitHub / repo query.
    github_keywords = [
        "github",
        "pull request",
        "pull-request",
        "issues",
        "repository",
        "repo ",
        "repo_",
        "repo",
    ]
    has_gh, match_gh = _contains_any(haystack, github_keywords)
    if has_gh:
        add("repo_query", match_gh)

    # Release/workflows automation.
    release_keywords = [
        "release",
        "changelog",
        "tag",
        "workflow",
        "workflows",
        "actions",
        "ci",
        "pipeline",
    ]
    has_rel, match_rel = _contains_any(haystack, release_keywords)
    if has_rel:
        add("release_workflow", match_rel)

    automation_keywords = ["script", "scripts", "makefile", "make ", "generate-", "cron", "automation"]
    has_auto, match_auto = _contains_any(haystack, automation_keywords)
    if has_auto:
        add("automation", match_auto)

    # Docs editing / text generation.
    docs_keywords = ["docs", "documentation", "readme", "markdown", "generate docs", "docs generation"]
    has_docs, match_docs = _contains_any(haystack, docs_keywords)
    if has_docs:
        add("docs_editing", match_docs)
        add("text_generation", match_docs)

    # Summarization / transform often implies text generation.
    summarization_keywords = ["summarize", "summary", "summaries", "condense", "shorten", "paraphrase", "tl;dr", "rewrite"]
    if "transform" in primitive or _contains_any(haystack, summarization_keywords)[0]:
        add("text_generation", ["transform_or_summarize"])

    # API / structured fetch.
    api_keywords = ["api", "http", "request", "fetch", "rest", "graphql", "webhook", "axios", "httpx", "aiohttp", "urllib"]
    has_api, match_api = _contains_any(haystack, api_keywords)
    if has_api:
        add("api_integration", match_api)

    structured_keywords = ["structured", "schema", "json", "extract", "tool call", "structured fetch"]
    has_struct, match_struct = _contains_any(haystack, structured_keywords)
    if has_struct:
        add("structured_fetch", match_struct)

    # Data analysis.
    data_keywords = ["data", "csv", "pandas", "analysis", "analyze csv", "data analysis"]
    has_data, match_data = _contains_any(haystack, data_keywords)
    if has_data:
        add("data_analysis", match_data)

    # MCP tool: detected via extracted tool ids.
    if extracted_tool_ids:
        mcp_matches = [tid for tid in extracted_tool_ids if "mcp" in tid.lower()]
        if mcp_matches:
            add("mcp_tool", mcp_matches)

    # Ensure deterministic lists (unique while preserving order).
    for k, v in list(detected.items()):
        seen: set[str] = set()
        uniq: List[str] = []
        for e in v:
            if e in seen:
                continue
            seen.add(e)
            uniq.append(e)
        detected[k] = uniq

    return detected


def infer_capabilities_from_agent_text(agent_input: Any) -> Dict[str, Dict[str, Any]]:
    """
    Stage 2: detected signals -> inferred capabilities (score + evidence).
    """
    detected = _infer_detected_signals_from_agent(agent_input)

    def cap(name: str, weight: float) -> Dict[str, Any]:
        evidence = detected.get(name, [])
        return {"score": (weight if evidence else 0.0), "evidence": evidence}

    # Weights: tuned to be "confident but conservative".
    caps: Dict[str, Dict[str, Any]] = {
        "repo_query": cap("repo_query", 0.7),
        "release_workflow": cap("release_workflow", 0.95),
        "docs_editing": cap("docs_editing", 0.9),
        "file_search": cap("file_search", 0.85),
        "api_integration": cap("api_integration", 0.9),
        "data_analysis": cap("data_analysis", 0.9),
        "structured_fetch": cap("structured_fetch", 0.85),
        "code_navigation": cap("code_navigation", 0.75),
        "text_generation": cap("text_generation", 0.8),
        "automation": cap("automation", 0.85),
        "mcp_tool": cap("mcp_tool", 0.95),
    }
    return caps


def detect_signals_from_agent_text(agent_input: Any) -> Dict[str, List[str]]:
    """
    Stage 1 (public): agent text -> detected signals evidence.

    This is exposed for debug / transparency.
    """
    return _infer_detected_signals_from_agent(agent_input)


def infer_execution_types_from_capabilities(capabilities: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Stage 3: inferred capabilities -> inferred execution types (score + evidence).
    """
    def cap_score(name: str) -> float:
        v = capabilities.get(name) or {}
        s = v.get("score")
        return float(s) if isinstance(s, (int, float)) else 0.0

    def cap_evidence(name: str) -> List[str]:
        v = capabilities.get(name) or {}
        ev = v.get("evidence") or []
        return [str(x) for x in ev if str(x).strip()]

    # Weighted mapping per plan.
    http_s = 0.25 * cap_score("repo_query") + 0.85 * cap_score("api_integration") + 0.8 * cap_score("structured_fetch")
    file_op_s = 0.9 * cap_score("file_search") + 0.8 * cap_score("code_navigation")
    text_transform_s = 0.85 * cap_score("docs_editing") + 0.75 * cap_score("text_generation")
    cli_s = 0.9 * cap_score("release_workflow") + 0.95 * cap_score("automation")
    py_s = 0.95 * cap_score("data_analysis")
    mcp_s = 0.95 * cap_score("mcp_tool")

    execution: Dict[str, Dict[str, Any]] = {
        "http_request": {"score": http_s, "evidence": cap_evidence("api_integration") + cap_evidence("structured_fetch")},
        "file_operation": {"score": file_op_s, "evidence": cap_evidence("file_search") + cap_evidence("code_navigation")},
        "text_transform": {
            "score": text_transform_s,
            "evidence": cap_evidence("docs_editing") + cap_evidence("text_generation"),
        },
        "cli_command": {"score": cli_s, "evidence": cap_evidence("release_workflow") + cap_evidence("automation")},
        "python_function": {"score": py_s, "evidence": cap_evidence("data_analysis")},
        "mcp_tool": {"score": mcp_s, "evidence": cap_evidence("mcp_tool")},
    }

    # Normalize evidence lists.
    for k, v in execution.items():
        ev = v.get("evidence") or []
        seen: set[str] = set()
        uniq: List[str] = []
        for e in ev:
            e_s = str(e)
            if e_s in seen or not e_s.strip():
                continue
            seen.add(e_s)
            uniq.append(e_s)
        v["evidence"] = uniq
    return execution


def _infer_detected_signals_from_repo(scout: Any, architecture: Any) -> Dict[str, List[str]]:
    """
    Stage 1 for repo-to-agent:
    scout/architecture -> detected signals evidence based on file paths and integrations.
    """
    scout_d = scout.model_dump() if hasattr(scout, "model_dump") else (scout or {}) if isinstance(scout, dict) else {}
    arch_d = architecture.model_dump() if hasattr(architecture, "model_dump") else (architecture or {}) if isinstance(architecture, dict) else {}

    important = _as_list(scout_d.get("important_files") or [])
    key_paths = _as_list(arch_d.get("key_paths") or [])
    entrypoints = _as_list(arch_d.get("entrypoints") or [])
    integrations = [str(x).lower() for x in _as_list(arch_d.get("integrations") or [])]

    all_paths = important + key_paths + entrypoints
    all_lower = [p.lower() for p in all_paths if p]

    detected: Dict[str, List[str]] = {}

    def add(signal: str, evidence: List[str]) -> None:
        if not evidence:
            return
        detected.setdefault(signal, [])
        detected[signal].extend(evidence)

    # Code-like vs docs vs scripts.
    code_exts = [".py", ".js", ".ts", ".go", ".rs", ".java", ".rb", ".php", ".c", ".cpp", ".h", ".cs"]
    has_code = any(any(p.endswith(ext) for ext in code_exts) for p in all_lower) or bool(_as_list(arch_d.get("languages") or []))
    if has_code:
        # For code repos, we typically need to query repo contents to navigate.
        add("repo_query", ["code_repo"])
        add("code_navigation", ["code_paths_present"])
        add("file_search", ["code_paths_present"])

    # Docs-only / docs editing.
    docs_paths = [p for p in all_lower if "/docs/" in p or p.startswith("docs/") or p.endswith(".md") or p.endswith(".markdown") or p.endswith("readme.md")]
    if docs_paths:
        add("docs_editing", [docs_paths[0]])
        add("text_generation", ["docs_text_generation"])
        add("file_search", ["docs_file_search"])

    # Release / changelog / workflows.
    # Keep markers specific enough to avoid false positives like "notes.txt".
    release_markers = ["changelog", "release", "release-notes", "release_notes", ".github/workflows", "workflows", "actions", "ci", "tag"]
    matched_release = [m for m in release_markers if any(m in p for p in all_lower) or m in integrations]
    if matched_release:
        add("release_workflow", matched_release)
        add("automation", ["workflow_or_release_markers"])
        add("repo_query", ["release_or_changelog_repo"])

    # Script-heavy automation.
    automation_markers = ["scripts/", "makefile", "generate-", ".sh", ".bash", "bin/", "entrypoint", "dockerfile"]
    matched_auto = [m for m in automation_markers if any(m.lower() in p for p in all_lower)]
    if matched_auto:
        add("automation", matched_auto)
        add("repo_query", ["automation_repo"])

    # HTTP/API.
    # Avoid over-triggering on generic substrings like "api" in unrelated folder names.
    # Prefer path-segment-ish markers (api/, /api/) and concrete library/framework keywords.
    api_markers = ["api/", "/api/", "http", "request", "fetch", "rest", "graphql", "webhook", "axios", "httpx", "aiohttp", "urllib", "requests"]
    matched_api: List[str] = []
    for m in api_markers:
        if any(m in p for p in all_lower) or m.strip("/").lower() in integrations:
            matched_api.append(m)
    if matched_api:
        add("api_integration", matched_api)
        add("structured_fetch", ["api_or_structured_fetch"])
        add("repo_query", ["api_repo"])

    # Data analysis.
    data_markers = [".csv", "pandas", "data analysis", "analyze csv", "data/"]
    matched_data = [m for m in data_markers if any(m.lower() in p for p in all_lower)]
    if matched_data:
        add("data_analysis", matched_data)
        add("repo_query", ["data_analysis_repo"])

    # Deterministic evidence lists.
    for k, v in list(detected.items()):
        seen: set[str] = set()
        uniq: List[str] = []
        for e in v:
            e_s = str(e).strip()
            if not e_s or e_s in seen:
                continue
            seen.add(e_s)
            uniq.append(e_s)
        detected[k] = uniq

    return detected


def infer_capabilities_from_repo(scout: Any, architecture: Any) -> Dict[str, Dict[str, Any]]:
    """
    Stage 2 for repo-to-agent:
    detected repo signals -> inferred capabilities (score + evidence).
    """
    detected = _infer_detected_signals_from_repo(scout, architecture)

    def cap(name: str, weight: float) -> Dict[str, Any]:
        evidence = detected.get(name, [])
        return {"score": (weight if evidence else 0.0), "evidence": evidence}

    return {
        "repo_query": cap("repo_query", 0.7),
        "release_workflow": cap("release_workflow", 0.95),
        "docs_editing": cap("docs_editing", 0.9),
        "file_search": cap("file_search", 0.85),
        "api_integration": cap("api_integration", 0.9),
        "data_analysis": cap("data_analysis", 0.9),
        "structured_fetch": cap("structured_fetch", 0.85),
        "code_navigation": cap("code_navigation", 0.75),
        "text_generation": cap("text_generation", 0.8),
        "automation": cap("automation", 0.85),
        "mcp_tool": cap("mcp_tool", 0.95),
    }


def detect_signals_from_repo(scout: Any, architecture: Any) -> Dict[str, List[str]]:
    """
    Stage 1 (public): scout/architecture -> detected repo signals evidence.
    """
    return _infer_detected_signals_from_repo(scout, architecture)


def _execution_all_scores(execution_types: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for etype in EXECUTION_TYPES:
        v = execution_types.get(etype) or {}
        s = v.get("score")
        out[etype] = float(s) if isinstance(s, (int, float)) else 0.0
    return out


def _tool_alignment_score(
    tool: Any,
    execution_types: Dict[str, Dict[str, Any]],
    capabilities: Dict[str, Dict[str, Any]],
    extracted_tool_ids: List[str],
) -> Dict[str, Any]:
    tid = str(_get_attr_or_key(tool, "tool_id", "") or _get_attr_or_key(tool, "id", "") or "").strip()
    category = _normalize_str(_get_attr_or_key(tool, "category", "") or "")
    description = _normalize_str(_get_attr_or_key(tool, "description", "") or "")
    tool_text = " ".join([tid.lower(), category, description])

    caps = {k: float((capabilities.get(k) or {}).get("score") or 0.0) for k in CAPABILITIES.keys()}
    et_scores = _execution_all_scores(execution_types)

    if tid and tid in extracted_tool_ids:
        return {"score": 3.0, "signals": ["extracted_tool_preserved", f"extracted:{tid}"]}

    signals: List[str] = []
    score = 0.0
    tool_overlap_factor = 0.55

    # http_request tool is special-cased with conservative promotion.
    if tid == "http_request" or "http" in tool_text or "web" in category:
        http_base = et_scores.get("http_request", 0.0)
        allow = max(caps.get("api_integration", 0.0), caps.get("structured_fetch", 0.0)) >= HTTP_PROMOTION_CAP_THRESHOLD
        if allow and http_base > 0:
            score += 1.25 * http_base
            signals.append("http_request_alignment")
        else:
            score += 0.05 * http_base
            if http_base > 0:
                signals.append("http_request_conservative_denied")

    # GitHub repo read acts as "repo query" + "file access" capability.
    if tid == "github_repo_read" or "github" in category or "github" in description:
        github_base = max(et_scores.get("file_operation", 0.0), et_scores.get("cli_command", 0.0), et_scores.get("http_request", 0.0))
        # Only add when repo query/file ops are clearly inferred.
        file_clear = max(caps.get("file_search", 0.0), caps.get("code_navigation", 0.0), caps.get("repo_query", 0.0)) >= 0.6
        if file_clear and github_base > 0:
            score += 1.1 * github_base
            signals.append("github_repo_read_alignment")
        else:
            score += 0.1 * github_base

    # Generic file/search tooling.
    if any(k in tid.lower() for k in ["glob_search", "grep_search", "file_tool"]) or any(
        k in tool_text for k in ["search", "grep", "glob", "read file", "write file", "filesystem", "file access"]
    ):
        score += 1.05 * et_scores.get("file_operation", 0.0)
        if et_scores.get("file_operation", 0.0) > 0:
            signals.append("file_operation_alignment")

    # Generic shell/CLI tooling.
    if any(k in tid.lower() for k in ["shell_tool", "cli", "make", "tag_release"]) or any(k in tool_text for k in ["shell", "make ", "tag ", "release", "workflow"]):
        score += 1.0 * et_scores.get("cli_command", 0.0)
        if et_scores.get("cli_command", 0.0) > 0:
            signals.append("cli_command_alignment")

    # Text transform / writing tooling.
    if "summarize" in tool_text or "transform" in tool_text or "rewrite" in tool_text or "paraphrase" in tool_text:
        score += 1.0 * et_scores.get("text_transform", 0.0)
        if et_scores.get("text_transform", 0.0) > 0:
            signals.append("text_transform_alignment")

    # Python/data analysis tooling.
    if "csv" in tool_text or "data analysis" in tool_text or "pandas" in tool_text or "python" in tool_text:
        score += 1.0 * et_scores.get("python_function", 0.0)
        if et_scores.get("python_function", 0.0) > 0:
            signals.append("python_function_alignment")

    # MCP.
    if tid and "mcp" in tid.lower():
        score += 1.0 * et_scores.get("mcp_tool", 0.0)
        if et_scores.get("mcp_tool", 0.0) > 0:
            signals.append("mcp_tool_alignment")

    return {"score": float(score), "signals": signals}


def _bundle_alignment_score(
    bundle: Any,
    available_tools: List[Any],
    execution_types: Dict[str, Dict[str, Any]],
    capabilities: Dict[str, Dict[str, Any]],
    *,
    extracted_tool_ids: List[str],
    bundle_threshold_override: Optional[float] = None,
) -> Dict[str, Any]:
    bundle_id = str(_get_attr_or_key(bundle, "bundle_id", "") or "").strip()
    category = _normalize_str(_get_attr_or_key(bundle, "category", "") or "")
    title = _normalize_str(_get_attr_or_key(bundle, "title", "") or "")
    description = _normalize_str(_get_attr_or_key(bundle, "description", "") or "")
    tools_in_bundle = _as_list(_get_attr_or_key(bundle, "tools", []) or [])

    et_scores = _execution_all_scores(execution_types)
    caps = {k: float((capabilities.get(k) or {}).get("score") or 0.0) for k in CAPABILITIES.keys()}

    # Build tool alignment scores for tools present in this bundle.
    tool_score_by_id: Dict[str, float] = {}
    for t in available_tools:
        tid = str(_get_attr_or_key(t, "tool_id", "") or "").strip()
        if not tid:
            continue
        if tid not in tools_in_bundle:
            continue
        al = _tool_alignment_score(t, execution_types, capabilities, extracted_tool_ids)
        tool_score_by_id[tid] = float(al.get("score") or 0.0)

    tool_scores_sorted = sorted(tool_score_by_id.items(), key=lambda kv: (-kv[1], kv[0]))
    top_scores = [s for _, s in tool_scores_sorted[:3]]

    signals: List[str] = []
    score = 0.0
    tool_overlap_factor = 0.55

    # Known catalog bundle ids (special cases).
    if bundle_id == "no_tools_writer":
        score += 1.2 * et_scores.get("text_transform", 0.0) + 0.25 * et_scores.get("file_operation", 0.0)
        if et_scores.get("text_transform", 0.0) > 0:
            signals.append("no_tools_writer_text_transform_dominant")
    elif bundle_id in ("github_reader", "repo_to_agent"):
        github_base = max(et_scores.get("file_operation", 0.0), et_scores.get("cli_command", 0.0))
        if github_base > 0:
            score += 1.1 * github_base
            signals.append("github_bundle_repo_access")
        # Prefer repo_to_agent slightly when repo_query or release_workflow are strong.
        if bundle_id == "repo_to_agent":
            score += 0.15 * caps.get("repo_query", 0.0) + 0.1 * caps.get("release_workflow", 0.0)
    elif bundle_id == "research_basic":
        allow = max(caps.get("api_integration", 0.0), caps.get("structured_fetch", 0.0)) >= HTTP_PROMOTION_CAP_THRESHOLD
        if allow:
            http_s = et_scores.get("http_request", 0.0)
            file_s = et_scores.get("file_operation", 0.0)
            dominance = http_s - file_s
            # Prefer repo-centric bundles when code/file ops are also strongly inferred.
            if dominance >= 0.4:
                score += 1.3 * http_s
                signals.append("research_basic_http_dominant")
            else:
                score += 0.65 * http_s
                signals.append("research_basic_http_not_dominant")
                tool_overlap_factor = 0.25
        else:
            score += 0.05 * et_scores.get("http_request", 0.0)

    # Generic fallback scoring for non-catalog bundle ids (unit tests pass custom bundle ids).
    if score <= 0:
        bundle_text = " ".join([category, title, description])
        if any(k in bundle_text for k in ["filesystem", "file", "search", "navigation", "code"]):
            score += 1.1 * et_scores.get("file_operation", 0.0)
            score += 0.15 * et_scores.get("cli_command", 0.0)
            signals.append("filesystem_bundle_alignment")
        if any(k in bundle_text for k in ["github", "git"]):
            score += 1.05 * et_scores.get("cli_command", 0.0) + 0.25 * et_scores.get("file_operation", 0.0)
            signals.append("github_bundle_alignment")
        if any(k in bundle_text for k in ["writing", "write", "text", "summar"]):
            score += 1.1 * et_scores.get("text_transform", 0.0)
            signals.append("writing_bundle_alignment")
        if any(k in bundle_text for k in ["data", "analysis"]):
            score += 1.05 * et_scores.get("python_function", 0.0)
            signals.append("data_bundle_alignment")

    # Add tool overlap signals (deterministic).
    if top_scores:
        score += tool_overlap_factor * sum(top_scores)

    # Preserve extracted tool ids already present in bundle.
    for tid in extracted_tool_ids:
        if tid in tools_in_bundle:
            score += 1.4
            signals.append(f"contains_extracted:{tid}")

    # Stable cap.
    score = float(min(MAX_DEFAULT_BUNDLE_SCORE, max(0.0, score)))

    return {
        "score": score,
        "signals": signals + [f"top_tools={','.join(str(s) for s in top_scores)}"],
    }


def recommend_bundles_and_tools(
    *,
    detected_signals: Dict[str, List[str]],
    capabilities: Dict[str, Dict[str, Any]],
    execution_types: Dict[str, Dict[str, Any]],
    available_tools: List[Any],
    available_bundles: List[Any],
    extracted_tool_ids: Optional[List[str]] = None,
    max_additional_tools: int = 8,
    bundle_threshold: float = DEFAULT_BUNDLE_THRESHOLD,
    tool_threshold: float = DEFAULT_TOOL_THRESHOLD,
) -> Dict[str, Any]:
    """
    Stage 4: execution types -> deterministic bundle + tool recommendations.
    """
    extracted = [str(t).strip() for t in (extracted_tool_ids or []) if str(t).strip()]

    # Compute tool scores first (used for bundle scoring and additional tool selection).
    tool_scores: Dict[str, Dict[str, Any]] = {}
    for t in available_tools:
        tid = str(_get_attr_or_key(t, "tool_id", "") or "").strip()
        if not tid:
            continue
        tool_scores[tid] = _tool_alignment_score(t, execution_types, capabilities, extracted)

    bundle_scores: Dict[str, Dict[str, Any]] = {}
    for b in available_bundles:
        bid = str(_get_attr_or_key(b, "bundle_id", "") or "").strip()
        if not bid:
            continue
        bundle_scores[bid] = _bundle_alignment_score(
            b,
            available_tools=available_tools,
            execution_types=execution_types,
            capabilities=capabilities,
            extracted_tool_ids=extracted,
        )

    # Choose bundle: max score then stable tie-break by id.
    best_bid: Optional[str] = None
    best_score = -1.0
    for bid, details in bundle_scores.items():
        s = float(details.get("score") or 0.0)
        if s > best_score or (s == best_score and (best_bid is None or bid < best_bid)):
            best_score = s
            best_bid = bid

    chosen_bundle_id: Optional[str] = best_bid
    used_conservative_fallback = False
    if chosen_bundle_id is None or best_score < bundle_threshold:
        # Conservative fallback: pick no_tools_writer if present, else None.
        used_conservative_fallback = True
        for b in available_bundles:
            bid = str(_get_attr_or_key(b, "bundle_id", "") or "").strip()
            if bid == "no_tools_writer":
                chosen_bundle_id = "no_tools_writer"
                break
        if chosen_bundle_id == "no_tools_writer":
            # keep selected even if below threshold; we need deterministic fallback for UI/tests.
            pass
        elif chosen_bundle_id is None:
            chosen_bundle_id = None

    chosen_bundle_tools: List[str] = []
    if chosen_bundle_id:
        for b in available_bundles:
            if str(_get_attr_or_key(b, "bundle_id", "") or "").strip() == chosen_bundle_id:
                chosen_bundle_tools = _as_list(_get_attr_or_key(b, "tools", []) or [])
                break

    # Additional tools: include extracted first (preserve), then aligned by threshold.
    already = set(chosen_bundle_tools)
    additional_tool_scores: List[Tuple[str, float]] = []
    for tid, details in tool_scores.items():
        if tid in already:
            continue
        additional_tool_scores.append((tid, float(details.get("score") or 0.0)))

    # Ensure extracted tools always considered.
    for tid in extracted:
        if tid in tool_scores and tid not in already and tid not in [x for x, _ in additional_tool_scores]:
            additional_tool_scores.append((tid, 3.0))

    additional_tool_ids: List[str] = []

    # Sort stable by (-score, tool_id).
    additional_tool_scores_sorted = sorted(additional_tool_scores, key=lambda kv: (-kv[1], kv[0]))
    for tid, s in additional_tool_scores_sorted:
        if len(additional_tool_ids) >= max_additional_tools:
            break
        if tid in extracted:
            additional_tool_ids.append(tid)
            continue
        if s < tool_threshold:
            continue
        additional_tool_ids.append(tid)

    # Safe fallback: do not add http_request unless api/structured is strong.
    if "http_request" in additional_tool_ids:
        api_s = float((capabilities.get("api_integration") or {}).get("score") or 0.0)
        struct_s = float((capabilities.get("structured_fetch") or {}).get("score") or 0.0)
        if max(api_s, struct_s) < HTTP_PROMOTION_CAP_THRESHOLD:
            additional_tool_ids = [tid for tid in additional_tool_ids if tid != "http_request"]

    # Safe fallback: only add github_repo_read when file_search/code_navigation/repo_query is clearly inferred.
    if "github_repo_read" in additional_tool_ids:
        file_s = float((capabilities.get("file_search") or {}).get("score") or 0.0)
        code_s = float((capabilities.get("code_navigation") or {}).get("score") or 0.0)
        repo_s = float((capabilities.get("repo_query") or {}).get("score") or 0.0)
        if max(file_s, code_s, repo_s) < 0.6:
            additional_tool_ids = [tid for tid in additional_tool_ids if tid != "github_repo_read"]

    # Docs-only dead-zone avoidance: if bundle is no_tools_writer but docs/file_search evidence exists,
    # still allow github_repo_read as an additional tool for reading docs.
    if chosen_bundle_id == "no_tools_writer":
        docs_s = float((capabilities.get("docs_editing") or {}).get("score") or 0.0)
        file_s = float((capabilities.get("file_search") or {}).get("score") or 0.0)
        if max(docs_s, file_s) >= 0.65 and "github_repo_read" in tool_scores and "github_repo_read" not in already:
            additional_tool_ids = ["github_repo_read"] + [t for t in additional_tool_ids if t != "github_repo_read"]
            additional_tool_ids = additional_tool_ids[:max_additional_tools]

    # Rationale: keep it compact but debug-friendly.
    rationale: List[str] = []
    if capabilities.get("file_search") and capabilities["file_search"].get("score", 0) > 0:
        rationale.append("Detected filesystem/search capability from evidence.")
    if capabilities.get("code_navigation") and capabilities["code_navigation"].get("score", 0) > 0:
        rationale.append("Evidence suggests code navigation or repository browsing needs.")
    if capabilities.get("release_workflow") and capabilities["release_workflow"].get("score", 0) > 0:
        rationale.append("Release/changelog/workflow intent detected.")
    if capabilities.get("docs_editing") and capabilities["docs_editing"].get("score", 0) > 0:
        rationale.append("Docs editing/writing intent detected; preferring lightweight writer bundles.")
    if capabilities.get("text_generation") and capabilities["text_generation"].get("score", 0) > 0:
        rationale.append("Detected transform/text-generation intent; preferring lightweight writer bundles.")
    if capabilities.get("api_integration") and capabilities["api_integration"].get("score", 0) > 0:
        rationale.append("API/HTTP integration intent detected; may recommend http_request when safe.")
    if capabilities.get("data_analysis") and capabilities["data_analysis"].get("score", 0) > 0:
        rationale.append("Data analysis intent detected; may recommend python-style tooling.")
    if capabilities.get("mcp_tool") and capabilities["mcp_tool"].get("score", 0) > 0:
        rationale.append("MCP tool intent detected via extracted tool ids.")

    if chosen_bundle_id:
        if used_conservative_fallback:
            rationale.append("No bundle met the minimum score; using conservative fallback.")
        else:
            rationale.append(f"Selected bundle '{chosen_bundle_id}' via deterministic scoring.")
    else:
        rationale.append("No bundle met the minimum score; using conservative fallback.")

    if additional_tool_ids:
        rationale.append(f"Selected additional tools: {', '.join(additional_tool_ids)}.")
    else:
        rationale.append("No additional tools strongly matched the inferred execution types.")

    debug = {
        "detected_signals": detected_signals,
        "inferred_capabilities": capabilities,
        "inferred_execution_types": execution_types,
        "bundle_scores": bundle_scores,
        "tool_scores": tool_scores,
    }

    return {
        "bundle_id": chosen_bundle_id,
        "additional_tool_ids": additional_tool_ids,
        "rationale": rationale,
        "debug": debug,
    }

