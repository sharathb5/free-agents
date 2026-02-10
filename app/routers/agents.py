"""
Agent Registry API.

Registry-backed discovery and invocation of agents.
Uses build_error_envelope and request_id pattern as sessions.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import json
import yaml
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import get_settings
from app.dependencies import AuthError, get_provider, require_clerk_user_id
from app.examples import get_example
from app.engine import build_error_envelope, new_request_id, process_invoke_for_preset
from app.preset_loader import PresetLoadError, get_active_preset
from app.registry_adapter import spec_to_preset
from app.storage import registry_store

logger = logging.getLogger("agent-gateway")

router = APIRouter(prefix="/agents", tags=["agents"])


def _agents_error(status_code: int, code: str, message: str, details: Any = None) -> JSONResponse:
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


def _parse_bool(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    return None


@router.post("/register")
async def register_agent(request: Request) -> JSONResponse:
    """
    Register an agent spec (YAML string or JSON object).
    """
    try:
        from app.dependencies import enforce_auth

        enforce_auth(request)
    except AuthError as exc:
        return _agents_error(401, "UNAUTHORIZED", str(exc))

    try:
        payload = await request.json()
    except Exception:
        return _agents_error(400, "MALFORMED_REQUEST", "Request body must be valid JSON")

    if not isinstance(payload, dict) or "spec" not in payload:
        return _agents_error(400, "AGENT_SPEC_INVALID", "Missing 'spec' field")

    raw_spec = payload.get("spec")
    if isinstance(raw_spec, str):
        try:
            spec_obj = yaml.safe_load(raw_spec)
        except Exception as exc:
            return _agents_error(400, "AGENT_SPEC_INVALID", "Spec must be valid YAML", details={"message": str(exc)})
    elif isinstance(raw_spec, dict):
        spec_obj = raw_spec
    else:
        return _agents_error(400, "AGENT_SPEC_INVALID", "Spec must be a YAML string or JSON object")

    try:
        settings = get_settings()
        owner_user_id: Optional[str] = None
        if settings.clerk_jwt_key or settings.clerk_jwks_url:
            owner_user_id = require_clerk_user_id(request)
        agent_id, version = registry_store.register_agent(spec_obj, owner_user_id=owner_user_id)
    except registry_store.AgentNotOwner as exc:
        return _agents_error(403, "FORBIDDEN", str(exc))
    except registry_store.AgentSpecInvalid as exc:
        return _agents_error(400, "AGENT_SPEC_INVALID", str(exc), details=getattr(exc, "details", None))
    except registry_store.AgentVersionExists as exc:
        return _agents_error(409, "AGENT_VERSION_EXISTS", str(exc))
    except Exception as exc:
        logger.exception("register_agent failed")
        return _agents_error(500, "REGISTRY_ERROR", "Failed to register agent", details={"message": str(exc)})

    return JSONResponse(
        status_code=200,
        content={"ok": True, "agent_id": agent_id, "version": version, "status": "registered"},
    )


@router.get("/mine")
async def get_my_agents(request: Request, include_archived: Optional[str] = None) -> JSONResponse:
    """
    List agents owned by the current authenticated user.
    """
    try:
        owner_user_id = require_clerk_user_id(request)
    except AuthError as exc:
        return _agents_error(401, "UNAUTHORIZED", str(exc))

    include_archived_bool = _parse_bool(include_archived)
    if include_archived_bool is None:
        include_archived_bool = False
    agents = registry_store.list_agents_by_owner(
        owner_user_id,
        include_archived=include_archived_bool,
    )
    return JSONResponse(status_code=200, content={"agents": agents})


@router.get("")
async def get_agents(
    q: Optional[str] = None,
    primitive: Optional[str] = None,
    supports_memory: Optional[str] = None,
    latest_only: Optional[str] = None,
    include_archived: Optional[str] = None,
) -> JSONResponse:
    """
    List agents from the registry with optional filters.
    Returns 200 with { "agents": [ ... ] }.
    """
    supports_memory_bool = _parse_bool(supports_memory)
    latest_only_bool = _parse_bool(latest_only)
    include_archived_bool = _parse_bool(include_archived)
    if latest_only_bool is None:
        latest_only_bool = True
    if include_archived_bool is None:
        include_archived_bool = False

    agents = registry_store.list_agents(
        q=q,
        primitive=primitive,
        supports_memory=supports_memory_bool,
        latest_only=latest_only_bool,
        include_archived=include_archived_bool,
    )
    return JSONResponse(status_code=200, content={"agents": agents})


@router.post("/{agent_id}/archive")
async def archive_agent(request: Request, agent_id: str, version: Optional[str] = None) -> JSONResponse:
    """
    Archive an agent (soft delete). Requires auth and ownership.
    """
    owner_user_id: Optional[str] = None
    settings = get_settings()
    if settings.clerk_jwt_key or settings.clerk_jwks_url:
        try:
            owner_user_id = require_clerk_user_id(request)
        except AuthError as exc:
            return _agents_error(401, "UNAUTHORIZED", str(exc))

    try:
        agent_id_out, version_out = registry_store.archive_agent(
            agent_id,
            version=version,
            owner_user_id=owner_user_id,
        )
    except registry_store.AgentNotOwner as exc:
        return _agents_error(403, "FORBIDDEN", str(exc))
    except registry_store.AgentNotFound as exc:
        return _agents_error(404, "AGENT_NOT_FOUND", str(exc))
    except Exception as exc:
        logger.exception("archive_agent failed")
        return _agents_error(500, "REGISTRY_ERROR", "Failed to archive agent", details={"message": str(exc)})

    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "agent_id": agent_id_out,
            "version": version_out,
            "status": "archived",
        },
    )


@router.post("/{agent_id}/unarchive")
async def unarchive_agent(request: Request, agent_id: str, version: Optional[str] = None) -> JSONResponse:
    """
    Unarchive an agent. Requires auth and ownership.
    """
    owner_user_id: Optional[str] = None
    settings = get_settings()
    if settings.clerk_jwt_key or settings.clerk_jwks_url:
        try:
            owner_user_id = require_clerk_user_id(request)
        except AuthError as exc:
            return _agents_error(401, "UNAUTHORIZED", str(exc))

    try:
        agent_id_out, version_out = registry_store.unarchive_agent(
            agent_id,
            version=version,
            owner_user_id=owner_user_id,
        )
    except registry_store.AgentNotOwner as exc:
        return _agents_error(403, "FORBIDDEN", str(exc))
    except registry_store.AgentNotFound as exc:
        return _agents_error(404, "AGENT_NOT_FOUND", str(exc))
    except Exception as exc:
        logger.exception("unarchive_agent failed")
        return _agents_error(500, "REGISTRY_ERROR", "Failed to unarchive agent", details={"message": str(exc)})

    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "agent_id": agent_id_out,
            "version": version_out,
            "status": "active",
        },
    )


@router.get("/updates/stream")
async def stream_agent_updates() -> StreamingResponse:
    """
    Server-sent events stream for agent registry updates.
    Emits `agent_created` events when a new agent is registered.
    """

    async def event_stream():
        last_seen = registry_store.get_registry_version()
        # Initial keepalive so the client knows the stream is connected.
        yield ": connected\n\n"
        while True:
            version = await registry_store.wait_for_registry_change(last_seen)
            if version != last_seen:
                last_seen = version
                payload = json.dumps({"version": version})
                yield f"event: agent_created\ndata: {payload}\n\n"
            else:
                # Periodic keepalive to avoid idle timeouts.
                yield ": keepalive\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/{agent_id}")
async def get_agents_id(agent_id: str, version: Optional[str] = None) -> JSONResponse:
    """
    Get one agent by id. Returns 200 with full details or 404 with AGENT_NOT_FOUND envelope.
    """
    spec = registry_store.get_agent(agent_id, version=version)
    if spec is None:
        return _agents_error(404, "AGENT_NOT_FOUND", f"Agent not found: {agent_id}")

    body: Dict[str, Any] = {
        "id": spec.get("id"),
        "version": spec.get("version"),
        "name": spec.get("name"),
        "description": spec.get("description"),
        "primitive": spec.get("primitive"),
        "prompt": spec.get("prompt"),
        "input_schema": spec.get("input_schema"),
        "output_schema": spec.get("output_schema"),
        "supports_memory": bool(spec.get("supports_memory", False)),
        "memory_policy": spec.get("memory_policy"),
        "tags": spec.get("tags"),
        "credits": spec.get("credits"),
        "created_at": spec.get("created_at"),
    }
    return JSONResponse(status_code=200, content=body)


@router.get("/{agent_id}/schema")
async def get_agents_schema(agent_id: str, version: Optional[str] = None) -> JSONResponse:
    """
    Return schema for agent id + optional version.
    """
    schema = registry_store.get_agent_schema(agent_id, version=version)
    if schema is None:
        return _agents_error(404, "AGENT_NOT_FOUND", f"Agent not found: {agent_id}")
    return JSONResponse(status_code=200, content=schema)


@router.get("/{agent_id}/examples")
async def get_agents_examples(agent_id: str) -> JSONResponse:
    """
    Return plug-and-play input/output examples for a preset-backed agent id.
    """
    example = get_example(agent_id)
    if example is None:
        return _agents_error(404, "EXAMPLE_NOT_FOUND", f"No example found for agent: {agent_id}")
    return JSONResponse(status_code=200, content={"agent": agent_id, "example": example})


@router.post("/{agent_id}/invoke")
async def invoke_agent(
    agent_id: str,
    request: Request,
    version: Optional[str] = None,
    provider=Depends(get_provider),
) -> JSONResponse:
    """
    Invoke a registry agent by id (and optional version).
    """
    spec = registry_store.get_agent(agent_id, version=version)
    if spec is None:
        return _agents_error(404, "AGENT_NOT_FOUND", f"Agent not found: {agent_id}")

    preset = spec_to_preset(spec)
    result = await process_invoke_for_preset(request=request, provider=provider, preset=preset)
    return JSONResponse(status_code=result["status_code"], content=result["body"])


@router.post("/{agent_id}/stream")
async def stream_agent(agent_id: str, request: Request) -> JSONResponse:
    """
    Streaming interface (not implemented yet).
    """
    try:
        from app.dependencies import enforce_auth

        enforce_auth(request)
    except AuthError as exc:
        return _agents_error(401, "UNAUTHORIZED", str(exc))

    return _agents_error(501, "NOT_IMPLEMENTED", "Streaming endpoint is not implemented")
