"""
Tests for Part 6 eval store: create/read/write of eval suites, runs, and case results.
"""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Dict

import pytest

# Import after pytest so env_vars can override .env before store operations
from app.storage import eval_store


@pytest.fixture
def db_path():
    """Temporary DB path for eval_store. Isolated per test."""
    with tempfile.TemporaryDirectory(prefix="agent_evals_") as tmp:
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


def test_create_eval_suite_and_get(db_path) -> None:
    """create_eval_suite returns dict; get_eval_suite returns same data."""
    with env_vars({"DB_PATH": db_path, "DATABASE_URL": "", "SUPABASE_DATABASE_URL": ""}):
        eval_store.init_eval_db()
        cases = [
            {"name": "case1", "input": {"x": 1}, "expected": {"y": 2}, "matcher": {"type": "exact_json"}},
        ]
        suite = eval_store.create_eval_suite(
            agent_id="test_agent",
            name="My Suite",
            cases=cases,
            agent_version="1",
            description="Test suite",
        )
        assert suite["id"]
        assert suite["agent_id"] == "test_agent"
        assert suite["agent_version"] == "1"
        assert suite["name"] == "My Suite"
        assert suite["description"] == "Test suite"
        assert suite["cases_json"] == cases

        loaded = eval_store.get_eval_suite(suite["id"])
        assert loaded is not None
        assert loaded["id"] == suite["id"]
        assert loaded["agent_id"] == suite["agent_id"]
        assert loaded["cases_json"] == cases


def test_list_eval_suites_filtered_by_agent_id(db_path) -> None:
    """list_eval_suites with agent_id returns only that agent's suites."""
    with env_vars({"DB_PATH": db_path, "DATABASE_URL": "", "SUPABASE_DATABASE_URL": ""}):
        eval_store.init_eval_db()
        eval_store.create_eval_suite("agent_a", "Suite A", [])
        eval_store.create_eval_suite("agent_b", "Suite B", [])
        eval_store.create_eval_suite("agent_a", "Suite A2", [])

        all_suites = eval_store.list_eval_suites()
        assert len(all_suites) == 3

        agent_a_suites = eval_store.list_eval_suites(agent_id="agent_a")
        assert len(agent_a_suites) == 2
        assert all(s["agent_id"] == "agent_a" for s in agent_a_suites)


def test_create_eval_run_and_set_status(db_path) -> None:
    """create_eval_run and set_eval_run_status persist correctly."""
    with env_vars({"DB_PATH": db_path, "DATABASE_URL": "", "SUPABASE_DATABASE_URL": ""}):
        eval_store.init_eval_db()
        suite = eval_store.create_eval_suite("agent_x", "Suite", [])
        run = eval_store.create_eval_run(suite["id"], "agent_x", agent_version="1")

        assert run["status"] == "queued"
        assert run["eval_suite_id"] == suite["id"]

        eval_store.set_eval_run_status(run["id"], "running")
        loaded = eval_store.get_eval_run(run["id"])
        assert loaded is not None
        assert loaded["status"] == "running"

        summary = {"passed": 2, "failed": 1, "errored": 0, "average_score": 0.67}
        eval_store.set_eval_run_status(run["id"], "succeeded", summary_json=summary)
        loaded = eval_store.get_eval_run(run["id"])
        assert loaded["status"] == "succeeded"
        assert loaded["summary_json"] == summary


def test_append_eval_case_results_and_list(db_path) -> None:
    """append_eval_case_result and list_eval_case_results persist and order by case_index."""
    with env_vars({"DB_PATH": db_path, "DATABASE_URL": "", "SUPABASE_DATABASE_URL": ""}):
        eval_store.init_eval_db()
        suite = eval_store.create_eval_suite("agent_y", "Suite", [])
        run = eval_store.create_eval_run(suite["id"], "agent_y")

        eval_store.append_eval_case_result(
            run["id"],
            case_index=0,
            status="passed",
            score=1.0,
            matcher_type="exact_json",
            expected_json={"a": 1},
            actual_json={"a": 1},
            run_id="runtime-run-123",
        )
        eval_store.append_eval_case_result(
            run["id"],
            case_index=1,
            status="failed",
            score=0.0,
            matcher_type="exact_json",
            message="Mismatch",
        )

        results = eval_store.list_eval_case_results(run["id"])
        assert len(results) == 2
        assert results[0]["case_index"] == 0
        assert results[0]["status"] == "passed"
        assert results[0]["score"] == 1.0
        assert results[0]["run_id"] == "runtime-run-123"
        assert results[0]["expected_json"] == {"a": 1}
        assert results[1]["case_index"] == 1
        assert results[1]["status"] == "failed"
        assert results[1]["message"] == "Mismatch"


def test_get_eval_run_returns_none_for_unknown_id(db_path) -> None:
    """get_eval_run returns None for non-existent id."""
    with env_vars({"DB_PATH": db_path, "DATABASE_URL": "", "SUPABASE_DATABASE_URL": ""}):
        eval_store.init_eval_db()
        assert eval_store.get_eval_run("nonexistent-id") is None


def test_get_eval_suite_returns_none_for_unknown_id(db_path) -> None:
    """get_eval_suite returns None for non-existent id."""
    with env_vars({"DB_PATH": db_path, "DATABASE_URL": "", "SUPABASE_DATABASE_URL": ""}):
        eval_store.init_eval_db()
        assert eval_store.get_eval_suite("nonexistent-id") is None
