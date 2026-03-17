"""
Tests for Part 6 eval runner: synchronous execution, persist results, continue-on-error.
"""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict

import pytest

from app.evals.runner import EvalSuiteNotFound, run_eval_suite
from app.storage import eval_store


@pytest.fixture
def db_path():
    """Temporary DB path. Isolated per test."""
    with tempfile.TemporaryDirectory(prefix="agent_eval_runner_") as tmp:
        yield str(Path(tmp) / "gateway.db")


@contextmanager
def env_vars(env: Dict[str, str]):
    """Context manager to set env vars and restore after."""
    old = {}
    for k, v in env.items():
        old[k] = os.environ.get(k)
        os.environ[k] = v
    try:
        yield
    finally:
        for k, old_v in old.items():
            if old_v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old_v


def _init_and_seed_temp_db() -> None:
    """Initialize DBs and seed registry from presets."""
    from app.preset_loader import PRESETS_DIR
    from app.storage import registry_store
    from app.storage import run_store
    from app.storage import session_store

    session_store.init_db()
    registry_store.init_registry_db()
    run_store.init_run_db()
    eval_store.init_eval_db()
    registry_store.seed_from_presets(PRESETS_DIR)


class ActionContractProvider:
    """Provider that returns a fixed action (final or tool_call)."""

    def __init__(self, action: Dict[str, Any]):
        self.action = action

    def complete_json(self, prompt: str, *, schema: Any) -> Any:
        import json
        from app.providers import ProviderResult
        return ProviderResult(parsed_json=self.action, raw_text=json.dumps(self.action))


def test_run_eval_suite_returns_summary(db_path) -> None:
    """run_eval_suite executes cases, persists results, returns eval run with summary."""
    with env_vars({
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
    }):
        _init_and_seed_temp_db()

        cases = [
            {
                "name": "case1",
                "input": {"text": "hello"},
                "expected": {"summary": "ok", "bullets": ["a", "b"]},
                "matcher": {"type": "exact_json"},
            },
        ]
        suite = eval_store.create_eval_suite("summarizer", "Test Suite", cases)
        provider = ActionContractProvider({"type": "final", "output": {"summary": "ok", "bullets": ["a", "b"]}})

        result = run_eval_suite(suite["id"], provider)

        assert result["status"] == "succeeded"
        assert result["summary_json"] is not None
        summary = result["summary_json"]
        assert summary["total_cases"] == 1
        assert summary["passed"] == 1
        assert summary["failed"] == 0
        assert summary["errored"] == 0
        assert summary["completed_cases"] == 1
        assert summary["average_score"] == 1.0
        assert summary["pass_rate"] == 1.0

        results = eval_store.list_eval_case_results(result["id"])
        assert len(results) == 1
        assert results[0]["status"] == "passed"
        assert results[0]["score"] == 1.0
        assert results[0]["run_id"] is not None


def test_run_eval_suite_failed_case_persists(db_path) -> None:
    """When expected does not match actual, case is failed and result is persisted."""
    with env_vars({
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
    }):
        _init_and_seed_temp_db()

        cases = [
            {
                "name": "mismatch",
                "input": {"text": "x"},
                "expected": {"result": "expected"},
                "matcher": {"type": "exact_json"},
            },
        ]
        suite = eval_store.create_eval_suite("summarizer", "Suite", cases)
        provider = ActionContractProvider({"type": "final", "output": {"result": "actual"}})

        result = run_eval_suite(suite["id"], provider)

        assert result["status"] == "succeeded"
        assert result["summary_json"]["passed"] == 0
        assert result["summary_json"]["failed"] == 1

        results = eval_store.list_eval_case_results(result["id"])
        assert results[0]["status"] == "failed"
        assert results[0]["score"] == 0.0


def test_run_eval_suite_continue_on_error(db_path) -> None:
    """When one case fails (e.g. tool_call with tools disabled), mark error and continue."""
    with env_vars({
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
        "AGENT_TOOLS_ENABLED": "false",
    }):
        _init_and_seed_temp_db()

        cases = [
            {
                "name": "pass",
                "input": {"text": "a"},
                "expected": {"ok": True},
                "matcher": {"type": "exact_json"},
            },
            {
                "name": "tool_call_fails",
                "input": {"text": "b"},
                "expected": {},
                "matcher": {"type": "exact_json"},
            },
        ]
        suite = eval_store.create_eval_suite("summarizer", "Suite", cases)
        # First call returns final (pass), second returns tool_call (fails when tools disabled)
        call_count = [0]

        class TwoPhaseProvider:
            def complete_json(self, prompt: str, *, schema: Any) -> Any:
                import json
                from app.providers import ProviderResult
                call_count[0] += 1
                if call_count[0] == 1:
                    return ProviderResult(parsed_json={"type": "final", "output": {"ok": True}}, raw_text="{}")
                return ProviderResult(
                    parsed_json={"type": "tool_call", "tool_name": "http_request", "args": {"url": "x"}},
                    raw_text="{}",
                )

        result = run_eval_suite(suite["id"], TwoPhaseProvider())

        assert result["status"] == "succeeded"
        summary = result["summary_json"]
        assert summary["total_cases"] == 2
        assert summary["passed"] == 1
        assert summary["errored"] == 1

        results = eval_store.list_eval_case_results(result["id"])
        assert len(results) == 2
        assert results[0]["status"] == "passed"
        assert results[1]["status"] == "error"


def test_run_eval_suite_raises_when_suite_not_found(db_path) -> None:
    """run_eval_suite raises EvalSuiteNotFound when suite does not exist."""
    with env_vars({
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
    }):
        eval_store.init_eval_db()
        provider = ActionContractProvider({"type": "final", "output": {}})

        with pytest.raises(EvalSuiteNotFound, match="not found"):
            run_eval_suite("nonexistent-suite-id", provider)


def test_run_eval_suite_raises_when_agent_not_found(db_path) -> None:
    """run_eval_suite raises AgentNotFound when agent does not exist in registry."""
    with env_vars({
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
    }):
        from app.storage import registry_store

        eval_store.init_eval_db()
        registry_store.init_registry_db()
        suite = eval_store.create_eval_suite("nonexistent_agent", "Suite", [{"name": "c", "input": {}, "expected": {}, "matcher": {"type": "exact_json"}}])
        provider = ActionContractProvider({"type": "final", "output": {}})

        with pytest.raises(registry_store.AgentNotFound, match="Agent not found"):
            run_eval_suite(suite["id"], provider)


def test_run_eval_suite_multiple_cases_aggregates(db_path) -> None:
    """Multiple cases: summary aggregates passed/failed correctly."""
    with env_vars({
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
    }):
        _init_and_seed_temp_db()

        cases = [
            {"name": "c1", "input": {"text": "1"}, "expected": {"v": 1}, "matcher": {"type": "exact_json"}},
            {"name": "c2", "input": {"text": "2"}, "expected": {"v": 2}, "matcher": {"type": "exact_json"}},
            {"name": "c3", "input": {"text": "3"}, "expected": {"v": 99}, "matcher": {"type": "exact_json"}},
        ]
        suite = eval_store.create_eval_suite("summarizer", "Suite", cases)

        call_idx = [0]
        outputs = [{"v": 1}, {"v": 2}, {"v": 3}]

        class MultiOutputProvider:
            def complete_json(self, prompt: str, *, schema: Any) -> Any:
                import json
                from app.providers import ProviderResult
                idx = call_idx[0] % 3
                call_idx[0] += 1
                out = outputs[idx]
                return ProviderResult(parsed_json={"type": "final", "output": out}, raw_text=json.dumps(out))

        result = run_eval_suite(suite["id"], MultiOutputProvider())

        assert result["summary_json"]["passed"] == 2
        assert result["summary_json"]["failed"] == 1
        assert result["summary_json"]["average_score"] == pytest.approx(2 / 3)
