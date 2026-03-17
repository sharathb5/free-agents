"""
Tool and bundle catalog loader (Part 5). Loads YAML source of truth and validates.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml

_CATALOG_DIR = Path(__file__).parent


class CatalogError(Exception):
    """Raised when catalog data is invalid."""


def load_tools_catalog() -> Dict[str, Any]:
    """Load and return parsed tools.yaml. Does not validate cross-references."""
    path = _CATALOG_DIR / "tools.yaml"
    if not path.exists():
        raise CatalogError(f"tools catalog not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or "tools" not in data:
        raise CatalogError("tools.yaml must have top-level key 'tools'")
    return data


def load_bundles_catalog() -> Dict[str, Any]:
    """Load and return parsed bundles.yaml. Does not validate cross-references."""
    path = _CATALOG_DIR / "bundles.yaml"
    if not path.exists():
        raise CatalogError(f"bundles catalog not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or "bundles" not in data:
        raise CatalogError("bundles.yaml must have top-level key 'bundles'")
    return data


def validate_catalogs(
    tools_catalog: Dict[str, Any],
    bundles_catalog: Dict[str, Any],
) -> None:
    """
    Validate tools and bundles catalogs. Raises CatalogError on failure.
    - Every bundle tool_id exists in tools catalog.
    - Categories are strings (in tools and bundles).
    - policy_overrides and default_policy are dicts.
    - Each bundle has a string category.
    """
    tools_list = tools_catalog.get("tools")
    if not isinstance(tools_list, list):
        raise CatalogError("tools catalog 'tools' must be a list")
    tool_ids = set()
    for i, t in enumerate(tools_list):
        if not isinstance(t, dict):
            raise CatalogError(f"tools[{i}] must be an object")
        tid = t.get("tool_id")
        if not isinstance(tid, str):
            raise CatalogError(f"tools[{i}].tool_id must be a string")
        tool_ids.add(tid)
        cat = t.get("category")
        if cat is not None and not isinstance(cat, str):
            raise CatalogError(f"tools[{i}].category must be a string")
        default_policy = t.get("default_policy")
        if default_policy is not None and not isinstance(default_policy, dict):
            raise CatalogError(f"tools[{i}].default_policy must be a dict")

    bundles_list = bundles_catalog.get("bundles")
    if not isinstance(bundles_list, list):
        raise CatalogError("bundles catalog 'bundles' must be a list")
    for i, b in enumerate(bundles_list):
        if not isinstance(b, dict):
            raise CatalogError(f"bundles[{i}] must be an object")
        cat = b.get("category")
        if not isinstance(cat, str):
            raise CatalogError(f"bundles[{i}].category must be a string")
        bundle_tools = b.get("tools")
        if not isinstance(bundle_tools, list):
            raise CatalogError(f"bundles[{i}].tools must be a list")
        for tid in bundle_tools:
            if tid not in tool_ids:
                raise CatalogError(
                    f"bundles[{i}] references tool_id '{tid}' which is not in tools catalog"
                )
        policy_overrides = b.get("policy_overrides")
        if policy_overrides is not None and not isinstance(policy_overrides, dict):
            raise CatalogError(f"bundles[{i}].policy_overrides must be a dict")
        if policy_overrides:
            for k, v in policy_overrides.items():
                if not isinstance(v, dict):
                    raise CatalogError(
                        f"bundles[{i}].policy_overrides.{k} must be a dict"
                    )
