"""
Centralized exception handling for repo-to-agent execution.

Use these helpers instead of checking exception class names by string,
so SDK or timeout semantics can change in one place.
"""

from __future__ import annotations


class StepTimeoutError(Exception):
    """Raised when a specialist step exceeds its wall-clock timeout."""

    pass


def is_should_fallback_to_internal(exc: BaseException) -> bool:
    """
    Return True if this exception should trigger fallback to the internal runner
    for scout/architect steps (e.g. max turns exceeded or step timeout).

    Prefer isinstance checks when the SDK is available; fall back to class name
    and module so we don't require the SDK at import time.
    """
    # Custom step timeout (we raise this when step-level timeout fires)
    if isinstance(exc, StepTimeoutError):
        return True

    # SDK MaxTurnsExceeded: try to resolve the real type first
    try:
        from agents.errors import MaxTurnsExceeded  # type: ignore[import-not-found]
        if isinstance(exc, MaxTurnsExceeded):
            return True
    except ImportError:
        pass
    try:
        from agents import MaxTurnsExceeded  # type: ignore[import-not-found]
        if isinstance(exc, MaxTurnsExceeded):
            return True
    except ImportError:
        pass

    # Fallback: same exception may be raised from SDK without importing it here
    cls = type(exc)
    if cls.__name__ == "MaxTurnsExceeded":
        mod = getattr(cls, "__module__", "") or ""
        if "agents" in mod:
            return True

    return False
