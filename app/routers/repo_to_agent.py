"""
Repo-to-agent async job API.

POST /repo-to-agent creates a run and executes the repo-to-agent workflow in a
background thread. Clients poll GET /runs/{run_id} and GET /runs/{run_id}/result.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.dependencies import AuthError, enforce_auth, require_clerk_user_id
from app.engine import new_request_id
from app.repo_to_agent.app_flow import run_repo_to_agent
from app.routers.github import _fetch_clerk_github_access_token
from app.storage import run_store

logger = logging.getLogger("agent-gateway")

router = APIRouter(prefix="/repo-to-agent", tags=["repo-to-agent"])

def _agents_error(status_code: int, code: str, message: str, details: list | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {"code": code, "message": message, **({"details": details} if details is not None else {})},
            "meta": {"request_id": new_request_id()},
        },
    )


@router.post("/")
async def create_repo_to_agent_run(request: Request) -> JSONResponse:
    """
    Start a repo-to-agent run asynchronously. Body: owner, repo, ref?, url?, execution_backend?.

    When Clerk is configured, requires a valid session token so the gateway can use the user's
    GitHub OAuth token (higher API limits). Otherwise falls back to GITHUB_TOKEN or anonymous.

    Returns run_id and status "queued". Poll GET /runs/{run_id} and GET /runs/{run_id}/result.
    """
    settings = get_settings()
    github_token_for_run: Optional[str] = None
    if settings.auth_token:
        try:
            enforce_auth(request)
        except AuthError as exc:
            return _agents_error(401, "UNAUTHORIZED", str(exc))
    elif settings.clerk_jwks_url or settings.clerk_jwt_key:
        try:
            user_id = require_clerk_user_id(request)
        except AuthError as exc:
            return _agents_error(401, "UNAUTHORIZED", str(exc))
        try:
            tok, _ = await _fetch_clerk_github_access_token(user_id=user_id)
            github_token_for_run = tok
            if not tok:
                logger.info(
                    "repo-to-agent: no Clerk GitHub OAuth token for user (connect GitHub in Clerk); "
                    "using GITHUB_TOKEN or anonymous GitHub API"
                )
        except Exception as exc:
            logger.warning("repo-to-agent: Clerk GitHub token lookup failed: %s", exc)
    try:
        body = await request.json()
    except Exception:
        return _agents_error(400, "MALFORMED_REQUEST", "Request body must be valid JSON")
    if not isinstance(body, dict):
        return _agents_error(400, "MALFORMED_REQUEST", "Request body must be a JSON object")

    owner = body.get("owner")
    repo = body.get("repo")
    url = body.get("url")
    if not owner and not repo and not url:
        return _agents_error(
            422,
            "INPUT_VALIDATION_ERROR",
            "At least one of owner+repo or url is required",
            details=[{"path": [], "message": "Missing 'owner' and 'repo' (or 'url')"}],
        )

    execution_backend = body.get("execution_backend")
    if execution_backend is None or (isinstance(execution_backend, str) and not execution_backend.strip()):
        execution_backend = "openai"
    if execution_backend not in ("openai", "internal"):
        return _agents_error(
            422,
            "INPUT_VALIDATION_ERROR",
            f"execution_backend must be 'openai' or 'internal', got {execution_backend!r}",
        )

    run_store.init_run_db()
    run = run_store.create_run(
        agent_id="repo_to_agent",
        agent_version="1.0",
        session_id=None,
        input_json=body,
    )
    run_id = run["id"]

    def run_in_background() -> None:
        try:
            repo_input: Dict[str, Any] = {
                k: v for k, v in body.items() if k in ("owner", "repo", "ref", "url") and v is not None
            }
            result = run_repo_to_agent(
                repo_input,
                execution_backend=execution_backend,
                github_token=github_token_for_run,
            )
            run_store.set_run_status(run_id, "succeeded", output_json=result.model_dump())
        except Exception as e:
            logger.exception("repo-to-agent run %s failed", run_id)
            run_store.set_run_status(run_id, "failed", error=str(e))

    thread = threading.Thread(target=run_in_background)
    thread.start()
    return JSONResponse(status_code=200, content={"run_id": run_id, "status": "queued"})
