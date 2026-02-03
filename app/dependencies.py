from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Request
import jwt
from jwt import PyJWKClient

from .config import get_settings
from .providers import BaseProvider, build_provider


def get_provider() -> BaseProvider:
    """
    Dependency returning the active provider.

    Tests rely on this function name to override the provider with a
    RecordingProvider/RaisingProvider via FastAPI's dependency_overrides.
    """

    return build_provider()


def _get_bearer_token(request: Request) -> Optional[str]:
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        return token or None
    return None


def _get_session_cookie(request: Request) -> Optional[str]:
    cookie_token = request.cookies.get("__session")
    return cookie_token or None


def _get_jwks_client(jwks_url: str) -> PyJWKClient:
    # PyJWKClient internally caches keys by kid; keep instance-level cache by URL.
    if not jwks_url:
        raise AuthError("Clerk JWKS URL is not configured")
    return PyJWKClient(jwks_url)


_jwks_clients: Dict[str, PyJWKClient] = {}


def _get_cached_jwks_client(jwks_url: str) -> PyJWKClient:
    client = _jwks_clients.get(jwks_url)
    if client is None:
        client = _get_jwks_client(jwks_url)
        _jwks_clients[jwks_url] = client
    return client


def _verify_clerk_token(token: str) -> Dict[str, Any]:
    settings = get_settings()
    clerk_jwt_key = settings.clerk_jwt_key
    clerk_jwks_url = settings.clerk_jwks_url
    clerk_issuer = settings.clerk_issuer
    clerk_audience = settings.clerk_audience
    authorized_parties = settings.clerk_authorized_parties

    if not clerk_jwt_key and not clerk_jwks_url:
        raise AuthError("Clerk auth is not configured")

    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise AuthError("Invalid session token") from exc

    if unverified_header.get("alg") != "RS256":
        raise AuthError("Unsupported token algorithm")

    options = {"verify_aud": bool(clerk_audience)}
    decode_kwargs: Dict[str, Any] = {
        "algorithms": ["RS256"],
        "options": options,
    }
    if clerk_issuer:
        decode_kwargs["issuer"] = clerk_issuer
    if clerk_audience:
        decode_kwargs["audience"] = clerk_audience

    try:
        if clerk_jwt_key:
            claims = jwt.decode(token, clerk_jwt_key, **decode_kwargs)
        else:
            jwks_client = _get_cached_jwks_client(clerk_jwks_url or "")
            signing_key = jwks_client.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, signing_key, **decode_kwargs)
    except jwt.PyJWTError as exc:
        raise AuthError("Invalid or expired session token") from exc

    if authorized_parties:
        azp = claims.get("azp")
        if not azp or azp not in authorized_parties:
            raise AuthError("Unauthorized token issuer")

    return claims


def require_clerk_user_id(request: Request) -> str:
    """
    Require Clerk authentication and return the Clerk user id (sub).
    """
    token = _get_bearer_token(request) or _get_session_cookie(request)
    if not token:
        raise AuthError("Missing session token")

    claims = _verify_clerk_token(token)
    user_id = claims.get("sub")
    if not user_id:
        raise AuthError("Missing user id in token")
    return str(user_id)


def enforce_auth(request: Request) -> None:
    """
    Auth guard used by mutating endpoints.

    Priority:
    - If AUTH_TOKEN is set, accept only that bearer token (legacy tests/dev).
    - Otherwise, require a valid Clerk session token.
    - If neither is configured, authentication is effectively disabled.
    """
    settings = get_settings()
    if settings.auth_token:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise AuthError("Missing or invalid Authorization header")
        supplied = auth_header.split(" ", 1)[1].strip()
        if supplied != settings.auth_token:
            raise AuthError("Invalid bearer token")
        return

    if settings.clerk_jwt_key or settings.clerk_jwks_url:
        require_clerk_user_id(request)
        return

    # No auth configured: allow through for dev/tests.
    return


class AuthError(RuntimeError):
    """Raised when authentication fails."""
