"""
Catalog API (Part 5): tools by category, bundles, recommend bundle, resolve spec draft.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.catalog.loader import load_bundles_catalog, load_tools_catalog, validate_catalogs
from app.catalog.recommendation import recommend_bundle
from app.catalog.resolution import ResolutionError, resolve_spec_tools
from app.engine import build_error_envelope, new_request_id
from app.preset_loader import PresetLoadError, get_active_preset
from app.recommendations.tool_recommender import (
    CatalogBundle,
    CatalogTool,
    RecommendationInput,
    recommend_tools_for_agent,
)

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
async def get_catalog_tools(
    category: Optional[str] = None,
    execution_kind: Optional[str] = None,
    q: Optional[str] = None,
    limit: Optional[int] = None,
    flat: bool = False,
) -> JSONResponse:
    """
    Return tools from the catalog.

    - Legacy behavior (default): grouped by category under {"categories": [...]}
    - Flat mode (flat=true or when any filter is provided): {"tools": [...]}
    """
    try:
        tools_catalog = load_tools_catalog()
    except Exception as e:
        return _catalog_error(500, "CATALOG_ERROR", str(e))

    tools_list = tools_catalog.get("tools") or []

    # If any filter is provided or flat=true, return a flat list with frontend-friendly metadata.
    if flat or any([category, execution_kind, q, limit is not None]):
        # Basic validation for limit
        if limit is not None and limit <= 0:
            return _catalog_error(400, "MALFORMED_REQUEST", "limit must be positive when provided")

        q_norm = (q or "").strip().lower()
        category_norm = (category or "").strip().lower() or None
        execution_kind_norm = (execution_kind or "").strip().lower() or None

        filtered: List[Dict[str, Any]] = []
        for t in tools_list:
            if not isinstance(t, dict):
                continue
            tool_id = t.get("tool_id")
            if not isinstance(tool_id, str):
                continue

            cat = t.get("category")
            ek = t.get("execution_kind")

            if category_norm is not None:
                cat_norm = (cat or "").strip().lower()
                if cat_norm != category_norm:
                    continue

            if execution_kind_norm is not None:
                ek_norm = (ek or "").strip().lower()
                if ek_norm != execution_kind_norm:
                    continue

            if q_norm:
                haystack = " ".join(
                    [
                        str(tool_id),
                        str(t.get("name") or ""),
                        str(t.get("description") or ""),
                        str(t.get("source_repo") or ""),
                        str(t.get("source_path") or ""),
                    ]
                ).lower()
                if q_norm not in haystack:
                    continue

            filtered.append(
                {
                    "id": tool_id,
                    "name": t.get("name") or tool_id,
                    "description": t.get("description"),
                    "category": cat,
                    "execution_kind": ek,
                    "confidence": t.get("confidence"),
                    "source_repo": t.get("source_repo"),
                    "source_path": t.get("source_path"),
                    "promotion_reason": t.get("promotion_reason"),
                }
            )

        # Stable ordering: sort by id for determinism, then apply limit.
        filtered_sorted = sorted(filtered, key=lambda x: x.get("id") or "")
        if limit is not None:
            filtered_sorted = filtered_sorted[:limit]

        return JSONResponse(status_code=200, content={"tools": filtered_sorted})

    # Legacy response: tools grouped by category (used by existing tests and docs).
    by_category: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for t in tools_list:
        if not isinstance(t, dict):
            continue
        cat = t.get("category") or "Other"
        if not isinstance(cat, str):
            cat = "Other"
        by_category[cat].append(
            {
                "tool_id": t.get("tool_id"),
                "category": cat,
                "description": t.get("description"),
                "safety_level": t.get("safety_level"),
                "input_schema_ref": t.get("input_schema_ref"),
                "default_policy": t.get("default_policy") or {},
            }
        )
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


@router.post("/recommend-tools")
async def post_catalog_recommend_tools(request: Request) -> JSONResponse:
    """Recommend tools (bundle + additional tools) for an agent design."""
    try:
        body = await request.json()
    except Exception:
        return _catalog_error(400, "MALFORMED_REQUEST", "Request body must be valid JSON")
    if not isinstance(body, dict):
        return _catalog_error(400, "MALFORMED_REQUEST", "Request body must be an object")

    def _as_str(value: Optional[Any]) -> str:
        if value is None:
            return ""
        return str(value)

    name = _as_str(body.get("name"))
    description = _as_str(body.get("description"))
    primitive = _as_str(body.get("primitive"))
    prompt = _as_str(body.get("prompt"))
    repo_url_val = body.get("repo_url")
    repo_url = str(repo_url_val) if isinstance(repo_url_val, str) else None
    extracted_tool_ids_val = body.get("extracted_tool_ids") or []
    extracted_tool_ids: List[str] = []
    if isinstance(extracted_tool_ids_val, list):
        for item in extracted_tool_ids_val:
            if isinstance(item, str):
                extracted_tool_ids.append(item)

    try:
        tools_catalog = load_tools_catalog()
        bundles_catalog = load_bundles_catalog()
    except Exception as e:
        return _catalog_error(500, "CATALOG_ERROR", str(e))

    tools_list = tools_catalog.get("tools") or []
    bundles_list = bundles_catalog.get("bundles") or []

    available_tools: List[CatalogTool] = []
    for t in tools_list:
        if not isinstance(t, dict):
            continue
        tool_id = t.get("tool_id")
        if not isinstance(tool_id, str):
            continue
        available_tools.append(
            CatalogTool(
                tool_id=tool_id,
                name=t.get("name"),
                description=t.get("description"),
                category=t.get("category"),
                execution_kind=t.get("execution_kind"),
                confidence=t.get("confidence"),
                source_repo=t.get("source_repo"),
                source_path=t.get("source_path"),
                promotion_reason=t.get("promotion_reason"),
            )
        )

    available_bundles: List[CatalogBundle] = []
    for b in bundles_list:
        if not isinstance(b, dict):
            continue
        bundle_id = b.get("bundle_id")
        if not isinstance(bundle_id, str):
            continue
        tools = b.get("tools") or []
        tools_clean: List[str] = [tid for tid in tools if isinstance(tid, str)]
        available_bundles.append(
            CatalogBundle(
                bundle_id=bundle_id,
                title=b.get("title"),
                description=b.get("description"),
                category=b.get("category"),
                tools=tools_clean,
            )
        )

    rec_input = RecommendationInput(
        name=name,
        description=description,
        primitive=primitive,
        prompt=prompt,
        repo_url=repo_url,
        repo_context={},
        extracted_tool_ids=extracted_tool_ids,
    )

    result = recommend_tools_for_agent(
        agent_input=rec_input,
        available_tools=available_tools,
        available_bundles=available_bundles,
    )
    return JSONResponse(
        status_code=200,
        content=result.model_dump(),
    )

