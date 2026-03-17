"""
Effective tool permissions resolution (Part 5).
Merges bundle + additional_tools + catalog defaults and execution limits.

Execution limits merge order (deterministic): A) settings defaults,
B) bundle.execution_limits, C) agent spec execution_limits.
Result stored as resolved_execution_limits; runtime uses it for
max_tool_calls, max_steps, max_wall_time_seconds.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.catalog.loader import CatalogError, load_bundles_catalog, load_tools_catalog, validate_catalogs

MAX_EXTRA_TOOLS = 3

# Execution limit keys (global, not per-tool)
EXECUTION_LIMIT_KEYS = ("max_tool_calls", "max_steps", "max_wall_time_seconds")


class ResolutionError(CatalogError):
    """Raised when resolution fails (unknown tool, too many additional_tools, etc.)."""


def _tools_by_id(tools_catalog: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Build tool_id -> tool entry from tools catalog."""
    out: Dict[str, Dict[str, Any]] = {}
    for t in tools_catalog.get("tools") or []:
        if isinstance(t, dict) and isinstance(t.get("tool_id"), str):
            out[t["tool_id"]] = t
    return out


def _bundles_by_id(bundles_catalog: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Build bundle_id -> bundle from bundles catalog."""
    out: Dict[str, Dict[str, Any]] = {}
    for b in bundles_catalog.get("bundles") or []:
        if isinstance(b, dict) and isinstance(b.get("bundle_id"), str):
            out[b["bundle_id"]] = b
    return out


def _merge_policy(base: Dict[str, Any], overlay: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Shallow merge overlay onto base (overlay wins). Exclude execution limit keys from tool policy."""
    result = dict(base)
    if overlay:
        for k, v in overlay.items():
            if k not in EXECUTION_LIMIT_KEYS:  # keep tool policies tool-specific
                result[k] = v
    return result


def resolve_effective_tools(
    agent_spec: Dict[str, Any],
    tools_catalog: Dict[str, Any],
    bundles_catalog: Dict[str, Any],
    *,
    default_execution_limits: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Resolve allowed tools, tool-specific policies, and global execution limits.

    Returns:
        resolved_allowed_tools: sorted list of tool_ids
        resolved_tool_policies: tool_id -> merged policy (tool-specific only)
        resolved_execution_limits: max_tool_calls, max_steps, max_wall_time_seconds
        resolved_bundle_id: str or None
        warnings: list of strings
    """
    tools_by_id = _tools_by_id(tools_catalog)
    bundles_by_id = _bundles_by_id(bundles_catalog)
    warnings: List[str] = []

    # Additional tools: prefer additional_tools, accept extra_tools as alias
    raw_additional = agent_spec.get("additional_tools")
    if raw_additional is None:
        raw_additional = agent_spec.get("extra_tools")
    additional_tools: List[str] = []
    if isinstance(raw_additional, list):
        additional_tools = [str(t).strip() for t in raw_additional if t]
    if len(additional_tools) > MAX_EXTRA_TOOLS:
        raise ResolutionError(
            f"additional_tools must not exceed {MAX_EXTRA_TOOLS} (got {len(additional_tools)})"
        )
    for tid in additional_tools:
        if tid not in tools_by_id:
            raise ResolutionError(f"additional_tools contains unknown tool_id: {tid}")

    bundle_id_raw = agent_spec.get("bundle_id")
    resolved_bundle_id: Optional[str] = (bundle_id_raw and str(bundle_id_raw).strip()) or None
    if resolved_bundle_id and resolved_bundle_id not in bundles_by_id:
        raise ResolutionError(f"bundle_id not found in catalog: {resolved_bundle_id}")

    # Base tools: from bundle or legacy allowed_tools
    base_tools: List[str] = []
    bundle_execution_limits: Dict[str, Any] = {}
    bundle_policy_overrides: Dict[str, Dict[str, Any]] = {}
    if resolved_bundle_id:
        bundle = bundles_by_id[resolved_bundle_id]
        base_tools = list(bundle.get("tools") or [])
        bundle_execution_limits = dict(bundle.get("execution_limits") or {})
        bundle_policy_overrides = {
            k: dict(v) for k, v in (bundle.get("policy_overrides") or {}).items()
        }
    else:
        legacy = agent_spec.get("allowed_tools")
        if isinstance(legacy, list):
            base_tools = [str(t).strip() for t in legacy if t]
        for tid in base_tools:
            if tid not in tools_by_id:
                raise ResolutionError(f"allowed_tools contains unknown tool_id: {tid}")

    # Combined allowed list: base + additional, dedupe, sort
    allowed_set: Dict[str, None] = {}
    for t in base_tools:
        allowed_set[t] = None
    for t in additional_tools:
        allowed_set[t] = None
    resolved_allowed_tools = sorted(allowed_set.keys())

    # Tool policies: catalog default -> bundle overrides -> agent tool_policies (tool-specific only)
    resolved_tool_policies: Dict[str, Dict[str, Any]] = {}
    agent_tool_policies = agent_spec.get("tool_policies")
    if not isinstance(agent_tool_policies, dict):
        agent_tool_policies = {}
    for tid in resolved_allowed_tools:
        tool_entry = tools_by_id.get(tid)
        base_policy = dict(tool_entry.get("default_policy") or {}) if tool_entry else {}
        base_policy = _merge_policy(base_policy, bundle_policy_overrides.get(tid))
        base_policy = _merge_policy(base_policy, agent_tool_policies.get(tid))
        resolved_tool_policies[tid] = base_policy

    # Execution limits: default -> bundle -> agent
    defaults = default_execution_limits or {}
    limits = {
        "max_tool_calls": defaults.get("max_tool_calls", 5),
        "max_steps": defaults.get("max_steps", 10),
        "max_wall_time_seconds": defaults.get("max_wall_time_seconds", 60),
    }
    for key in EXECUTION_LIMIT_KEYS:
        if key in bundle_execution_limits and bundle_execution_limits[key] is not None:
            limits[key] = int(bundle_execution_limits[key])
    agent_limits = agent_spec.get("execution_limits")
    if isinstance(agent_limits, dict):
        for key in EXECUTION_LIMIT_KEYS:
            if key in agent_limits and agent_limits[key] is not None:
                limits[key] = int(agent_limits[key])
    resolved_execution_limits = limits

    return {
        "resolved_allowed_tools": resolved_allowed_tools,
        "resolved_tool_policies": resolved_tool_policies,
        "resolved_execution_limits": resolved_execution_limits,
        "resolved_bundle_id": resolved_bundle_id,
        "warnings": warnings,
    }


def resolve_spec_tools(agent_spec: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Single entry point for tool resolution: catalog load, validation, and resolution.
    Used by both POST /catalog/tools/resolve (preview) and _normalize_spec (persistence).

    Returns:
        (resolved, tools_catalog) - resolved dict and tools_catalog for additional_tools normalization.
    """
    from app.config import get_settings

    tools_catalog = load_tools_catalog()
    bundles_catalog = load_bundles_catalog()
    validate_catalogs(tools_catalog, bundles_catalog)
    settings = get_settings()
    default_limits = {
        "max_tool_calls": settings.max_tool_calls,
        "max_steps": settings.max_steps,
        "max_wall_time_seconds": settings.max_wall_time_seconds,
    }
    resolved = resolve_effective_tools(
        agent_spec,
        tools_catalog,
        bundles_catalog,
        default_execution_limits=default_limits,
    )
    return resolved, tools_catalog
