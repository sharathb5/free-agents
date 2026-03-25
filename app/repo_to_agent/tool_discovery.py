"""
Repo-based tool discovery: recommend bundle and additional tools from scout + architect output.

Uses deterministic heuristics over RepoScoutOutput and RepoArchitectureOutput so the
internal runner can produce data-driven recommendations instead of fixed stubs.
All recommendations are constrained to the tool and bundle catalogs.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Set

_log = logging.getLogger(__name__)

from app.catalog.loader import CatalogError, load_bundles_catalog, load_tools_catalog
from app.recommendations.layered_mapping import (
    detect_signals_from_repo,
    infer_capabilities_from_repo,
    infer_execution_types_from_capabilities,
    recommend_bundles_and_tools,
)

from .repo_classifier import classify_repo_type


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
    discovered_repo_tools: Any | None = None,
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
          - debug: dict with signals/capabilities/execution types and scoring details
    """
    try:
        tools_catalog = tools_catalog or load_tools_catalog()
        bundles_catalog = bundles_catalog or load_bundles_catalog()
    except CatalogError:
        return {
            "bundle_id": "no_tools_writer",
            "additional_tools": [],
            "rationale": ["Catalogs unavailable; defaulting to no_tools_writer."],
            "debug": {},
        }

    available_tools: List[Dict[str, Any]] = [
        t for t in (tools_catalog.get("tools") or []) if isinstance(t, dict) and isinstance(t.get("tool_id"), str)
    ]
    available_bundles: List[Dict[str, Any]] = [
        b for b in (bundles_catalog.get("bundles") or []) if isinstance(b, dict) and isinstance(b.get("bundle_id"), str)
    ]

    allowed_tool_ids: Set[str] = {str(t.get("tool_id")).strip() for t in available_tools if t.get("tool_id")}

    detected_signals = detect_signals_from_repo(scout, architecture)
    capabilities = infer_capabilities_from_repo(scout, architecture)
    execution_types = infer_execution_types_from_capabilities(capabilities)

    # Repo type is an advisory bias only (never overrides strong evidence).
    scout_d = _scout_dict(scout)
    arch_d = _arch_dict(architecture)
    all_paths = _as_list(scout_d.get("important_files")) + _as_list(arch_d.get("key_paths")) + _as_list(arch_d.get("entrypoints"))
    paths_lower = [p.lower() for p in all_paths]

    # Normalize discovered_repo_tools to a list (accept dict/list/None).
    tools_list: list[Any] | None = None
    if isinstance(discovered_repo_tools, list):
        tools_list = discovered_repo_tools
    elif discovered_repo_tools:
        # If caller passed a single tool object/dict, wrap it.
        tools_list = [discovered_repo_tools]

    if os.getenv("REPO_CLASSIFIER_DEBUG", "").strip().lower() in ("1", "true", "yes"):
        try:
            print(
                "tool_discovery_classifier_inputs",
                {
                    "important_files_count": len(_as_list(scout_d.get("important_files"))),
                    "key_paths_count": len(_as_list(arch_d.get("key_paths"))),
                    "entrypoints_count": len(_as_list(arch_d.get("entrypoints"))),
                    "discovered_repo_tools_count": len(tools_list or []),
                },
            )
        except Exception:
            pass
    repo_type_result = classify_repo_type(
        scout_d,
        arch_d,
        has_agent_json=("agent.json" in paths_lower),
        has_system_prompt=("prompts/system_prompt.md" in paths_lower),
        discovered_repo_tools=tools_list,
    )

    # Bridge extracted repo structure -> catalog tool_ids.
    # Keep this minimal and safe: we only synthesize evidence for tools that already exist in the catalog.
    extracted_tool_ids: List[str] = []
    has_code = _has_code_signals(arch_d, scout_d)
    suggests_http = _suggests_http_or_api(arch_d, scout_d)
    if suggests_http and "http_request" in allowed_tool_ids:
        extracted_tool_ids.append("http_request")
    # For non-docs repos with code/automation/library/agent purpose, reading the repo is typically required.
    if repo_type_result.repo_type in {"automation_scripts", "library_framework", "explicit_agent", "agent_framework"} or (
        has_code and repo_type_result.repo_type != "docs_tutorial"
    ):
        if "github_repo_read" in allowed_tool_ids:
            extracted_tool_ids.append("github_repo_read")
    extracted_tool_ids = list(dict.fromkeys(extracted_tool_ids))

    rec = recommend_bundles_and_tools(
        detected_signals=detected_signals,
        capabilities=capabilities,
        execution_types=execution_types,
        available_tools=available_tools,
        available_bundles=available_bundles,
        extracted_tool_ids=extracted_tool_ids,
        max_additional_tools=8,
    )

    bundle_id = str(rec.get("bundle_id") or "no_tools_writer").strip() or "no_tools_writer"
    pre_bias_bundle_id = bundle_id
    additional_tools: List[str] = [
        str(tid).strip() for tid in (rec.get("additional_tool_ids") or []) if str(tid).strip()
    ]

    # Bias bundle choice based on repo_type when scores are close.
    # This avoids "generic fallback everywhere" without overriding strong evidence.
    target_by_repo_type = {
        "docs_tutorial": "repo_to_agent",
        "automation_scripts": "repo_to_agent",
        "explicit_agent": "repo_to_agent",
        "agent_framework": "repo_to_agent",
        "library_framework": "repo_to_agent",
    }
    target = target_by_repo_type.get(repo_type_result.repo_type)
    # Release/workflow repos can look docs-heavy (e.g. CHANGELOG + workflows)
    # but still need repo-centric bundles; avoid forcing docs bundle in that case.
    if (
        repo_type_result.repo_type == "docs_tutorial"
        and float((capabilities.get("release_workflow") or {}).get("score") or 0.0) >= 0.8
    ):
        target = None
    debug = rec.get("debug") or {}
    bundle_scores = (debug.get("bundle_scores") or {}) if isinstance(debug, dict) else {}
    bundle_bias_applied = False
    bundle_bias_reason = ""
    if target and isinstance(bundle_scores, dict) and target in bundle_scores and bundle_id in bundle_scores:
        try:
            chosen_s = float((bundle_scores.get(bundle_id) or {}).get("score") or 0.0)
            target_s = float((bundle_scores.get(target) or {}).get("score") or 0.0)
            # Some tutorial repos contain "API" chapter names that can over-score
            # research bundles. Widen docs tie-break only when tutorial evidence is
            # explicit to avoid affecting generic docs/code repositories.
            has_strong_tutorial_evidence = any(
                ev in {"text:tutorial_terms", "shape:docs_only"}
                for ev in (repo_type_result.evidence or [])
            )
            tie_break_margin = (
                1.0
                if repo_type_result.repo_type == "docs_tutorial" and has_strong_tutorial_evidence
                else 0.2
            )
            # Only switch when target is close to (or better than) chosen.
            if target_s + tie_break_margin >= chosen_s:
                bundle_id = target
                bundle_bias_applied = pre_bias_bundle_id != bundle_id
                bundle_bias_reason = (
                    f"repo_type target={target} score={target_s:.2f} close_to chosen={pre_bias_bundle_id} "
                    f"score={chosen_s:.2f} margin={tie_break_margin:.2f}"
                )
        except Exception:
            pass
    # Keep docs/tutorial demos consistent: even with incidental API keywords in
    # lesson names, prefer the docs-oriented bundle when classifier confidence
    # already indicates docs/tutorial intent.
    has_strong_tutorial_evidence = any(
        ev in {"text:tutorial_terms", "shape:docs_only"}
        for ev in (repo_type_result.evidence or [])
    )
    if (
        repo_type_result.repo_type == "docs_tutorial"
        and target == "no_tools_writer"
        and bundle_id != "no_tools_writer"
        and repo_type_result.confidence >= 0.6
        and has_strong_tutorial_evidence
    ):
        bundle_id = "no_tools_writer"
        bundle_bias_applied = pre_bias_bundle_id != bundle_id
        bundle_bias_reason = (
            "forced docs_tutorial bundle preference to avoid API-keyword skew in tutorial paths"
        )

    # Ensure catalog-valid tool ids.
    additional_tools = [tid for tid in additional_tools if tid in allowed_tool_ids]

    rationale: List[str] = list(rec.get("rationale") or [])
    if bundle_bias_applied and bundle_bias_reason:
        rationale.append(f"Applied repo_type tie-break: {bundle_bias_reason}.")
    if pre_bias_bundle_id != bundle_id:
        rationale.append(
            f"Final recommended bundle changed from '{pre_bias_bundle_id}' to '{bundle_id}' after repo_type tie-break."
        )
    else:
        rationale.append(f"Final recommended bundle: '{bundle_id}'.")
    _log.info(
        "tool_discovery repo_type=%s confidence=%.2f bundle_id=%s",
        repo_type_result.repo_type,
        repo_type_result.confidence,
        bundle_id,
    )
    rationale.append(f"Repo type classified as {repo_type_result.repo_type}.")

    return {
        "bundle_id": bundle_id,
        "additional_tools": additional_tools,
        "rationale": rationale,
        "debug": {
            **(debug if isinstance(debug, dict) else {}),
            "extracted_tool_ids": extracted_tool_ids,
            "bundle_id_pre_repo_type_bias": pre_bias_bundle_id,
            "bundle_id_post_repo_type_bias": bundle_id,
            "bundle_repo_type_bias_applied": bundle_bias_applied,
            "bundle_repo_type_bias_reason": bundle_bias_reason,
            "repo_type": repo_type_result.repo_type,
            "repo_type_confidence": repo_type_result.confidence,
            "repo_type_evidence": repo_type_result.evidence,
            "repo_type_scores": repo_type_result.scores,
        },
    }
