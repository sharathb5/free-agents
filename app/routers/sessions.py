"""
Session Memory API: POST /sessions, POST /sessions/{id}/events, GET /sessions/{id}.

Contract: 201 + session_id; 200 + ok/session_id/appended; 200 + session dict or 404.
Error responses use build_error_envelope-style body (404/400/500).
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.engine import build_error_envelope, new_request_id
from app.preset_loader import PresetLoadError, get_active_preset
from app.storage import session_store

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _session_error(status_code: int, code: str, message: str, details: Any = None) -> JSONResponse:
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


@router.post("", status_code=201)
async def post_sessions(request: Request) -> JSONResponse:
    """
    Create a new session. Body optional. Uses active preset id as agent_id.
    Returns 201 with { session_id }.
    """
    try:
        preset = get_active_preset()
    except PresetLoadError as exc:
        return _session_error(500, "INTERNAL_ERROR", str(exc))
    session_id = session_store.create_session(preset.id)
    return JSONResponse(status_code=201, content={"session_id": session_id})


@router.post("/{session_id}/events")
async def post_sessions_events(session_id: str, request: Request) -> JSONResponse:
    """
    Append events to a session. Body: { "events": [ { "role", "content" }, ... ] }.
    Returns 200 with { ok: true, session_id, appended: N }. 400 if body invalid; 404 if session not found.
    """
    try:
        body = await request.json()
    except Exception:
        return _session_error(400, "MALFORMED_REQUEST", "Request body must be valid JSON")
    if not isinstance(body, dict) or "events" not in body:
        return _session_error(
            400,
            "MALFORMED_REQUEST",
            "Request body must include 'events' array",
            details=[{"message": "Missing 'events' field"}],
        )
    events = body["events"]
    if not isinstance(events, list):
        return _session_error(400, "MALFORMED_REQUEST", "'events' must be an array")
    session = session_store.get_session(session_id)
    if session is None:
        return _session_error(404, "NOT_FOUND", f"Session not found: {session_id}")
    appended = session_store.append_events(session_id, events)
    return JSONResponse(
        status_code=200,
        content={"ok": True, "session_id": session_id, "appended": appended},
    )


@router.get("/{session_id}")
async def get_sessions_id(session_id: str) -> JSONResponse:
    """
    Get session by id. Returns 200 with { session_id, agent_id, created_at, events, running_summary } or 404.
    """
    session = session_store.get_session(session_id)
    if session is None:
        return _session_error(404, "NOT_FOUND", f"Session not found: {session_id}")
    return JSONResponse(status_code=200, content=session)
