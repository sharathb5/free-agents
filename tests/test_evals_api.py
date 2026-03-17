"""
Tests for Part 6 evals API: create suite, list, get, run (wait true/false), get run, get results.
"""

from __future__ import annotations

import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory(prefix="agent_evals_api_") as tmp:
        yield str(Path(tmp) / "gateway.db")


@pytest.fixture
def app():
    from app.main import app as fastapi_app
    return fastapi_app


@pytest.fixture
def client(app):
    return TestClient(app)


@contextmanager
def env_vars(env: Dict[str, str]):
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


def _init_and_seed(db_path):
    from app.preset_loader import PRESETS_DIR
    from app.storage import eval_store
    from app.storage import registry_store
    from app.storage import run_store
    from app.storage import session_store

    session_store.init_db()
    registry_store.init_registry_db()
    run_store.init_run_db()
    eval_store.init_eval_db()
    registry_store.seed_from_presets(PRESETS_DIR)


class ActionContractProvider:
    def __init__(self, action: Dict[str, Any]):
        self.action = action

    def complete_json(self, prompt: str, *, schema: Any) -> Any:
        import json
        from app.providers import ProviderResult
        return ProviderResult(parsed_json=self.action, raw_text=json.dumps(self.action))


def _override_provider(app, provider):
    from app.dependencies import get_provider
    app.dependency_overrides[get_provider] = lambda: provider
    return get_provider


def test_post_agents_evals_creates_suite(app, client, db_path) -> None:
    """POST /agents/{agent_id}/evals creates suite and returns 201."""
    with env_vars({
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
    }):
        _init_and_seed(db_path)
        resp = client.post(
            "/agents/summarizer/evals",
            json={
                "name": "My Suite",
                "description": "Test",
                "cases": [
                    {"name": "c1", "input": {"x": 1}, "expected": {"y": 2}, "matcher": {"type": "exact_json"}},
                ],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["name"] == "My Suite"
        assert data["agent_id"] == "summarizer"


def test_post_evals_rejects_invalid_matcher(app, client, db_path) -> None:
    """POST /agents/{agent_id}/evals rejects invalid matcher type with 400."""
    with env_vars({
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
    }):
        from app.storage import eval_store
        from app.storage import registry_store
        from app.storage import run_store
        from app.storage import session_store
        from app.preset_loader import PRESETS_DIR

        session_store.init_db()
        registry_store.init_registry_db()
        run_store.init_run_db()
        eval_store.init_eval_db()
        registry_store.seed_from_presets(PRESETS_DIR)

        resp = client.post(
            "/agents/summarizer/evals",
            json={
                "name": "Bad",
                "cases": [
                    {"name": "c1", "input": {}, "expected": {}, "matcher": {"type": "invalid_type"}},
                ],
            },
        )
        assert resp.status_code == 400


def test_get_agents_evals_lists_suites(app, client, db_path) -> None:
    """GET /agents/{agent_id}/evals returns list of suites."""
    with env_vars({
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
    }):
        _init_and_seed(db_path)
        from app.storage import eval_store
        eval_store.create_eval_suite("summarizer", "Suite A", [])
        eval_store.create_eval_suite("summarizer", "Suite B", [])

        resp = client.get("/agents/summarizer/evals")
        assert resp.status_code == 200
        data = resp.json()
        assert "suites" in data
        assert len(data["suites"]) == 2


def test_get_evals_suite_id_returns_suite(app, client, db_path) -> None:
    """GET /evals/{eval_suite_id} returns suite with cases."""
    with env_vars({
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
    }):
        _init_and_seed(db_path)
        from app.storage import eval_store
        suite = eval_store.create_eval_suite("summarizer", "S", [{"name": "c", "input": {}, "expected": {}, "matcher": {"type": "exact_json"}}])

        resp = client.get(f"/evals/{suite['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == suite["id"]
        assert data["name"] == "S"
        assert len(data["cases"]) == 1


def test_post_evals_run_wait_true_returns_summary(app, client, db_path) -> None:
    """POST /evals/{eval_suite_id}/run with wait=true returns eval_run_id and summary."""
    with env_vars({
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
    }):
        _init_and_seed(db_path)
        provider = ActionContractProvider({"type": "final", "output": {"ok": True}})
        _override_provider(app, provider)

        from app.storage import eval_store
        suite = eval_store.create_eval_suite(
            "summarizer",
            "S",
            [{"name": "c", "input": {}, "expected": {"ok": True}, "matcher": {"type": "exact_json"}}],
        )

        resp = client.post(f"/evals/{suite['id']}/run", json={"wait": True})
        assert resp.status_code == 200
        data = resp.json()
        assert "eval_run_id" in data
        assert data["status"] == "succeeded"
        assert data["summary"]["passed"] == 1
        assert data["summary"]["total_cases"] == 1


def test_post_evals_run_wait_false_returns_immediately(app, client, db_path) -> None:
    """POST /evals/{eval_suite_id}/run with wait=false returns eval_run_id immediately."""
    with env_vars({
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
    }):
        _init_and_seed(db_path)
        provider = ActionContractProvider({"type": "final", "output": {"ok": True}})
        overridden = _override_provider(app, provider)
        try:
            from app.storage import eval_store
            suite = eval_store.create_eval_suite(
                "summarizer",
                "S",
                [{"name": "c", "input": {}, "expected": {"ok": True}, "matcher": {"type": "exact_json"}}],
            )

            resp = client.post(f"/evals/{suite['id']}/run", json={"wait": False})
            assert resp.status_code == 200
            data = resp.json()
            assert "eval_run_id" in data
            assert data["status"] == "running"

            eval_run_id = data["eval_run_id"]
            for _ in range(20):
                time.sleep(0.15)
                get_resp = client.get(f"/eval-runs/{eval_run_id}")
                if get_resp.status_code == 200:
                    run_data = get_resp.json()
                    if run_data["status"] in ("succeeded", "failed"):
                        assert run_data["status"] == "succeeded"
                        break
            else:
                pytest.fail("Eval run did not complete within timeout")
        finally:
            app.dependency_overrides.pop(overridden, None)


def test_get_eval_runs_id_returns_run(app, client, db_path) -> None:
    """GET /eval-runs/{eval_run_id} returns run status and summary."""
    with env_vars({
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
    }):
        _init_and_seed(db_path)
        provider = ActionContractProvider({"type": "final", "output": {}})
        _override_provider(app, provider)

        from app.storage import eval_store
        suite = eval_store.create_eval_suite("summarizer", "S", [{"name": "c", "input": {}, "expected": {}, "matcher": {"type": "exact_json"}}])
        resp = client.post(f"/evals/{suite['id']}/run", json={"wait": True})
        eval_run_id = resp.json()["eval_run_id"]

        get_resp = client.get(f"/eval-runs/{eval_run_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["eval_run_id"] == eval_run_id
        assert data["status"] == "succeeded"
        assert "summary" in data


def test_get_eval_runs_id_results_returns_case_results(app, client, db_path) -> None:
    """GET /eval-runs/{eval_run_id}/results returns case results."""
    with env_vars({
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
    }):
        _init_and_seed(db_path)
        provider = ActionContractProvider({"type": "final", "output": {"x": 1}})
        _override_provider(app, provider)

        from app.storage import eval_store
        suite = eval_store.create_eval_suite(
            "summarizer",
            "S",
            [{"name": "c", "input": {}, "expected": {"x": 1}, "matcher": {"type": "exact_json"}}],
        )
        resp = client.post(f"/evals/{suite['id']}/run", json={"wait": True})
        eval_run_id = resp.json()["eval_run_id"]

        results_resp = client.get(f"/eval-runs/{eval_run_id}/results")
        assert results_resp.status_code == 200
        data = results_resp.json()
        assert "results" in data
        assert len(data["results"]) == 1
        assert data["results"][0]["status"] == "passed"
        assert data["results"][0]["run_id"] is not None


def test_get_evals_suite_404(app, client, db_path) -> None:
    """GET /evals/{eval_suite_id} returns 404 for unknown id."""
    with env_vars({"DB_PATH": db_path, "DATABASE_URL": "", "SUPABASE_DATABASE_URL": ""}):
        from app.storage import eval_store
        eval_store.init_eval_db()
        resp = client.get("/evals/nonexistent-id")
        assert resp.status_code == 404


def test_get_eval_runs_404(app, client, db_path) -> None:
    """GET /eval-runs/{eval_run_id} returns 404 for unknown id."""
    with env_vars({"DB_PATH": db_path, "DATABASE_URL": "", "SUPABASE_DATABASE_URL": ""}):
        from app.storage import eval_store
        eval_store.init_eval_db()
        resp = client.get("/eval-runs/nonexistent-id")
        assert resp.status_code == 404
