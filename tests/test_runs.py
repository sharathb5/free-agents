"""
Tests for Agent Runtime Part 1: runs API and runner loop.

- test_create_run_wait_true_returns_output_and_succeeded
- test_run_steps_persisted_and_ordered
- test_tool_call_action_fails_gracefully_when_tools_disabled
- test_wait_false_returns_run_id_and_status_then_run_completes
"""

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
    """Temporary DB path for run_store and session_store. Isolated per test."""
    with tempfile.TemporaryDirectory(prefix="agent_runs_") as tmp:
        yield str(Path(tmp) / "gateway.db")


@pytest.fixture
def app():
    """FastAPI app from runtime."""
    from app.main import app as fastapi_app  # type: ignore
    return fastapi_app


@pytest.fixture
def client(app):
    return TestClient(app)


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


def _init_and_seed_temp_db():
    """Initialize and seed the DB pointed at by get_settings() (e.g. temp path in tests)."""
    from app.preset_loader import PRESETS_DIR
    from app.storage import registry_store
    from app.storage import run_store
    from app.storage import session_store

    session_store.init_db()
    registry_store.init_registry_db()
    run_store.init_run_db()
    registry_store.seed_from_presets(PRESETS_DIR)


def _override_provider(app, provider):
    from app.dependencies import get_provider  # type: ignore
    app.dependency_overrides[get_provider] = lambda: provider
    return get_provider


class ActionContractProvider:
    """Provider that returns an action contract (final or tool_call) for the runner."""

    def __init__(self, action: Dict[str, Any]):
        self.action = action

    def complete_json(self, prompt: str, *, schema: Any) -> Any:
        from app.providers import ProviderResult  # type: ignore
        import json
        return ProviderResult(parsed_json=self.action, raw_text=json.dumps(self.action))


def test_create_run_wait_true_returns_output_and_succeeded(app, client, db_path):
    """
    POST /agents/{agent_id}/runs with wait=true and provider returning final
    yields 200 with run_id, status succeeded, output, and meta.step_count.
    Run and steps are persisted.
    """
    provider = ActionContractProvider({"type": "final", "output": {"summary": "ok", "bullets": ["a", "b"]}})
    with env_vars({
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
    }):
        _init_and_seed_temp_db()
        get_provider = _override_provider(app, provider)
        try:
            resp = client.post(
                "/agents/summarizer/runs",
                json={"input": {"text": "hello"}, "wait": True},
            )
        finally:
            app.dependency_overrides.pop(get_provider, None)

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("status") == "succeeded"
        assert "run_id" in data
        assert data.get("output") == {"summary": "ok", "bullets": ["a", "b"]}
        assert "meta" in data
        assert data["meta"].get("step_count") >= 1

        run_id = data["run_id"]
        get_resp = client.get(f"/runs/{run_id}")
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["status"] == "succeeded"
        assert get_data["step_count"] >= 1


def test_run_steps_persisted_and_ordered(app, client, db_path):
    """
    After a successful run with wait=true, GET /runs/{run_id}/steps returns
    steps ordered by step_index, including llm_action and final.
    """
    provider = ActionContractProvider({"type": "final", "output": {"result": "done"}})
    with env_vars({
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
    }):
        _init_and_seed_temp_db()
        get_provider = _override_provider(app, provider)
        try:
            resp = client.post(
                "/agents/summarizer/runs",
                json={"input": {"text": "hi"}, "wait": True},
            )
        finally:
            app.dependency_overrides.pop(get_provider, None)

        assert resp.status_code == 200
        run_id = resp.json()["run_id"]

        steps_resp = client.get(f"/runs/{run_id}/steps")
        assert steps_resp.status_code == 200
        steps_data = steps_resp.json()
        steps = steps_data["steps"]
        assert len(steps) >= 2
        step_types = [s["step_type"] for s in steps]
        assert "llm_action" in step_types
        assert "final" in step_types
        for i, s in enumerate(steps):
            assert s["step_index"] == i + 1, "steps must be ordered by step_index"


def test_tool_call_action_fails_gracefully_when_tools_disabled(app, client, db_path):
    """
    When the model returns type=tool_call, the run fails with a clear message
    and run_steps include tool_call and error.
    """
    provider = ActionContractProvider({"type": "tool_call", "tool_name": "search", "args": {"q": "x"}})
    with env_vars({
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
    }):
        _init_and_seed_temp_db()
        get_provider = _override_provider(app, provider)
        try:
            resp = client.post(
                "/agents/summarizer/runs",
                json={"input": {"text": "search me"}, "wait": True},
            )
        finally:
            app.dependency_overrides.pop(get_provider, None)

        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "failed"
        assert data.get("error") is not None
        assert "not enabled" in (data.get("error") or "").lower() or "tool" in (data.get("error") or "").lower()

        run_id = data["run_id"]
        steps_resp = client.get(f"/runs/{run_id}/steps?verbose=true")
        assert steps_resp.status_code == 200
        steps = steps_resp.json()["steps"]
        step_types = [s["step_type"] for s in steps]
        assert "llm_action" in step_types
        assert "tool_call" in step_types
        assert "error" in step_types


def test_wait_false_returns_run_id_and_status_then_run_completes(app, client, db_path):
    """
    POST with wait=false returns run_id and status queued; the run completes in the
    background; polling GET /runs/{run_id}/result eventually returns 200 with output.
    """
    provider = ActionContractProvider({"type": "final", "output": {"done": True}})
    with env_vars({
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
    }):
        _init_and_seed_temp_db()
        get_provider = _override_provider(app, provider)
        try:
            resp = client.post(
                "/agents/summarizer/runs",
                json={"input": {"text": "async"}, "wait": False},
            )
        finally:
            app.dependency_overrides.pop(get_provider, None)

        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert data.get("status") == "queued"

        run_id = data["run_id"]
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            result_resp = client.get(f"/runs/{run_id}/result")
            if result_resp.status_code == 200:
                assert result_resp.json().get("output") == {"done": True}
                return
            if result_resp.status_code == 400:
                pytest.fail(f"Run failed: {result_resp.json()}")
            time.sleep(0.05)
        pytest.fail("Run did not complete within 10s")


def test_sse_events_emits_steps_and_run_finished(app, client, db_path):
    """
    GET /runs/{run_id}/events streams SSE: at least one step event and a terminal run_finished.
    Start wait=false run then consume events until run_finished.
    """
    provider = ActionContractProvider({"type": "final", "output": {"done": True}})
    with env_vars({
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
    }):
        _init_and_seed_temp_db()
        get_provider = _override_provider(app, provider)
        try:
            resp = client.post(
                "/agents/summarizer/runs",
                json={"input": {"text": "sse test"}, "wait": False},
            )
        finally:
            app.dependency_overrides.pop(get_provider, None)
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]

        step_events = []
        run_finished = False
        ev = ""
        with client.stream("GET", f"/runs/{run_id}/events?heartbeat_seconds=60") as sresp:
            assert sresp.status_code == 200
            buf = ""
            for chunk in sresp.iter_text():
                buf += chunk
                while "\n\n" in buf:
                    part, buf = buf.split("\n\n", 1)
                    for line in part.split("\n"):
                        if line.startswith("event:"):
                            ev = line.split(":", 1)[1].strip()
                        elif line.startswith("data:"):
                            import json as _json
                            data = _json.loads(line.split(":", 1)[1].strip())
                            if ev == "step":
                                step_events.append(data)
                            elif ev == "run" and isinstance(data, dict) and data.get("event") == "run_finished":
                                run_finished = True
                                break
                    if run_finished:
                        break
            if not run_finished and buf:
                for line in buf.split("\n"):
                    if line.startswith("data:"):
                        import json as _json
                        data = _json.loads(line.split(":", 1)[1].strip())
                        if isinstance(data, dict) and data.get("event") == "run_finished":
                            run_finished = True
                            break

        assert len(step_events) >= 1, "expected at least one step event"
        assert run_finished, "expected run_finished event"


def test_replay_creates_new_run_with_parent_link(app, client, db_path):
    """
    Create a run that succeeds; POST /runs/{run_id}/replay with wait=true.
    Assert new run_id != original, output matches, parent_run_id in response and on GET.
    """
    provider = ActionContractProvider({"type": "final", "output": {"replay": "ok"}})
    with env_vars({
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
    }):
        _init_and_seed_temp_db()
        get_provider = _override_provider(app, provider)
        try:
            resp = client.post(
                "/agents/summarizer/runs",
                json={"input": {"text": "replay me"}, "wait": True},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("status") == "succeeded"
            original_run_id = data["run_id"]
            original_output = data.get("output")

            replay_resp = client.post(
                f"/runs/{original_run_id}/replay",
                json={"wait": True},
            )
            assert replay_resp.status_code == 200, replay_resp.text
            replay_data = replay_resp.json()
            new_run_id = replay_data["run_id"]
            assert new_run_id != original_run_id
            assert replay_data.get("status") == "succeeded"
            assert replay_data.get("output") == original_output
            assert replay_data.get("meta", {}).get("parent_run_id") == original_run_id

            get_resp = client.get(f"/runs/{new_run_id}")
            assert get_resp.status_code == 200
            assert get_resp.json().get("parent_run_id") == original_run_id
        finally:
            app.dependency_overrides.pop(get_provider, None)


def test_run_steps_include_observability_fields(app, client, db_path):
    """
    GET /runs/{id}/steps includes latency_ms, error_code, event_time (Part 3 observability).
    """
    provider = ActionContractProvider({"type": "final", "output": {"x": 1}})
    with env_vars({
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
    }):
        _init_and_seed_temp_db()
        get_provider = _override_provider(app, provider)
        try:
            resp = client.post(
                "/agents/summarizer/runs",
                json={"input": {"text": "obs"}, "wait": True},
            )
        finally:
            app.dependency_overrides.pop(get_provider, None)
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]
        steps_resp = client.get(f"/runs/{run_id}/steps")
        assert steps_resp.status_code == 200
        steps = steps_resp.json()["steps"]
        assert len(steps) >= 1
        for s in steps:
            assert "step_index" in s
            assert "step_type" in s
            assert "created_at" in s
            # Part 3 fields (may be null)
            assert "latency_ms" in s
            assert "error_code" in s
            assert "event_time" in s or "created_at" in s
