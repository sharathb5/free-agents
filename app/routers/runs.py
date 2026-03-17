"""
Runs API: get run status, result, steps, SSE events, and replay.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import get_settings
from app.dependencies import get_provider
from app.engine import new_request_id
from app.providers import BaseProvider
from app.registry_adapter import spec_to_preset
from app.runtime.runner import run_runner
from app.runtime.tools.registry import DefaultToolRegistry
from app.storage import registry_store
from app.storage import run_store
from app.utils.redaction import cap_text, redact_secrets

logger = logging.getLogger("agent-gateway")

router = APIRouter(prefix="/runs", tags=["runs"])

# Max chars for action_json / tool_result_json in verbose mode (capped for response size)
VERBOSE_JSON_MAX_CHARS = 10000
# SSE summary max length for step payload when verbose=false
SSE_SUMMARY_MAX_CHARS = 500
# Poll interval for SSE (seconds)
SSE_POLL_INTERVAL = 0.35


def _run_not_found() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "error": {"code": "RUN_NOT_FOUND", "message": "Run not found"},
            "meta": {"request_id": new_request_id()},
        },
    )


@router.get("/{run_id}")
async def get_run(run_id: str) -> JSONResponse:
    """Return run status, step_count, timestamps, and error if any."""
    run = run_store.get_run(run_id)
    if run is None:
        return _run_not_found()
    payload: Dict[str, Any] = {
        "run_id": run["id"],
        "agent_id": run["agent_id"],
        "agent_version": run["agent_version"],
        "status": run["status"],
        "step_count": run["step_count"],
        "created_at": run["created_at"],
        "updated_at": run["updated_at"],
    }
    if run.get("error"):
        payload["error"] = run["error"]
    if run.get("parent_run_id"):
        payload["parent_run_id"] = run["parent_run_id"]
    return JSONResponse(status_code=200, content=payload)


@router.get("/{run_id}/result")
async def get_run_result(run_id: str) -> JSONResponse:
    """If succeeded: 200 with output. If running/queued: 202 with status. If failed: 400 with error."""
    run = run_store.get_run(run_id)
    if run is None:
        return _run_not_found()
    status = run["status"]
    if status == "succeeded":
        return JSONResponse(
            status_code=200,
            content={"output": run.get("output_json")},
        )
    if status in ("running", "queued"):
        return JSONResponse(
            status_code=202,
            content={"status": status},
        )
    return JSONResponse(
        status_code=400,
        content={
            "error": {"code": "RUN_FAILED", "message": run.get("error") or "Run failed"},
            "status": status,
        },
    )


def _redact_and_cap_step(step: Dict[str, Any], verbose: bool) -> Dict[str, Any]:
    """Apply redaction and optional cap to step fields for API response."""
    out: Dict[str, Any] = {
        "id": step.get("id"),
        "run_id": step.get("run_id"),
        "step_index": step.get("step_index"),
        "step_type": step.get("step_type"),
        "created_at": step.get("created_at"),
        "event_time": step.get("event_time"),
        "tool_name": step.get("tool_name"),
        "error": step.get("error"),
        "tool_latency_ms": step.get("tool_latency_ms"),
        "latency_ms": step.get("latency_ms"),
        "tokens_prompt": step.get("tokens_prompt"),
        "tokens_completion": step.get("tokens_completion"),
        "cost_microusd": step.get("cost_microusd"),
        "error_code": step.get("error_code"),
    }
    if verbose:
        action = step.get("action_json")
        if action is not None:
            redacted = redact_secrets(action)
            s = str(redacted)
            out["action_json"] = cap_text(s, VERBOSE_JSON_MAX_CHARS) if len(s) > VERBOSE_JSON_MAX_CHARS else redacted
        tool_result = step.get("tool_result_json")
        if tool_result is not None:
            redacted = redact_secrets(tool_result)
            s = str(redacted)
            out["tool_result_json"] = cap_text(s, VERBOSE_JSON_MAX_CHARS) if len(s) > VERBOSE_JSON_MAX_CHARS else redacted
        tool_args = step.get("tool_args_json")
        if tool_args is not None:
            out["tool_args_json"] = redact_secrets(tool_args)
    return out


def _step_event_payload(step: Dict[str, Any], run_id: str, verbose: bool) -> Dict[str, Any]:
    """Build SSE step event payload: minimal (summary) when verbose=false, else redacted/capped full."""
    base: Dict[str, Any] = {
        "run_id": run_id,
        "step_index": step.get("step_index"),
        "step_type": step.get("step_type"),
        "latency_ms": step.get("latency_ms") or step.get("tool_latency_ms"),
        "error_code": step.get("error_code"),
    }
    if verbose:
        base["created_at"] = step.get("created_at")
        base["event_time"] = step.get("event_time")
        base["tool_name"] = step.get("tool_name")
        base["error"] = step.get("error")
        action = step.get("action_json")
        if action is not None:
            redacted = redact_secrets(action)
            s = str(redacted)
            base["action_json"] = cap_text(s, VERBOSE_JSON_MAX_CHARS) if len(s) > VERBOSE_JSON_MAX_CHARS else redacted
        tool_result = step.get("tool_result_json")
        if tool_result is not None:
            redacted = redact_secrets(tool_result)
            s = str(redacted)
            base["tool_result_json"] = cap_text(s, VERBOSE_JSON_MAX_CHARS) if len(s) > VERBOSE_JSON_MAX_CHARS else redacted
        return base
    # Minimal: summary for tool_result
    st = step.get("step_type")
    if st == "tool_result" and step.get("tool_result_json"):
        tr = step["tool_result_json"]
        if isinstance(tr, dict):
            sc = tr.get("status_code")
            body = tr.get("text", tr.get("body", ""))
            if isinstance(body, str) and len(body) > SSE_SUMMARY_MAX_CHARS:
                body = body[:SSE_SUMMARY_MAX_CHARS] + "...[truncated]"
            base["summary"] = f"{sc} OK (truncated)" if sc else str(tr)[:SSE_SUMMARY_MAX_CHARS]
        else:
            base["summary"] = str(tr)[:SSE_SUMMARY_MAX_CHARS]
    elif step.get("error"):
        base["summary"] = cap_text(step["error"], SSE_SUMMARY_MAX_CHARS)
    else:
        base["summary"] = st or ""
    return base


async def _sse_generator(
    run_id: str,
    verbose: bool,
    heartbeat_seconds: float,
) -> Any:
    """Async generator yielding SSE lines: run_started, step events, run_finished; heartbeat comments."""
    run = run_store.get_run(run_id)
    if run is None:
        yield f"event: error\ndata: {json.dumps({'error': 'RUN_NOT_FOUND', 'run_id': run_id})}\n\n"
        return
    yield f"event: run\ndata: {json.dumps({'event': 'run_started', 'run_id': run_id, 'status': run.get('status')})}\n\n"
    last_step_index: Optional[int] = None
    last_heartbeat = asyncio.get_event_loop().time()
    terminal = ("succeeded", "failed")
    while True:
        run = run_store.get_run(run_id)
        if run is None:
            break
        status = run.get("status")
        steps = run_store.list_run_steps(run_id, after_step_index=last_step_index)
        for step in steps:
            idx = step.get("step_index")
            if idx is not None:
                last_step_index = max(last_step_index or 0, idx)
            payload = _step_event_payload(step, run_id, verbose)
            yield f"event: step\ndata: {json.dumps(payload)}\n\n"
        if status in terminal:
            yield f"event: run\ndata: {json.dumps({'event': 'run_finished', 'run_id': run_id, 'status': status, 'error': run.get('error')})}\n\n"
            break
        # Heartbeat
        now = asyncio.get_event_loop().time()
        if heartbeat_seconds > 0 and (now - last_heartbeat) >= heartbeat_seconds:
            yield ": heartbeat\n\n"
            last_heartbeat = now
        await asyncio.sleep(SSE_POLL_INTERVAL)


@router.get("/{run_id}/events")
async def get_run_events(
    run_id: str,
    verbose: Optional[bool] = Query(False, alias="verbose"),
    heartbeat_seconds: Optional[float] = Query(10, alias="heartbeat_seconds"),
) -> StreamingResponse:
    """Server-Sent Events stream: run_started, step events, run_finished. Poll-based; use heartbeat_seconds to keep connection alive."""
    run = run_store.get_run(run_id)
    if run is None:
        return _run_not_found()
    return StreamingResponse(
        _sse_generator(run_id, verbose=bool(verbose), heartbeat_seconds=float(heartbeat_seconds or 10)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{run_id}/replay")
async def replay_run(
    run_id: str,
    request: Request,
    provider: BaseProvider = Depends(get_provider),
) -> JSONResponse:
    """
    Replay a run: create a new run with same agent_id, agent_version, input_json; optional session_id_override and write_back.
    Body: wait (default true), session_id_override?, write_back (default false).
    Returns new run_id, status, output/error.
    """
    original = run_store.get_run(run_id)
    if original is None:
        return _run_not_found()
    try:
        body = await request.json() if request.headers.get("content-length") else {}
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    wait = body.get("wait", True)
    if isinstance(wait, str):
        wait = wait.strip().lower() in ("true", "1", "yes")
    elif not isinstance(wait, bool):
        wait = True
    session_id_override = body.get("session_id_override") if isinstance(body.get("session_id_override"), str) else None
    write_back = body.get("write_back", False)
    if isinstance(write_back, str):
        write_back = write_back.strip().lower() in ("true", "1", "yes")
    elif not isinstance(write_back, bool):
        write_back = False

    agent_id = original.get("agent_id")
    agent_version = original.get("agent_version")
    input_json = original.get("input_json")
    if not agent_id or not isinstance(input_json, dict):
        return JSONResponse(
            status_code=400,
            content={
                "error": {"code": "REPLAY_INVALID", "message": "Original run missing agent_id or input_json"},
                "meta": {"request_id": new_request_id()},
            },
        )
    if agent_version is None:
        agent_version = "latest"
    session_id: Optional[str] = None
    if write_back:
        session_id = session_id_override if session_id_override is not None else original.get("session_id")

    spec = registry_store.get_agent(agent_id, version=agent_version)
    if spec is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {"code": "AGENT_NOT_FOUND", "message": f"Agent not found: {agent_id}"},
                "meta": {"request_id": new_request_id()},
            },
        )
    preset = spec_to_preset(spec)
    resolved_version = spec.get("version", "latest")
    run = run_store.create_run(
        agent_id,
        resolved_version,
        session_id,
        input_json,
        parent_run_id=run_id,
    )
    new_run_id = run["id"]
    request_id = new_request_id()
    tools_enabled = get_settings().tools_enabled
    tool_registry = DefaultToolRegistry() if tools_enabled else None
    limits = getattr(preset, "resolved_execution_limits", None) or {}

    if wait:
        run_runner(
            preset=preset,
            provider=provider,
            input_payload=input_json,
            run_id=new_run_id,
            session_id=session_id,
            request_id=request_id,
            tool_registry=tool_registry,
            max_steps=limits.get("max_steps"),
            max_wall_time_seconds=limits.get("max_wall_time_seconds"),
        )
        run = run_store.get_run(new_run_id)
        if run is None:
            return JSONResponse(
                status_code=500,
                content={
                    "error": {"code": "INTERNAL_ERROR", "message": "Run not found after execution"},
                    "meta": {"request_id": request_id},
                },
            )
        meta: Dict[str, Any] = {"step_count": run.get("step_count", 0), "parent_run_id": run_id}
        if session_id is not None:
            meta["session_id"] = session_id
        steps = run_store.list_run_steps(new_run_id)
        meta["tool_calls_used"] = sum(1 for s in steps if s.get("step_type") == "tool_call")
        meta["max_tool_calls"] = (
            limits.get("max_tool_calls") if limits.get("max_tool_calls") is not None else get_settings().max_tool_calls
        )
        return JSONResponse(
            status_code=200,
            content={
                "run_id": new_run_id,
                "status": run["status"],
                "output": run.get("output_json"),
                "error": run.get("error"),
                "meta": meta,
            },
        )

    def run_in_background() -> None:
        run_runner(
            preset=preset,
            provider=provider,
            input_payload=input_json,
            run_id=new_run_id,
            session_id=session_id,
            request_id=request_id,
            tool_registry=tool_registry,
            max_steps=limits.get("max_steps"),
            max_wall_time_seconds=limits.get("max_wall_time_seconds"),
        )

    threading.Thread(target=run_in_background).start()
    return JSONResponse(status_code=200, content={"run_id": new_run_id, "status": "queued", "parent_run_id": run_id})


@router.get("/{run_id}/steps")
async def get_run_steps(
    run_id: str,
    verbose: Optional[bool] = Query(False, alias="verbose"),
) -> JSONResponse:
    """Return list of steps; with verbose=true include full action_json/tool_result_json (redacted/capped)."""
    run = run_store.get_run(run_id)
    if run is None:
        return _run_not_found()
    steps = run_store.list_run_steps(run_id)
    payload = [_redact_and_cap_step(s, verbose=bool(verbose)) for s in steps]
    return JSONResponse(status_code=200, content={"steps": payload})
