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
    Append events to a session.
    Body: { "events": [ { "role", "content" }, ... ], "idempotency_key"?: "..." }.
    Returns 200 with { ok: true, session_id, appended: N, duplicated: bool }. 400 if body invalid; 404 if session not found.
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
    body_idempotency_key = body.get("idempotency_key")
    if body_idempotency_key is not None and not isinstance(body_idempotency_key, str):
        return _session_error(400, "MALFORMED_REQUEST", "'idempotency_key' must be a string")

    if isinstance(body_idempotency_key, str):
        enriched_events: List[Dict[str, Any]] = []
        for i, ev in enumerate(events):
            if not isinstance(ev, dict):
                enriched_events.append(ev)
                continue
            merged = dict(ev)
            if "idempotency_key" not in merged:
                merged["idempotency_key"] = (
                    body_idempotency_key if len(events) == 1 else f"{body_idempotency_key}:{i}"
                )
            enriched_events.append(merged)
        events = enriched_events
    session = session_store.get_session(session_id)
    if session is None:
        return _session_error(404, "NOT_FOUND", f"Session not found: {session_id}")
    result = session_store.append_events_detailed(session_id, events)
    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "session_id": session_id,
            "appended": int(result.get("appended", 0)),
            "duplicated": bool(result.get("duplicated", False)),
            "event_ids": result.get("event_ids", []),
        },
    )


@router.get("/{session_id}")
async def get_sessions_id(session_id: str) -> JSONResponse:
    """
    Get session by id. Returns 200 with
    { session_id, agent_id, created_at, events, running_summary, summary_updated_at, summary_message_count }
    or 404.
    """
    session = session_store.get_session(session_id)
    if session is None:
        return _session_error(404, "NOT_FOUND", f"Session not found: {session_id}")
    return JSONResponse(status_code=200, content=session)


@router.get("/{session_id}/summary")
async def get_sessions_summary(session_id: str) -> JSONResponse:
    """
    Get only the running_summary for a session.
    Returns 200 with { session_id, running_summary, summary_updated_at, summary_message_count } or 404.
    """
    session = session_store.get_session(session_id)
    if session is None:
        return _session_error(404, "NOT_FOUND", f"Session not found: {session_id}")
    return JSONResponse(
        status_code=200,
        content={
            "session_id": session["session_id"],
            "running_summary": session.get("running_summary") or "",
            "summary_updated_at": session.get("summary_updated_at"),
            "summary_message_count": session.get("summary_message_count", 0),
        },
    )
