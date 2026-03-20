"""
GitHub OAuth and repo listing scaffold.

This router intentionally exposes only placeholder responses for now so the
frontend can build against stable contracts without changing the current
paste-URL import path.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import get_settings
from app.engine import new_request_id

router = APIRouter(prefix="/github", tags=["github"])


class GitHubConnectionState(BaseModel):
    provider: str = "github"
    status: str = "disconnected"
    message: Optional[str] = None
    oauth_configured: bool = False


class GitHubOAuthStartResponse(BaseModel):
    provider: str = "github"
    status: str
    authorization_url: Optional[str] = None
    message: Optional[str] = None


class GitHubRepoSummary(BaseModel):
    id: str
    name: str
    full_name: str
    owner_login: str
    html_url: str
    default_branch: Optional[str] = None
    private: bool = False
    installation_type: str = "unknown"


class GitHubRepoListResponse(BaseModel):
    repos: List[GitHubRepoSummary]
    connection: GitHubConnectionState


def _not_implemented(message: str, *, details: Dict[str, Any] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={
            "error": {
                "code": "NOT_IMPLEMENTED",
                "message": message,
                **({"details": details} if details is not None else {}),
            },
            "meta": {"request_id": new_request_id()},
        },
    )


def _oauth_configured() -> bool:
    settings = get_settings()
    return bool(
        settings.github_client_id
        and settings.github_client_secret
        and settings.github_oauth_redirect_uri
    )


@router.get("/oauth/start")
async def github_oauth_start() -> JSONResponse:
    """
    Future OAuth start entry point.

    Later implementation should create the GitHub authorization URL and a
    state token, then redirect or return that URL to the client.
    """
    configured = _oauth_configured()
    if not configured:
        return _not_implemented(
            "GitHub OAuth is not configured",
            details={"provider": "github", "oauth_configured": False},
        )

    return _not_implemented(
        "GitHub OAuth start is scaffolded but not implemented",
        details={"provider": "github", "oauth_configured": True},
    )


@router.get("/oauth/callback")
async def github_oauth_callback() -> JSONResponse:
    """
    Future OAuth callback entry point.

    Later implementation should exchange the code for a server-side token and
    persist only the minimal session data needed to list repos/import.
    """
    return _not_implemented(
        "GitHub OAuth callback is scaffolded but not implemented",
        details={"provider": "github"},
    )


@router.get("/repos")
async def github_repos() -> JSONResponse:
    """
    Future repo picker data source.

    Later implementation should use the server-side GitHub token to list the
    accessible repositories and return only the minimal fields needed by the
    upload flow.
    """
    return _not_implemented(
        "GitHub repository listing is scaffolded but not implemented",
        details={
            "provider": "github",
            "oauth_configured": _oauth_configured(),
            "private_repo_support": False,
        },
    )
