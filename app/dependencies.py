from __future__ import annotations

from typing import Any

from fastapi import Request

from .config import get_settings
from .providers import BaseProvider, build_provider


def get_provider() -> BaseProvider:
    """
    Dependency returning the active provider.

    Tests rely on this function name to override the provider with a
    RecordingProvider/RaisingProvider via FastAPI's dependency_overrides.
    """

    return build_provider()


def enforce_auth(request: Request) -> None:
    """
    Enforce optional bearer token authentication for mutating endpoints.

    If AUTH_TOKEN env var is unset or empty, authentication is disabled.
    When it is set, we require `Authorization: Bearer <token>`.

    This helper raises `AuthError` on failure; the global exception handler is
    responsible for emitting the standardized error envelope.
    """

    settings = get_settings()
    token = settings.auth_token
    if not token:
        return

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise AuthError("Missing or invalid Authorization header")

    supplied = auth_header.split(" ", 1)[1]
    if supplied != token:
        raise AuthError("Invalid bearer token")


class AuthError(RuntimeError):
    """Raised when authentication fails."""

