"""
Catalog API (Part 5): tools by category, bundles, recommend bundle, resolve spec draft.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.catalog.loader import load_bundles_catalog, load_tools_catalog, validate_catalogs
from app.catalog.recommendation import recommend_bundle
from app.catalog.resolution import ResolutionError, resolve_spec_tools
from app.engine import build_error_envelope, new_request_id
from app.preset_loader import PresetLoadError, get_active_preset

router = APIRouter(prefix="/catalog", tags=["catalog"])


def _catalog_error(status_code: int, code: str, message: str, details: Any = None) -> JSONResponse:
    request_id = new_request_id()
    try:
        preset = get_active_preset()
    except PresetLoadError:
        preset = None
    _, body = build_error_envelope(
        request_id=request_id,
        preset=preset,
        status_code=status_code,
        code=code,
        message=message,
        details=details,
    )
    return JSONResponse(status_code=status_code, content=body)


@router.get("/tools")
async def get_catalog_tools() -> JSONResponse:
    """Return tools grouped by category."""
    try:
        tools_catalog = load_tools_catalog()
    except Exception as e:
        return _catalog_error(500, "CATALOG_ERROR", str(e))
    tools_list = tools_catalog.get("tools") or []
    by_category: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for t in tools_list:
        if not isinstance(t, dict):
            continue
        cat = t.get("category") or "Other"
        if not isinstance(cat, str):
            cat = "Other"
        by_category[cat].append({
            "tool_id": t.get("tool_id"),
            "category": cat,
            "description": t.get("description"),
            "safety_level": t.get("safety_level"),
            "input_schema_ref": t.get("input_schema_ref"),
            "default_policy": t.get("default_policy") or {},
        })
    categories = [
        {"name": name, "tools": sorted(tools, key=lambda t: t.get("tool_id") or "")}
        for name, tools in sorted(by_category.items())
    ]
    return JSONResponse(status_code=200, content={"categories": categories})


@router.get("/bundles")
async def get_catalog_bundles() -> JSONResponse:
    """Return list of bundles with bundle_id, title, description, category, tools."""
    try:
        bundles_catalog = load_bundles_catalog()
    except Exception as e:
        return _catalog_error(500, "CATALOG_ERROR", str(e))
    bundles_list = bundles_catalog.get("bundles") or []
    out: List[Dict[str, Any]] = []
    for b in bundles_list:
        if not isinstance(b, dict):
            continue
        out.append({
            "bundle_id": b.get("bundle_id"),
            "title": b.get("title"),
            "description": b.get("description"),
            "category": b.get("category"),
            "tools": b.get("tools") or [],
        })
    return JSONResponse(status_code=200, content={"bundles": out})


@router.post("/recommend")
async def post_catalog_recommend(request: Request) -> JSONResponse:
    """Recommend a bundle from an agent idea. Body: { \"agent_idea\": \"...\" }."""
    try:
        body = await request.json()
    except Exception:
        return _catalog_error(400, "MALFORMED_REQUEST", "Request body must be valid JSON")
    if not isinstance(body, dict):
        return _catalog_error(400, "MALFORMED_REQUEST", "Request body must be an object")
    agent_idea = body.get("agent_idea")
    if agent_idea is not None and not isinstance(agent_idea, str):
        agent_idea = str(agent_idea)
    result = recommend_bundle(agent_idea or "")
    return JSONResponse(status_code=200, content=result)


@router.post("/tools/resolve")
async def post_catalog_tools_resolve(request: Request) -> JSONResponse:
    """Resolve a spec draft to allowed_tools and policies without persisting. Body: { \"spec\": { ... } }."""
    try:
        body = await request.json()
    except Exception:
        return _catalog_error(400, "MALFORMED_REQUEST", "Request body must be valid JSON")
    if not isinstance(body, dict) or "spec" not in body:
        return _catalog_error(400, "MALFORMED_REQUEST", "Request body must have 'spec'")
    spec = body["spec"]
    if not isinstance(spec, dict):
        return _catalog_error(400, "MALFORMED_REQUEST", "'spec' must be an object")
    try:
        resolved, _ = resolve_spec_tools(spec)
    except ResolutionError as e:
        return _catalog_error(400, "RESOLUTION_ERROR", str(e))
    except Exception as e:
        return _catalog_error(500, "CATALOG_ERROR", str(e))
    return JSONResponse(status_code=200, content={
        "resolved_allowed_tools": resolved["resolved_allowed_tools"],
        "resolved_tool_policies": resolved["resolved_tool_policies"],
        "resolved_execution_limits": resolved["resolved_execution_limits"],
        "resolved_bundle_id": resolved["resolved_bundle_id"],
        "warnings": resolved["warnings"],
    })

