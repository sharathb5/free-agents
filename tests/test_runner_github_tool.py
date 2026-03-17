"""
Targeted integration tests: runner + registry execute github_repo_read.
Mock GitHub tool execution so no live API; assert run steps and success.
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
    with tempfile.TemporaryDirectory(prefix="agent_github_") as tmp:
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


def _minimal_github_reader_spec() -> Dict[str, Any]:
    """Minimal agent spec with bundle_id github_reader for resolution."""
    return {
        "id": "github_reader_agent",
        "version": "1.0.0",
        "name": "GitHub Reader Agent",
        "description": "Read GitHub repos",
        "primitive": "transform",
        "prompt": "Use github_repo_read to inspect the repo. Return final with a short summary.",
        "input_schema": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}}},
        "output_schema": {"type": "object", "properties": {"result": {"type": "string"}}},
        "bundle_id": "github_reader",
    }


class SequenceActionProvider:
    def __init__(self, actions: list):
        self.actions = actions
        self.call_index = 0

    def complete_json(self, prompt: str, *, schema: Any) -> Any:
        import json
        from app.providers import ProviderResult  # type: ignore
        idx = min(self.call_index, len(self.actions) - 1)
        action = self.actions[idx]
        self.call_index += 1
        return ProviderResult(parsed_json=action, raw_text=json.dumps(action))


def test_runner_executes_github_repo_read_tool_call(app, client, db_path):
    """
    Agent with github_reader bundle: model returns tool_call github_repo_read then final.
    Mock execute_github_repo_read so no live GitHub; assert run succeeds and steps include
    tool_call, tool_result, final.
    """
    from app.storage import registry_store

    actions = [
        {
            "type": "tool_call",
            "tool_name": "github_repo_read",
            "args": {"owner": "octocat", "repo": "Hello-World", "mode": "overview"},
        },
        {"type": "final", "output": {"result": "Repo has README and sample files."}},
    ]
    provider = SequenceActionProvider(actions)

    mock_result = {
        "mode": "overview",
        "repo": {"owner": "octocat", "name": "Hello-World", "default_branch": "main", "private": False},
        "top_level": [{"path": "README.md", "type": "file"}],
        "important_files": ["README.md"],
        "hints": {"languages": [], "frameworks": []},
        "truncated": False,
    }

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
        try:
            registry_store.register_agent(_minimal_github_reader_spec())
        except Exception:
            pass  # may already exist
        get_provider = _override_provider(app, provider)
        with patch("app.runtime.tools.registry.execute_github_repo_read", return_value=mock_result):
            try:
                resp = client.post(
                    "/agents/github_reader_agent/runs",
                    json={"input": {"owner": "octocat", "repo": "Hello-World"}, "wait": True},
                )
            finally:
                app.dependency_overrides.pop(get_provider, None)

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("status") == "succeeded"
        assert "run_id" in data
        run_id = data["run_id"]

        steps_resp = client.get(f"/runs/{run_id}/steps?verbose=true")
        assert steps_resp.status_code == 200, steps_resp.text
        steps = steps_resp.json()["steps"]
        step_types = [s["step_type"] for s in steps]
        assert "llm_action" in step_types
        assert "tool_call" in step_types
        assert "tool_result" in step_types
        assert "final" in step_types

        tool_call_step = next(s for s in steps if s.get("step_type") == "tool_call")
        assert tool_call_step.get("tool_name") == "github_repo_read"

        tool_result_step = next(s for s in steps if s.get("step_type") == "tool_result")
        assert tool_result_step.get("tool_name") == "github_repo_read"
        tr_json = tool_result_step.get("tool_result_json")
        assert isinstance(tr_json, dict)
        assert tr_json.get("mode") == "overview"
        assert tr_json.get("repo", {}).get("name") == "Hello-World"


def test_runner_prompt_includes_github_repo_read_when_allowed(app, db_path):
    """
    When preset has allowed_tools including github_repo_read, _build_prompt
    includes a line for github_repo_read. Verified indirectly via run that
    uses the tool (prompt was built with that tool available).
    """
    from app.registry_adapter import spec_to_preset
    from app.runtime.runner import _build_prompt
    from app.runtime.tools.registry import build_run_context
    from app.storage import registry_store

    with env_vars({"DB_PATH": db_path, "DATABASE_URL": "", "SUPABASE_DATABASE_URL": ""}):
        _init_and_seed_temp_db()
        try:
            registry_store.register_agent(_minimal_github_reader_spec())
        except Exception:
            pass
        spec = registry_store.get_agent("github_reader_agent")
        if not spec:
            pytest.skip("github_reader_agent not in registry")
        preset = spec_to_preset(spec)
        run_context = build_run_context(run_id="test", preset=preset)
        assert "github_repo_read" in run_context.allowed_tools
        mock_registry = MagicMock()
        prompt = _build_prompt(
            preset,
            [],
            {"owner": "o", "repo": "r"},
            [],
            tool_registry=mock_registry,
            run_context=run_context,
        )
        assert "github_repo_read" in prompt
        assert "overview" in prompt or "tree" in prompt or "file" in prompt or "sample" in prompt
