"""
GitHub repo listing endpoints for the upload flow.

Primary production path:
- authenticate the app user with Clerk
- fetch that user's GitHub OAuth access token from Clerk's backend API
- list repositories with that token

Legacy custom GitHub OAuth endpoints remain mounted for compatibility while the
frontend pivots to Clerk-backed account connections.
"""

from __future__ import annotations

import secrets
import time
import json
from dataclasses import dataclass
from html import escape
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlencode, urlparse

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from app.config import get_settings
from app.dependencies import AuthError, require_clerk_user_id
from app.engine import new_request_id

router = APIRouter(prefix="/github", tags=["github"])

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_BASE = "https://api.github.com"
GITHUB_API_ACCEPT = "application/vnd.github+json"
GITHUB_OAUTH_SCOPE = "read:user repo"
STATE_TTL_SECONDS = 600
SESSION_TTL_SECONDS = 60 * 60 * 8
MAX_REPO_PAGES = 5
REPOS_PER_PAGE = 100


class GitHubConnectionState(BaseModel):
    provider: str = "github"
    status: str = "disconnected"
    message: Optional[str] = None
    oauth_configured: bool = False
    connection_source: str = "clerk"


class GitHubOAuthStartResponse(BaseModel):
    provider: str = "github"
    status: str
    authorization_url: Optional[str] = None
    # Echo for GitHub UI: must match "Authorization callback URL" / user callback exactly.
    redirect_uri: Optional[str] = None
    message: Optional[str] = None


class GitHubRepoSummary(BaseModel):
    id: str
    name: str
    full_name: str
    owner_login: str
    html_url: str
    default_branch: Optional[str] = None
    private: bool = False
    installation_type: str = "oauth"


class GitHubRepoListResponse(BaseModel):
    repos: List[GitHubRepoSummary]
    connection: GitHubConnectionState


@dataclass
class _PendingOAuthState:
    state_token: str
    return_to: str
    created_at: float


@dataclass
class _GitHubSession:
    session_id: str
    access_token: str
    created_at: float
    github_login: Optional[str] = None


_pending_states: Dict[str, _PendingOAuthState] = {}
_github_sessions: Dict[str, _GitHubSession] = {}


def _oauth_configured() -> bool:
    settings = get_settings()
    return bool(
        settings.github_client_id
        and settings.github_client_secret
        and settings.github_oauth_redirect_uri
    )


def _redirect_uri_breakdown(redirect_uri: Optional[str]) -> Optional[Dict[str, Any]]:
    if not redirect_uri or not redirect_uri.strip():
        return None
    parsed = urlparse(redirect_uri.strip())
    return {
        "scheme": parsed.scheme or "",
        "hostname": parsed.hostname or "",
        "port": parsed.port,
        "path": parsed.path or "",
    }


def _clerk_github_configured() -> bool:
    settings = get_settings()
    return bool(settings.clerk_secret_key and (settings.clerk_jwt_key or settings.clerk_jwks_url))


def _cleanup_expired() -> None:
    now = time.time()
    expired_states = [
        token for token, state in _pending_states.items()
        if now - state.created_at > STATE_TTL_SECONDS
    ]
    for token in expired_states:
        _pending_states.pop(token, None)

    expired_sessions = [
        session_id for session_id, session in _github_sessions.items()
        if now - session.created_at > SESSION_TTL_SECONDS
    ]
    for session_id in expired_sessions:
        _github_sessions.pop(session_id, None)


def _json_error(status_code: int, code: str, message: str, *, details: Dict[str, Any] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                **({"details": details} if details is not None else {}),
            },
            "meta": {"request_id": new_request_id()},
        },
    )


def _disconnected_response(message: str, *, oauth_configured: bool, status: str = "disconnected") -> JSONResponse:
    body = GitHubRepoListResponse(
        repos=[],
        connection=GitHubConnectionState(
            status=status,
            message=message,
            oauth_configured=oauth_configured,
        ),
    )
    return JSONResponse(status_code=200, content=body.model_dump())


async def _fetch_clerk_github_access_token(*, user_id: str) -> tuple[Optional[str], List[str]]:
    settings = get_settings()
    if not settings.clerk_secret_key:
        raise RuntimeError("Clerk backend access is not configured.")

    api_base = (settings.clerk_api_url or "https://api.clerk.com").rstrip("/")
    url = f"{api_base}/v1/users/{quote(user_id, safe='')}/oauth_access_tokens/oauth_github"
    headers = {
        "Authorization": f"Bearer {settings.clerk_secret_key}",
        "Accept": "application/json",
        "User-Agent": "agent-toolbox/1.0",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url, headers=headers, params={"paginated": "true"})

    if response.status_code == 404:
        return None, []
    if response.status_code >= 400:
        raise RuntimeError(f"Clerk GitHub token lookup failed (HTTP {response.status_code})")

    payload = response.json()
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        items = payload["data"]
    elif isinstance(payload, list):
        items = payload
    else:
        items = []

    for item in items:
        if not isinstance(item, dict):
            continue
        token = item.get("token")
        scopes = item.get("scopes")
        if isinstance(token, str) and token.strip():
            return token.strip(), [str(scope) for scope in scopes] if isinstance(scopes, list) else []
    return None, []


def _github_headers(*, access_token: str) -> Dict[str, str]:
    return {
        "Accept": GITHUB_API_ACCEPT,
        "User-Agent": "agent-toolbox/1.0",
        "Authorization": f"Bearer {access_token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _canonical_origin(origin_or_url: str) -> Optional[str]:
    """Normalize scheme://host[:port] for comparisons."""
    s = origin_or_url.strip().rstrip("/")
    if not s or "://" not in s:
        return None
    p = urlparse(s)
    if p.scheme not in ("http", "https") or not p.hostname:
        return None
    scheme = p.scheme.lower()
    host = p.hostname.lower()
    if p.port:
        return f"{scheme}://{host}:{p.port}"
    return f"{scheme}://{host}"


def _safe_origin(return_to: str) -> str:
    """
    Validate `return_to` (frontend origin from oauth/start) for postMessage targetOrigin.
    Always allows http://localhost:* and http://127.0.0.1:*.
    Allows https (or http) origins listed in GITHUB_OAUTH_ALLOWED_RETURN_ORIGINS.
    If CORS_ORIGINS is not *, each comma-separated origin there is also allowed.
    """
    raw = return_to.strip()
    if not raw or "://" not in raw:
        return ""
    p = urlparse(raw)
    if p.scheme not in ("http", "https") or not p.hostname:
        return ""
    origin = f"{p.scheme}://{p.netloc}"
    key = _canonical_origin(origin)
    if not key:
        return ""

    host_l = p.hostname.lower()
    if p.scheme == "http" and (host_l == "localhost" or host_l == "127.0.0.1"):
        return origin

    settings = get_settings()
    for entry in settings.github_oauth_allowed_return_origins or []:
        if _canonical_origin(entry) == key:
            return origin

    cors = (settings.cors_origins or "").strip()
    if cors != "*":
        for part in cors.split(","):
            part = part.strip()
            if not part or part == "*":
                continue
            if _canonical_origin(part) == key:
                return origin

    return ""


def _popup_html(*, return_to: str, payload: Dict[str, Any]) -> HTMLResponse:
    target_origin = _safe_origin(return_to) or "*"
    payload_json = (
        json.dumps(payload)
        .replace("\\", "\\\\")
        .replace("</", "<\\/")
        .replace("'", "\\'")
    )
    html = f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>GitHub Connection</title>
  </head>
  <body style="font-family: sans-serif; background: #271203; color: #f0ede8; padding: 24px;">
    <p>Finishing GitHub connection...</p>
    <script>
      (function() {{
        var payload = JSON.parse('{payload_json}');
        if (window.opener && !window.opener.closed) {{
          window.opener.postMessage(payload, '{escape(target_origin)}');
        }}
        window.close();
      }})();
    </script>
  </body>
</html>"""
    return HTMLResponse(content=html)


async def _exchange_code_for_token(*, code: str) -> str:
    settings = get_settings()
    payload = {
        "client_id": settings.github_client_id,
        "client_secret": settings.github_client_secret,
        "code": code,
        "redirect_uri": settings.github_oauth_redirect_uri,
    }
    headers = {"Accept": "application/json", "User-Agent": "agent-toolbox/1.0"}
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(GITHUB_ACCESS_TOKEN_URL, data=payload, headers=headers)
    if response.status_code >= 400:
        raise RuntimeError(f"GitHub token exchange failed (HTTP {response.status_code})")
    data = response.json()
    token = data.get("access_token") if isinstance(data, dict) else None
    if not isinstance(token, str) or not token.strip():
        error = data.get("error_description") if isinstance(data, dict) else None
        raise RuntimeError(error or "GitHub token exchange did not return an access token")
    return token.strip()


async def _fetch_authenticated_user_login(*, access_token: str) -> Optional[str]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(f"{GITHUB_API_BASE}/user", headers=_github_headers(access_token=access_token))
    if response.status_code >= 400:
        return None
    data = response.json()
    login = data.get("login") if isinstance(data, dict) else None
    return login if isinstance(login, str) and login.strip() else None


async def _list_user_repos(*, access_token: str) -> List[GitHubRepoSummary]:
    repos: List[GitHubRepoSummary] = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        for page in range(1, MAX_REPO_PAGES + 1):
            response = await client.get(
                f"{GITHUB_API_BASE}/user/repos",
                headers=_github_headers(access_token=access_token),
                params={
                    "sort": "updated",
                    "per_page": REPOS_PER_PAGE,
                    "page": page,
                    "affiliation": "owner,collaborator,organization_member",
                },
            )
            if response.status_code >= 400:
                raise RuntimeError(f"GitHub repo listing failed (HTTP {response.status_code})")
            data = response.json()
            if not isinstance(data, list):
                break
            for item in data:
                if not isinstance(item, dict):
                    continue
                owner = item.get("owner") or {}
                owner_login = owner.get("login") if isinstance(owner, dict) else ""
                repo_id = item.get("id")
                name = item.get("name")
                full_name = item.get("full_name")
                html_url = item.get("html_url")
                if not all(isinstance(value, str) and value.strip() for value in (name, full_name, html_url, owner_login)):
                    continue
                repos.append(
                    GitHubRepoSummary(
                        id=str(repo_id),
                        name=name.strip(),
                        full_name=full_name.strip(),
                        owner_login=owner_login.strip(),
                        html_url=html_url.strip(),
                        default_branch=item.get("default_branch") if isinstance(item.get("default_branch"), str) else None,
                        private=bool(item.get("private", False)),
                    )
                )
            if len(data) < REPOS_PER_PAGE:
                break
    return repos


@router.get("/clerk-status")
async def github_clerk_status() -> JSONResponse:
    """
    Read-only wiring check for Clerk-backed GitHub listing (no secrets returned).
    If clerk_github_ready is false, /github/repos cannot use a Clerk-linked GitHub account.
    """
    settings = get_settings()
    has_secret = bool(settings.clerk_secret_key)
    has_jwt_verify = bool(settings.clerk_jwt_key or settings.clerk_jwks_url)
    if has_secret and has_jwt_verify:
        hint = "Clerk-backed GitHub listing should work for signed-in users who linked GitHub in Clerk."
    elif not has_jwt_verify:
        hint = "Set CLERK_JWKS_URL (or CLERK_JWT_KEY) and CLERK_SECRET_KEY on the gateway—the same Clerk instance as the frontend—then restart the API."
    else:
        hint = (
            "JWT verification is configured, but CLERK_SECRET_KEY is missing on the gateway. "
            "Add it (Clerk Dashboard → API Keys) so the API can fetch GitHub OAuth tokens for signed-in users, then restart."
        )

    return JSONResponse(
        {
            "clerk_secret_key_set": has_secret,
            "clerk_jwt_verification_configured": has_jwt_verify,
            "clerk_github_listing_ready": bool(has_secret and has_jwt_verify),
            "legacy_oauth_configured": _oauth_configured(),
            "hint": hint,
        }
    )


@router.get("/oauth/debug")
async def github_oauth_debug() -> JSONResponse:
    """
    Read-only OAuth wiring for the running process. Use when GitHub says
    redirect_uri is not associated: compare github_client_id and
    github_oauth_redirect_uri to the GitHub developer settings page for that
    same application (OAuth App callback vs GitHub App user callback).
    """
    settings = get_settings()
    rid = settings.github_oauth_redirect_uri
    return JSONResponse(
        {
            "oauth_configured": _oauth_configured(),
            "github_client_id": settings.github_client_id,
            "github_oauth_redirect_uri": rid,
            "redirect_uri_breakdown": _redirect_uri_breakdown(rid),
            "authorize_endpoint": GITHUB_AUTHORIZE_URL,
            "checklist": [
                "Open GitHub → Settings → Developer settings and find the app whose Client ID equals github_client_id above (not a different app).",
                "OAuth App: add github_oauth_redirect_uri under Authorization callback URL (one URL per line).",
                "GitHub App: add the same URL under User authorization callback URL (this flow uses github.com/login/oauth/authorize).",
                "Do not put multiple URLs on one line separated by commas; use a newline for each callback.",
                "This host's GITHUB_OAUTH_REDIRECT_URI must match where the browser is sent after authorize (local vs Render each need the matching URL registered).",
            ],
        }
    )


@router.get("/oauth/start")
async def github_oauth_start(
    return_to: str = Query(..., description="Frontend origin that opened the GitHub popup"),
) -> JSONResponse:
    _cleanup_expired()
    if not _oauth_configured():
        body = GitHubOAuthStartResponse(
            status="not_configured",
            message="GitHub OAuth is not configured on the backend.",
        )
        return JSONResponse(status_code=200, content=body.model_dump())

    target = _safe_origin(return_to)
    if not target:
        return _json_error(
            400,
            "INVALID_RETURN_TO",
            "return_to must be your frontend origin: localhost/127.0.0.1 (any port), "
            "or listed in GITHUB_OAUTH_ALLOWED_RETURN_ORIGINS, or match CORS_ORIGINS when not '*'.",
        )

    state_token = secrets.token_urlsafe(24)
    _pending_states[state_token] = _PendingOAuthState(
        state_token=state_token,
        return_to=target,
        created_at=time.time(),
    )

    settings = get_settings()
    authorization_url = (
        f"{GITHUB_AUTHORIZE_URL}?"
        + urlencode(
            {
                "client_id": settings.github_client_id or "",
                "redirect_uri": settings.github_oauth_redirect_uri or "",
                "scope": GITHUB_OAUTH_SCOPE,
                "state": state_token,
            }
        )
    )
    body = GitHubOAuthStartResponse(
        status="ready",
        authorization_url=authorization_url,
        redirect_uri=settings.github_oauth_redirect_uri,
        message="Open the GitHub authorization URL in a popup to continue.",
    )
    return JSONResponse(status_code=200, content=body.model_dump())


@router.get("/oauth/callback")
async def github_oauth_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
) -> HTMLResponse:
    _cleanup_expired()

    pending = _pending_states.pop(state or "", None)
    return_to = pending.return_to if pending else ""

    if error:
        return _popup_html(
            return_to=return_to,
            payload={
                "source": "github-oauth",
                "status": "error",
                "message": error_description or error,
            },
        )

    if not pending:
        return _popup_html(
            return_to=return_to,
            payload={
                "source": "github-oauth",
                "status": "error",
                "message": "GitHub OAuth state expired or was invalid.",
            },
        )

    if not code:
        return _popup_html(
            return_to=return_to,
            payload={
                "source": "github-oauth",
                "status": "error",
                "message": "Missing GitHub OAuth code.",
            },
        )

    try:
        access_token = await _exchange_code_for_token(code=code)
        github_login = await _fetch_authenticated_user_login(access_token=access_token)
        session_id = secrets.token_urlsafe(24)
        _github_sessions[session_id] = _GitHubSession(
            session_id=session_id,
            access_token=access_token,
            created_at=time.time(),
            github_login=github_login,
        )
        return _popup_html(
            return_to=return_to,
            payload={
                "source": "github-oauth",
                "status": "connected",
                "session_id": session_id,
                "github_login": github_login,
            },
        )
    except Exception as exc:
        return _popup_html(
            return_to=return_to,
            payload={
                "source": "github-oauth",
                "status": "error",
                "message": str(exc),
            },
        )


@router.get("/repos")
async def github_repos(request: Request, session_id: Optional[str] = Query(None)) -> JSONResponse:
    _cleanup_expired()
    settings = get_settings()

    # Primary path: derive GitHub access from the signed-in Clerk user.
    if _clerk_github_configured():
        try:
            user_id = require_clerk_user_id(request)
        except AuthError as exc:
            if session_id:
                # Allow temporary fallback for legacy popup sessions while the
                # frontend migrates fully to Clerk.
                pass
            else:
                detail = str(exc).strip() or "Authentication failed"
                hint = (
                    " The browser request must include Authorization: Bearer <JWT> from Clerk getToken(); "
                    "wait until Clerk has finished loading before calling the API."
                    if "Missing session token" in detail
                    else ""
                )
                if "Unauthorized token issuer" in detail:
                    hint = (
                        " Check CLERK_AUTHORIZED_PARTIES in the gateway .env: it must include this app’s "
                        "frontend origin (the JWT azp claim), or remove CLERK_AUTHORIZED_PARTIES to disable the check."
                    )
                elif "Invalid or expired" in detail or "Invalid session token" in detail:
                    hint = (
                        " Check CLERK_JWKS_URL and CLERK_ISSUER match the same Clerk instance as NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY."
                        " If the frontend uses NEXT_PUBLIC_CLERK_JWT_TEMPLATE, ensure it does not send that template JWT to this gateway"
                        " (use the default session token unless NEXT_PUBLIC_GATEWAY_USE_CLERK_JWT_TEMPLATE=1)."
                    )
                return _disconnected_response(
                    detail + hint,
                    oauth_configured=True,
                )
        else:
            try:
                access_token, scopes = await _fetch_clerk_github_access_token(user_id=user_id)
                if not access_token:
                    scope_note = (
                        " GitHub sign-in is enabled, but a reusable GitHub access token is not available for this user yet."
                    )
                    return _disconnected_response(
                        "Connect GitHub from your Clerk account settings, then refresh this list." + scope_note,
                        oauth_configured=True,
                    )

                repos = await _list_user_repos(access_token=access_token)
                has_repo_scope = any(scope == "repo" or scope.startswith("repo:") for scope in scopes)
                body = GitHubRepoListResponse(
                    repos=repos,
                    connection=GitHubConnectionState(
                        status="connected",
                        message=(
                            "Connected through Clerk. Private repos may still be limited unless the GitHub connection includes repo scopes; "
                            "the current parser still only imports public repos."
                            if not has_repo_scope
                            else "Connected through Clerk. Private repos can be listed, but the current parser still only imports public repos."
                        ),
                        oauth_configured=True,
                    ),
                )
                return JSONResponse(status_code=200, content=body.model_dump())
            except Exception as exc:
                body = GitHubRepoListResponse(
                    repos=[],
                    connection=GitHubConnectionState(
                        status="error",
                        message=str(exc),
                        oauth_configured=True,
                    ),
                )
                return JSONResponse(status_code=200, content=body.model_dump())

    # Legacy fallback: custom GitHub popup session.
    if not _oauth_configured():
        return _disconnected_response(
            "GitHub repository listing is not configured on this API. "
            "Set CLERK_SECRET_KEY and CLERK_JWKS_URL (Clerk-linked GitHub), "
            "or GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET / GITHUB_OAUTH_REDIRECT_URI (legacy popup). "
            "See GET /github/clerk-status.",
            oauth_configured=False,
            status="error",
        )

    if not session_id:
        # Reaching here means Clerk-backed listing is not active (_clerk_github_configured()
        # is false); otherwise /repos would have returned earlier. Users who linked GitHub
        # in Clerk still need server-side Clerk API + JWT settings.
        return _disconnected_response(
            "The gateway cannot read your Clerk-linked GitHub account yet. "
            "Add CLERK_SECRET_KEY and CLERK_JWKS_URL (or CLERK_JWT_KEY) to the API environment "
            "(Clerk Dashboard → API Keys / JWT verification; same instance as your frontend), restart uvicorn, then click Refresh. "
            "Open GET /github/clerk-status on this API to verify. "
            "Alternatively use legacy popup OAuth (GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, GITHUB_OAUTH_REDIRECT_URI) with that callback registered on GitHub.",
            oauth_configured=True,
        )

    session = _github_sessions.get(session_id)
    if session is None:
        return _disconnected_response(
            "GitHub session expired. Connect again to load repositories.",
            oauth_configured=True,
            status="error",
        )

    try:
        repos = await _list_user_repos(access_token=session.access_token)
    except Exception as exc:
        body = GitHubRepoListResponse(
            repos=[],
            connection=GitHubConnectionState(
                status="error",
                message=str(exc),
                oauth_configured=True,
                connection_source="legacy_oauth",
            ),
        )
        return JSONResponse(status_code=200, content=body.model_dump())

    body = GitHubRepoListResponse(
        repos=repos,
        connection=GitHubConnectionState(
            status="connected",
            message=(
                f"Connected as {session.github_login}. Private repos can be listed, "
                "but private-repo parsing is not enabled in the current import pipeline."
                if session.github_login
                else "Connected to GitHub."
            ),
            oauth_configured=True,
            connection_source="legacy_oauth",
        ),
    )
    return JSONResponse(status_code=200, content=body.model_dump())
