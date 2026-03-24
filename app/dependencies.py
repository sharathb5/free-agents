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


def _unverified_claims(token: str) -> Dict[str, Any]:
    """Parse JWT payload without verification (for error messages only)."""
    try:
        hdr = jwt.get_unverified_header(token)
        alg = hdr.get("alg") or "RS256"
    except jwt.PyJWTError:
        alg = "RS256"
    return jwt.decode(
        token,
        algorithms=[alg],
        options={
            "verify_signature": False,
            "verify_aud": False,
            "verify_exp": False,
        },
    )


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

    alg = unverified_header.get("alg")
    if alg not in ("RS256", "ES256"):
        raise AuthError(f"Unsupported session token algorithm ({alg!r}); expected RS256 or ES256.")

    options: Dict[str, Any] = {"verify_aud": bool(clerk_audience)}
    decode_kwargs: Dict[str, Any] = {
        "algorithms": [alg],
        "options": options,
        "leeway": 60,
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
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Session token expired; sign out and sign in again, then retry.") from exc
    except jwt.InvalidAudienceError as exc:
        try:
            uc = _unverified_claims(token)
            tok_aud = uc.get("aud")
        except jwt.PyJWTError:
            tok_aud = None
        raise AuthError(
            "JWT audience does not match this API. Remove CLERK_AUDIENCE from the gateway .env "
            "(Clerk session tokens often omit aud or use a value you did not expect), "
            f"or set CLERK_AUDIENCE to match the token. Token aud={tok_aud!r}, gateway CLERK_AUDIENCE={clerk_audience!r}."
        ) from exc
    except jwt.InvalidIssuerError as exc:
        try:
            uc = _unverified_claims(token)
            tok_iss = uc.get("iss")
            # Normalize iss for copy-paste hint (trailing slash trips many setups).
            iss_hint = str(tok_iss).rstrip("/") if tok_iss else None
        except jwt.PyJWTError:
            iss_hint = None
        raise AuthError(
            "JWT issuer mismatch. Set CLERK_ISSUER in the gateway .env to exactly the session token iss claim "
            f"({iss_hint!r}), or remove CLERK_ISSUER to skip issuer checks. "
            f"Gateway currently has CLERK_ISSUER={clerk_issuer!r}."
        ) from exc
    except jwt.InvalidSignatureError as exc:
        raise AuthError(
            "JWT signature verification failed. Use CLERK_JWKS_URL from the same Clerk instance as "
            "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY (Clerk Dashboard → API Keys → show JWT verification URL)."
        ) from exc
    except jwt.PyJWTError as exc:
        msg_l = str(exc).lower()
        try:
            uc = _unverified_claims(token)
            iss_raw = uc.get("iss")
            iss_hint = str(iss_raw).rstrip("/") if iss_raw else None
            aud_disp = uc.get("aud")
            extra = f" Token iss={iss_raw!r}, aud={aud_disp!r}."
        except jwt.PyJWTError:
            iss_hint = None
            extra = ""
        # PyJWKClient: kid not present in JWKS — almost always wrong CLERK_JWKS_URL vs browser Clerk app.
        if "signing key" in msg_l or "could not find a key" in msg_l:
            jwks_fix = (
                f"Set gateway CLERK_JWKS_URL to {iss_hint}/.well-known/jwks.json (same Clerk app as the browser)."
                if iss_hint
                else "Set gateway CLERK_JWKS_URL to the JWT verification URL for the same Clerk app the frontend uses."
            )
            raise AuthError(
                "Clerk JWT signing key missing from gateway JWKS — the API and the browser are using different "
                f"Clerk instances (common when root .env is production but Next.js loads another publishable key). "
                f"{jwks_fix} {extra.strip()}"
            ) from exc
        raise AuthError(f"Invalid session token ({exc!s}).{extra}") from exc

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
