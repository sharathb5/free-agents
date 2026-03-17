"""
Evals API (Part 6): create suites, run evals, get results.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.dependencies import get_provider
from app.engine import build_error_envelope, new_request_id
from app.evals.runner import EvalSuiteNotFound, run_eval_suite
from app.preset_loader import PresetLoadError, get_active_preset
from app.storage import eval_store
from app.storage import registry_store

logger = logging.getLogger("agent-gateway")

router = APIRouter(tags=["evals"])

ALLOWED_MATCHER_TYPES = frozenset({"exact_json", "subset_json", "string_contains", "schema_valid"})


def _evals_error(status_code: int, code: str, message: str, details: Any = None) -> JSONResponse:
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


def _validate_case(case: Any, index: int) -> str | None:
    """Validate a single case. Returns error message or None if valid."""
    if not isinstance(case, dict):
        return f"Case {index}: must be an object"
    if "input" not in case:
        return f"Case {index}: missing 'input'"
    if not isinstance(case.get("input"), dict):
        return f"Case {index}: 'input' must be an object"
    matcher = case.get("matcher")
    if not isinstance(matcher, dict):
        return f"Case {index}: 'matcher' must be an object"
    matcher_type = (matcher.get("type") or "").strip().lower()
    if not matcher_type:
        return f"Case {index}: 'matcher.type' is required"
    if matcher_type not in ALLOWED_MATCHER_TYPES:
        return f"Case {index}: matcher.type must be one of {sorted(ALLOWED_MATCHER_TYPES)}"
    if matcher_type == "schema_valid":
        options = matcher.get("options") or {}
        if not isinstance(options.get("schema"), dict):
            return f"Case {index}: schema_valid requires matcher.options.schema"
    return None


@router.post("/agents/{agent_id}/evals")
async def create_eval_suite(agent_id: str, request: Request) -> JSONResponse:
    """
    Create an eval suite for an agent.
    Body: name, description?, agent_version?, cases (list of {name, input, expected, matcher, ...}).
    """
    try:
        body = await request.json()
    except Exception:
        return _evals_error(400, "MALFORMED_REQUEST", "Request body must be valid JSON")
    if not isinstance(body, dict):
        return _evals_error(400, "MALFORMED_REQUEST", "Request body must be an object")
    name = body.get("name")
    if not name or not isinstance(name, str):
        return _evals_error(400, "VALIDATION_ERROR", "'name' is required and must be a string")
    cases = body.get("cases")
    if not isinstance(cases, list):
        return _evals_error(400, "VALIDATION_ERROR", "'cases' must be a list")

    for i, case in enumerate(cases):
        err = _validate_case(case, i)
        if err:
            return _evals_error(400, "VALIDATION_ERROR", err)

    if registry_store.get_agent(agent_id) is None:
        return _evals_error(404, "AGENT_NOT_FOUND", f"Agent not found: {agent_id}")

    description = body.get("description") if isinstance(body.get("description"), str) else None
    agent_version = body.get("agent_version") if isinstance(body.get("agent_version"), str) else None

    suite = eval_store.create_eval_suite(
        agent_id,
        name.strip(),
        cases,
        description=description,
        agent_version=agent_version,
    )
    return JSONResponse(
        status_code=201,
        content={
            "id": suite["id"],
            "agent_id": suite["agent_id"],
            "agent_version": suite.get("agent_version"),
            "name": suite["name"],
            "description": suite.get("description"),
            "created_at": suite["created_at"],
        },
    )


@router.get("/agents/{agent_id}/evals")
async def list_eval_suites(agent_id: str) -> JSONResponse:
    """List eval suites for an agent."""
    suites = eval_store.list_eval_suites(agent_id=agent_id)
    out: List[Dict[str, Any]] = []
    for s in suites:
        out.append({
            "id": s["id"],
            "agent_id": s["agent_id"],
            "agent_version": s.get("agent_version"),
            "name": s["name"],
            "description": s.get("description"),
            "created_at": s["created_at"],
        })
    return JSONResponse(status_code=200, content={"suites": out})


@router.get("/evals/{eval_suite_id}")
async def get_eval_suite(eval_suite_id: str) -> JSONResponse:
    """Return eval suite metadata and cases."""
    suite = eval_store.get_eval_suite(eval_suite_id)
    if suite is None:
        return _evals_error(404, "EVAL_SUITE_NOT_FOUND", f"Eval suite not found: {eval_suite_id}")
    return JSONResponse(status_code=200, content={
        "id": suite["id"],
        "agent_id": suite["agent_id"],
        "agent_version": suite.get("agent_version"),
        "name": suite["name"],
        "description": suite.get("description"),
        "created_at": suite["created_at"],
        "updated_at": suite["updated_at"],
        "cases": suite.get("cases_json", []),
    })


@router.post("/evals/{eval_suite_id}/run")
async def run_eval(
    eval_suite_id: str,
    request: Request,
    provider=Depends(get_provider),
) -> JSONResponse:
    """
    Run an eval suite.
    Body: wait (bool, default true), agent_version_override?.
    If wait=true: run synchronously, return eval_run_id and summary.
    If wait=false: start background thread, return eval_run_id and status.
    """
    suite = eval_store.get_eval_suite(eval_suite_id)
    if suite is None:
        return _evals_error(404, "EVAL_SUITE_NOT_FOUND", f"Eval suite not found: {eval_suite_id}")

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
    agent_version_override = body.get("agent_version_override") if isinstance(body.get("agent_version_override"), str) else None

    if wait:
        try:
            result = run_eval_suite(
                eval_suite_id,
                provider,
                agent_version_override=agent_version_override,
            )
        except EvalSuiteNotFound:
            return _evals_error(404, "EVAL_SUITE_NOT_FOUND", f"Eval suite not found: {eval_suite_id}")
        except registry_store.AgentNotFound as e:
            return _evals_error(404, "AGENT_NOT_FOUND", str(e))
        except Exception as e:
            logger.exception("run_eval_suite failed")
            return _evals_error(500, "EVAL_ERROR", str(e)[:500])

        return JSONResponse(status_code=200, content={
            "eval_run_id": result["id"],
            "status": result["status"],
            "summary": result.get("summary_json"),
        })

    agent_version = agent_version_override or suite.get("agent_version")
    eval_run = eval_store.create_eval_run(
        eval_suite_id,
        suite["agent_id"],
        agent_version=agent_version,
    )
    eval_run_id = eval_run["id"]
    eval_store.set_eval_run_status(eval_run_id, "running")

    def run_in_background() -> None:
        try:
            run_eval_suite(
                eval_suite_id,
                provider,
                agent_version_override=agent_version_override,
                eval_run_id=eval_run_id,
            )
        except Exception as e:
            logger.exception("eval run failed in background")
            eval_store.set_eval_run_status(
                eval_run_id,
                "failed",
                error=str(e)[:1000],
            )

    threading.Thread(target=run_in_background).start()
    return JSONResponse(status_code=200, content={
        "eval_run_id": eval_run_id,
        "status": "running",
    })


@router.get("/eval-runs/{eval_run_id}")
async def get_eval_run(eval_run_id: str) -> JSONResponse:
    """Return eval run summary and status."""
    run = eval_store.get_eval_run(eval_run_id)
    if run is None:
        return _evals_error(404, "EVAL_RUN_NOT_FOUND", f"Eval run not found: {eval_run_id}")
    return JSONResponse(status_code=200, content={
        "eval_run_id": run["id"],
        "eval_suite_id": run["eval_suite_id"],
        "agent_id": run["agent_id"],
        "agent_version": run.get("agent_version"),
        "status": run["status"],
        "created_at": run["created_at"],
        "updated_at": run["updated_at"],
        "summary": run.get("summary_json"),
        "error": run.get("error"),
    })


@router.get("/eval-runs/{eval_run_id}/results")
async def get_eval_run_results(eval_run_id: str) -> JSONResponse:
    """Return all case results for an eval run."""
    run = eval_store.get_eval_run(eval_run_id)
    if run is None:
        return _evals_error(404, "EVAL_RUN_NOT_FOUND", f"Eval run not found: {eval_run_id}")
    results = eval_store.list_eval_case_results(eval_run_id)
    return JSONResponse(status_code=200, content={"results": results})
