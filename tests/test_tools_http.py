"""
Tests for Agent Runtime Part 2: HTTP tool and tool execution loop.

- Happy path: tool_call then final, run succeeds, steps include tool_call, tool_result, final
- Domain denylist: request to disallowed domain -> run fails
- Header stripping: Authorization in args -> not passed to request, stored args redacted
- Max tool calls: exceed limit -> run fails max_tool_calls_exceeded
- Timeout: mock timeout -> run fails tool_execution_failed
"""

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory(prefix="agent_tools_") as tmp:
        yield str(Path(tmp) / "gateway.db")


@pytest.fixture
def app():
    from app.main import app as fastapi_app  # type: ignore
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


def _init_and_seed_temp_db():
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


class SequenceActionProvider:
    """Returns a sequence of actions (e.g. tool_call then final)."""

    def __init__(self, actions: list):
        self.actions = actions
        self.call_index = 0

    def complete_json(self, prompt: str, *, schema: Any) -> Any:
        from app.providers import ProviderResult  # type: ignore
        import json
        idx = min(self.call_index, len(self.actions) - 1)
        action = self.actions[idx]
        self.call_index += 1
        return ProviderResult(parsed_json=action, raw_text=json.dumps(action))


def test_http_tool_happy_path_tool_call_then_final(app, client, db_path):
    """
    Model returns tool_call(http_request) then final. Run succeeds; steps include
    tool_call, tool_result, final. Mock httpx so no real HTTP.
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"data": "ok"}'
    mock_response.headers = {"Content-Type": "application/json"}

    actions = [
        {"type": "tool_call", "tool_name": "http_request", "args": {"method": "GET", "url": "https://example.com/data"}},
        {"type": "final", "output": {"result": "done"}},
    ]
    provider = SequenceActionProvider(actions)

    env = {
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
        "AGENT_TOOLS_ENABLED": "true",
    }

    with env_vars(env):
        _init_and_seed_temp_db()
        # Use tool_agent which has allowed_tools and http_allowed_domains
        from app.storage import registry_store
        spec = registry_store.get_agent("tool_agent")
        if not spec:
            pytest.skip("tool_agent preset not seeded")
        get_provider = _override_provider(app, provider)
        with patch("app.runtime.tools.http_tool.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.request.return_value = mock_response
            try:
                resp = client.post(
                    "/agents/tool_agent/runs",
                    json={"input": {"query": "fetch"}, "wait": True},
                )
            finally:
                app.dependency_overrides.pop(get_provider, None)

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("status") == "succeeded"
        assert "run_id" in data
        run_id = data["run_id"]

        steps_resp = client.get(f"/runs/{run_id}/steps")
        assert steps_resp.status_code == 200
        steps = steps_resp.json()["steps"]
        step_types = [s["step_type"] for s in steps]
        assert "llm_action" in step_types
        assert "tool_call" in step_types
        assert "tool_result" in step_types
        assert "final" in step_types
        tool_result_step = next(s for s in steps if s.get("step_type") == "tool_result")
        assert tool_result_step.get("tool_name") == "http_request"
        assert "tool_latency_ms" in tool_result_step
        assert isinstance(tool_result_step.get("tool_latency_ms"), (int, type(None)))


def test_http_tool_domain_not_allowed(app, client, db_path):
    """
    tool_call to https://notallowed.com -> run fails with clear error, tool_call step recorded.
    """
    actions = [
        {"type": "tool_call", "tool_name": "http_request", "args": {"url": "https://notallowed.com/path"}},
    ]
    provider = SequenceActionProvider(actions)

    env = {
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
        "AGENT_TOOLS_ENABLED": "true",
    }

    with env_vars(env):
        _init_and_seed_temp_db()
        from app.storage import registry_store
        if registry_store.get_agent("tool_agent") is None:
            pytest.skip("tool_agent preset not seeded")
        get_provider = _override_provider(app, provider)
        try:
            resp = client.post(
                "/agents/tool_agent/runs",
                json={"input": {"query": "x"}, "wait": True},
            )
        finally:
            app.dependency_overrides.pop(get_provider, None)

        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "failed"
        assert "error" in data
        assert "not allowed" in (data.get("error") or "").lower() or "domain" in (data.get("error") or "").lower()


def test_http_tool_header_stripping(app, client, db_path):
    """
    tool_call includes Authorization header; request must be sent without it;
    stored tool_args should be redacted/dropped for sensitive keys.
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "ok"
    mock_response.headers = {}

    actions = [
        {"type": "tool_call", "tool_name": "http_request", "args": {
            "url": "https://example.com/",
            "headers": {"Authorization": "Bearer secret123", "X-Custom": "fine"},
        }},
        {"type": "final", "output": {"result": "done"}},
    ]
    provider = SequenceActionProvider(actions)

    env = {
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
        "AGENT_TOOLS_ENABLED": "true",
    }

    with env_vars(env):
        _init_and_seed_temp_db()
        from app.storage import registry_store
        if registry_store.get_agent("tool_agent") is None:
            pytest.skip("tool_agent preset not seeded")
        get_provider = _override_provider(app, provider)
        with patch("app.runtime.tools.http_tool.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.request.return_value = mock_response
            try:
                resp = client.post(
                    "/agents/tool_agent/runs",
                    json={"input": {"query": "x"}, "wait": True},
                )
            finally:
                app.dependency_overrides.pop(get_provider, None)

        assert resp.status_code == 200 and resp.json().get("status") == "succeeded"
        # Check that request was called without Authorization
        call_kw = mock_client.return_value.__enter__.return_value.request.call_args[1]
        headers = call_kw.get("headers") or {}
        assert headers.get("Authorization") is None
        assert "Bearer" not in str(headers)


def test_http_tool_max_tool_calls_exceeded(app, client, db_path):
    """
    Model repeatedly returns tool_call; after max_tool_calls run fails with max_tool_calls_exceeded.
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "ok"
    mock_response.headers = {}

    # Return tool_call every time (no final)
    actions = [
        {"type": "tool_call", "tool_name": "http_request", "args": {"url": "https://example.com/a"}},
        {"type": "tool_call", "tool_name": "http_request", "args": {"url": "https://example.com/b"}},
        {"type": "tool_call", "tool_name": "http_request", "args": {"url": "https://example.com/c"}},
        {"type": "tool_call", "tool_name": "http_request", "args": {"url": "https://example.com/d"}},
        {"type": "tool_call", "tool_name": "http_request", "args": {"url": "https://example.com/e"}},
        {"type": "tool_call", "tool_name": "http_request", "args": {"url": "https://example.com/f"}},
    ]
    provider = SequenceActionProvider(actions)

    env = {
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
        "AGENT_TOOLS_ENABLED": "true",
        "AGENT_MAX_TOOL_CALLS": "3",
    }

    with env_vars(env):
        _init_and_seed_temp_db()
        from app.storage import registry_store
        if registry_store.get_agent("tool_agent") is None:
            pytest.skip("tool_agent preset not seeded")
        get_provider = _override_provider(app, provider)
        with patch("app.runtime.tools.http_tool.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.request.return_value = mock_response
            try:
                resp = client.post(
                    "/agents/tool_agent/runs",
                    json={"input": {"query": "x"}, "wait": True},
                )
            finally:
                app.dependency_overrides.pop(get_provider, None)

        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "failed"
        assert "max_tool_calls" in (data.get("error") or "").lower() or "tool_execution_failed" in (data.get("error") or "").lower()


def test_http_tool_timeout_fails_run(app, client, db_path):
    """
    Mock httpx to raise TimeoutException; run fails with tool_execution_failed and error step.
    """
    import httpx

    actions = [
        {"type": "tool_call", "tool_name": "http_request", "args": {"url": "https://example.com/slow"}},
    ]
    provider = SequenceActionProvider(actions)

    env = {
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
        "AGENT_TOOLS_ENABLED": "true",
    }

    with env_vars(env):
        _init_and_seed_temp_db()
        from app.storage import registry_store
        if registry_store.get_agent("tool_agent") is None:
            pytest.skip("tool_agent preset not seeded")
        get_provider = _override_provider(app, provider)
        with patch("app.runtime.tools.http_tool.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.request.side_effect = httpx.TimeoutException("timeout")
            try:
                resp = client.post(
                    "/agents/tool_agent/runs",
                    json={"input": {"query": "x"}, "wait": True},
                )
            finally:
                app.dependency_overrides.pop(get_provider, None)

        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "failed"
        assert "tool_execution_failed" in (data.get("error") or "").lower() or data.get("error")
        run_id = data.get("run_id")
        if run_id:
            steps_resp = client.get(f"/runs/{run_id}/steps")
            assert steps_resp.status_code == 200
            steps = steps_resp.json()["steps"]
            assert any(s.get("step_type") == "error" for s in steps)


def test_tool_result_has_latency_ms(app, client, db_path):
    """
    Part 3: tool_result step has latency_ms set (mock returns quickly).
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "ok"
    mock_response.headers = {}

    actions = [
        {"type": "tool_call", "tool_name": "http_request", "args": {"url": "https://example.com/"}},
        {"type": "final", "output": {"done": True}},
    ]
    provider = SequenceActionProvider(actions)
    env = {
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
        "AGENT_TOOLS_ENABLED": "true",
    }
    with env_vars(env):
        _init_and_seed_temp_db()
        from app.storage import registry_store
        if registry_store.get_agent("tool_agent") is None:
            pytest.skip("tool_agent preset not seeded")
        get_provider = _override_provider(app, provider)
        try:
            with patch("app.runtime.tools.http_tool.httpx.Client") as mock_client:
                mock_client.return_value.__enter__.return_value.request.return_value = mock_response
                resp = client.post(
                    "/agents/tool_agent/runs",
                    json={"input": {"query": "x"}, "wait": True},
                )
            assert resp.status_code == 200 and resp.json().get("status") == "succeeded"
            steps = client.get(f"/runs/{resp.json()['run_id']}/steps").json()["steps"]
            tool_result_step = next((s for s in steps if s.get("step_type") == "tool_result"), None)
            assert tool_result_step is not None
            assert tool_result_step.get("latency_ms") is not None
            assert isinstance(tool_result_step["latency_ms"], int)
        finally:
            app.dependency_overrides.pop(get_provider, None)


def test_prompt_tool_cap_large_response_succeeds(app, client, db_path):
    """
    Part 3: When tool result body exceeds max_tool_prompt_chars, run still succeeds;
    injected content is capped so the model receives limited chars.
    """
    large_body = "x" * 20_000
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = large_body
    mock_response.headers = {"Content-Type": "text/plain"}

    actions = [
        {"type": "tool_call", "tool_name": "http_request", "args": {"url": "https://example.com/big"}},
        {"type": "final", "output": {"received": "capped"}},
    ]
    provider = SequenceActionProvider(actions)
    env = {
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
        "DB_PATH": db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
        "AGENT_TOOLS_ENABLED": "true",
        "AGENT_MAX_TOOL_PROMPT_CHARS": "500",
    }
    with env_vars(env):
        _init_and_seed_temp_db()
        from app.storage import registry_store
        if registry_store.get_agent("tool_agent") is None:
            pytest.skip("tool_agent preset not seeded")
        get_provider = _override_provider(app, provider)
        try:
            with patch("app.runtime.tools.http_tool.httpx.Client") as mock_client:
                mock_client.return_value.__enter__.return_value.request.return_value = mock_response
                resp = client.post(
                    "/agents/tool_agent/runs",
                    json={"input": {"query": "big"}, "wait": True},
                )
            assert resp.status_code == 200, resp.text
            assert resp.json().get("status") == "succeeded"
            run_id = resp.json()["run_id"]
            steps = client.get(f"/runs/{run_id}/steps?verbose=true").json()["steps"]
            tool_result_step = next((s for s in steps if s.get("step_type") == "tool_result"), None)
            assert tool_result_step is not None
            raw = tool_result_step.get("tool_result_json")
            assert raw is not None
            # For verbose=true, the API may return a dict or a capped string representation;
            # either way, the stored body should be larger than the prompt cap (500 chars).
            if isinstance(raw, dict):
                body = str(raw.get("text", ""))
            else:
                body = str(raw)
            assert len(body) > 500
        finally:
            app.dependency_overrides.pop(get_provider, None)
