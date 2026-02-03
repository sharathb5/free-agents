from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .dependencies import AuthError, get_provider
from .engine import (
    build_error_envelope,
    new_request_id,
    process_invoke_request,
)
from .preset_loader import PRESETS_DIR, PresetLoadError, get_active_preset
from .routers import agents as agents_router
from .routers import sessions as sessions_router
from .storage import registry_store
from .storage import session_store


logger = logging.getLogger("agent-gateway")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB and teardown on shutdown."""
    session_store.init_db()
    registry_store.init_registry_db()
    registry_store.seed_from_presets(PRESETS_DIR)
    yield


app = FastAPI(title="Standardized Agent Runtime", version="0.1.0", lifespan=lifespan)


# CORS: controlled by env CORS_ORIGINS (e.g. * or http://localhost:3000)
_cors_origins_list = [o.strip() for o in get_settings().cors_origins.strip().split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(agents_router.router)
app.include_router(sessions_router.router)


@app.get("/")
async def root() -> Dict[str, Any]:
    """
    Service metadata endpoint.
    """
    request_id = new_request_id()
    try:
        preset = get_active_preset()
    except PresetLoadError as exc:
        status_code, body = build_error_envelope(
            request_id=request_id,
            preset=None,
            status_code=500,
            code="INTERNAL_ERROR",
            message=str(exc),
            details=None,
        )
        return JSONResponse(status_code=status_code, content=body)

    return {
        "service": "agent-gateway",
        "agent": preset.id,
        "version": preset.version,
        "docs": "/docs",
        "schema": "/schema",
        "health": "/health",
    }


@app.get("/health")
async def health() -> JSONResponse:
    """
    Simple health check. Returns 200 when preset loads successfully.
    """
    request_id = new_request_id()
    try:
        preset = get_active_preset()
    except PresetLoadError as exc:
        status_code, body = build_error_envelope(
            request_id=request_id,
            preset=None,
            status_code=500,
            code="INTERNAL_ERROR",
            message=str(exc),
            details=None,
        )
        return JSONResponse(status_code=status_code, content=body)

    payload = {
        "status": "ok",
        "agent": preset.id,
        "version": preset.version,
    }
    return JSONResponse(status_code=200, content=payload)


@app.get("/schema")
async def schema() -> JSONResponse:
    """
    Return the active preset's schema information.
    """
    request_id = new_request_id()
    try:
        preset = get_active_preset()
    except PresetLoadError as exc:
        status_code, body = build_error_envelope(
            request_id=request_id,
            preset=None,
            status_code=500,
            code="INTERNAL_ERROR",
            message=str(exc),
            details=None,
        )
        return JSONResponse(status_code=status_code, content=body)

    payload = {
        "agent": preset.id,
        "version": preset.version,
        "primitive": preset.primitive,
        "input_schema": preset.input_schema,
        "output_schema": preset.output_schema,
    }
    return JSONResponse(status_code=200, content=payload)


@app.post("/invoke")
async def invoke(
    request: Request,
    provider=Depends(get_provider),
) -> JSONResponse:
    """
    Core agent invocation entrypoint.
    """
    result = await process_invoke_request(request=request, provider=provider)
    return JSONResponse(status_code=result["status_code"], content=result["body"])


@app.post("/stream")
async def stream(request: Request) -> JSONResponse:
    """
    Streaming interface (not implemented yet).
    """
    request_id = new_request_id()
    try:
        preset = get_active_preset()
    except PresetLoadError:
        preset = None

    # Enforce auth for mutating endpoints if configured. Catch only AuthError.
    try:
        from .dependencies import enforce_auth

        enforce_auth(request)
    except AuthError as exc:
        status_code, body = build_error_envelope(
            request_id=request_id,
            preset=preset,
            status_code=401,
            code="UNAUTHORIZED",
            message=str(exc),
            details=None,
        )
        return JSONResponse(status_code=status_code, content=body)

    status_code, body = build_error_envelope(
        request_id=request_id,
        preset=preset,
        status_code=501,
        code="NOT_IMPLEMENTED",
        message="Streaming endpoint is not implemented",
        details=None,
    )
    return JSONResponse(status_code=status_code, content=body)


def get_app() -> FastAPI:
    """Convenience accessor for external runners."""
    return app
