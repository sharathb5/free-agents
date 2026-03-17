"""
Tests for repo-to-agent exception helpers (centralized fallback detection).
"""

from __future__ import annotations

import pytest

from app.repo_to_agent.exceptions import (
    StepTimeoutError,
    is_should_fallback_to_internal,
)


def test_step_timeout_error_is_should_fallback() -> None:
    """StepTimeoutError is recognized as should-fallback."""
    assert is_should_fallback_to_internal(StepTimeoutError("timeout")) is True


def test_max_turns_exceeded_by_class_name_when_sdk_not_imported() -> None:
    """When SDK is not available, class name + module check is used."""
    class MaxTurnsExceeded(Exception):
        __module__ = "agents.runner"

    assert is_should_fallback_to_internal(MaxTurnsExceeded()) is True


def test_other_exception_not_fallback() -> None:
    """Generic exceptions are not treated as fallback."""
    assert is_should_fallback_to_internal(ValueError("other")) is False
    assert is_should_fallback_to_internal(RuntimeError("other")) is False


def test_same_name_different_module_not_fallback() -> None:
    """MaxTurnsExceeded from a non-agents module is not treated as fallback (safety)."""
    class MaxTurnsExceeded(Exception):
        __module__ = "other_package"

    assert is_should_fallback_to_internal(MaxTurnsExceeded()) is False
