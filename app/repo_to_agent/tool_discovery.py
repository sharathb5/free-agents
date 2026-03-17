"""
Repo-based tool discovery: recommend bundle and additional tools from scout + architect output.

Uses deterministic heuristics over RepoScoutOutput and RepoArchitectureOutput so the
internal runner can produce data-driven recommendations instead of fixed stubs.
All recommendations are constrained to the tool and bundle catalogs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set

from app.catalog.loader import CatalogError, load_bundles_catalog, load_tools_catalog


# Path/file patterns that suggest HTTP or API usage (for http_request recommendation).
HTTP_API_PATH_KEYWORDS = (
    "api", "client", "http", "request", "fetch", "rest", "graphql",
    "requests", "httpx", "aiohttp", "urllib", "axios", "fetch",
)
# Integrations that suggest external HTTP/API usage.
HTTP_INTEGRATION_KEYWORDS = ("http", "api", "rest", "webhook", "stripe", "twilio")


def _as_list(value: Any) -> List[str]:
    """Normalize value to list of non-empty strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if x is not None and str(x).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _scout_dict(scout: Any) -> Dict[str, Any]:
    """Normalize scout to dict (accepts model or dict)."""
    if hasattr(scout, "model_dump"):
        return scout.model_dump()
    if isinstance(scout, dict):
        return scout
    return {}


def _arch_dict(architecture: Any) -> Dict[str, Any]:
    """Normalize architecture to dict (accepts model or dict)."""
    if hasattr(architecture, "model_dump"):
        return architecture.model_dump()
    if isinstance(architecture, dict):
        return architecture
    return {}


def _has_code_signals(arch: Dict[str, Any], scout: Dict[str, Any]) -> bool:
    """True if repo appears to have code (languages, entrypoints, or code-like paths)."""
    languages = _as_list(arch.get("languages") or scout.get("language_hints"))
    entrypoints = _as_list(arch.get("entrypoints"))
    key_paths = _as_list(arch.get("key_paths"))
    important = _as_list(scout.get("important_files"))
    code_extensions = (".py", ".js", ".ts", ".go", ".rs", ".java", ".rb", ".php", ".c", ".cpp", ".h")
    all_paths = key_paths + important + entrypoints
    for p in all_paths:
        p_lower = p.lower()
        if any(p_lower.endswith(ext) for ext in code_extensions):
            return True
    return bool(languages or entrypoints)


def _suggests_http_or_api(arch: Dict[str, Any], scout: Dict[str, Any]) -> bool:
    """True if repo signals suggest HTTP/API usage (recommend http_request)."""
    integrations = [x.lower() for x in _as_list(arch.get("integrations"))]
    for kw in HTTP_INTEGRATION_KEYWORDS:
        if any(kw in i for i in integrations):
            return True
    key_paths = _as_list(arch.get("key_paths")) + _as_list(scout.get("important_files"))
    for p in key_paths:
        p_lower = p.lower()
        if any(kw in p_lower for kw in HTTP_API_PATH_KEYWORDS):
            return True
    return False


def discover_tools_from_repo(
    scout: Any,
    architecture: Any,
    *,
    tools_catalog: Dict[str, Any] | None = None,
    bundles_catalog: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Recommend bundle_id and additional tool_ids from repo scout + architect output.

    Args:
        scout: RepoScoutOutput or dict with repo_summary, important_files, language_hints, etc.
        architecture: RepoArchitectureOutput or dict with languages, frameworks, integrations, key_paths, etc.
        tools_catalog: Optional pre-loaded tools catalog; if None, load_tools_catalog() is used.
        bundles_catalog: Optional pre-loaded bundles catalog; if None, load_bundles_catalog() is used.

    Returns:
        dict with:
          - bundle_id: str (catalog-valid)
          - additional_tools: list of tool_id (catalog-valid, excluding tools already in bundle)
          - rationale: list of short strings explaining the recommendation
    """
    rationale: List[str] = []
    try:
        tools_catalog = tools_catalog or load_tools_catalog()
        bundles_catalog = bundles_catalog or load_bundles_catalog()
    except CatalogError:
        return {
            "bundle_id": "no_tools_writer",
            "additional_tools": [],
            "rationale": ["Catalogs unavailable; defaulting to no_tools_writer."],
        }

    allowed_tool_ids: Set[str] = set()
    for t in (tools_catalog.get("tools") or []):
        if isinstance(t, dict) and isinstance(t.get("tool_id"), str):
            allowed_tool_ids.add(t["tool_id"].strip())

    bundles_list = bundles_catalog.get("bundles") or []
    bundle_by_id: Dict[str, Dict[str, Any]] = {}
    for b in bundles_list:
        if isinstance(b, dict) and isinstance(b.get("bundle_id"), str):
            bid = b["bundle_id"].strip()
            bundle_by_id[bid] = b

    scout_d = _scout_dict(scout)
    arch_d = _arch_dict(architecture)

    if not _has_code_signals(arch_d, scout_d):
        bid = "no_tools_writer" if "no_tools_writer" in bundle_by_id else next(iter(bundle_by_id), "no_tools_writer")
        rationale.append("Repo has no clear code signals; recommending writer with no tools.")
        return {
            "bundle_id": bid,
            "additional_tools": [],
            "rationale": rationale,
        }

    # Prefer repo_to_agent for code repos (supports github_repo_read); fallback to github_reader then no_tools_writer.
    if "repo_to_agent" in bundle_by_id:
        bundle_id = "repo_to_agent"
        rationale.append("Code repo; using repo_to_agent bundle (github_repo_read).")
    elif "github_reader" in bundle_by_id:
        bundle_id = "github_reader"
        rationale.append("Code repo; using github_reader bundle (github_repo_read).")
    else:
        bundle_id = next(iter(bundle_by_id), "no_tools_writer")
        rationale.append("Code repo; chosen bundle is first available.")

    bundle_tools: Set[str] = set()
    if bundle_id in bundle_by_id:
        bundle_tools = set(_as_list(bundle_by_id[bundle_id].get("tools")))

    additional_tools: List[str] = []
    if _suggests_http_or_api(arch_d, scout_d) and "http_request" in allowed_tool_ids:
        if "http_request" not in bundle_tools:
            additional_tools.append("http_request")
            rationale.append("Repo signals suggest HTTP/API usage; adding http_request.")

    # Only return catalog-valid tool_ids not already in the bundle
    additional_tools = [t for t in additional_tools if t in allowed_tool_ids and t not in bundle_tools]

    return {
        "bundle_id": bundle_id,
        "additional_tools": additional_tools,
        "rationale": rationale,
    }
