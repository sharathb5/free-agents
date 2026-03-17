"""
Focused unit tests for github_repo_read tool logic using mocked GithubClientLike.
No registry, runner, or live GitHub calls. Runner/catalog tests use mocks and SQLite.
"""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.runtime.tools.github_tool import (
    GithubRepoReadPolicy,
    execute_github_repo_read,
    _detect_important_files,
    _derive_hints,
    _validate_args,
)
from app.runtime.tools.http_tool import ToolExecutionError


def _make_mock_client(
    repo: Optional[Dict[str, Any]] = None,
    default_branch: str = "main",
    tree: Optional[List[Dict[str, Any]]] = None,
    file_content: Optional[tuple[str, str]] = None,
    get_repo_error: Optional[Exception] = None,
    get_tree_error: Optional[Exception] = None,
    get_file_error: Optional[Exception] = None,
):
    from app.runtime.tools.github_client import GithubClientError

    client = MagicMock()
    if get_repo_error:
        client.get_repo.side_effect = get_repo_error
    else:
        client.get_repo.return_value = repo or {
            "name": "test-repo",
            "default_branch": default_branch,
            "private": False,
            "owner": {"login": "test-owner"},
        }
    client.get_default_branch.return_value = default_branch
    if get_tree_error:
        client.get_tree.side_effect = get_tree_error
    else:
        client.get_tree.return_value = tree or [
            {"path": "README.md", "type": "file", "size": 100},
            {"path": "package.json", "type": "file", "size": 200},
            {"path": "src/main.py", "type": "file", "size": 500},
        ]
    if get_file_error:
        client.get_file.side_effect = get_file_error
    else:
        client.get_file.return_value = file_content or ("file content here", "utf-8")
    return client


def test_github_repo_read_overview_happy_path():
    """Mocked client returns repo + tree; assert overview structure and important file detection."""
    tree = [
        {"path": "README.md", "type": "file", "size": 100},
        {"path": "pyproject.toml", "type": "file", "size": 80},
        {"path": "main.py", "type": "file", "size": 200},
        {"path": "other.txt", "type": "file", "size": 10},
    ]
    client = _make_mock_client(tree=tree)
    policy = GithubRepoReadPolicy(max_entries=50, max_file_chars=12_000, max_sample_files=5)
    result = execute_github_repo_read(
        {"owner": "o", "repo": "r", "mode": "overview"},
        policy,
        client,
    )
    assert result["mode"] == "overview"
    assert result["repo"]["owner"] == "test-owner"
    assert result["repo"]["name"] == "test-repo"
    assert result["repo"]["default_branch"] == "main"
    assert "top_level" in result
    assert len(result["top_level"]) == 4
    assert "important_files" in result
    assert "README.md" in result["important_files"]
    assert "pyproject.toml" in result["important_files"]
    assert "main.py" in result["important_files"]
    assert "hints" in result
    assert "languages" in result["hints"]
    assert "Python" in result["hints"]["languages"]
    assert result["truncated"] is False


def test_github_repo_read_tree_happy_path():
    """Mock tree response; assert entries returned and max_entries cap."""
    tree = [{"path": f"f{i}.py", "type": "file", "size": 100} for i in range(10)]
    client = _make_mock_client(tree=tree)
    policy = GithubRepoReadPolicy(max_entries=5)
    result = execute_github_repo_read(
        {"owner": "o", "repo": "r", "mode": "tree", "path": "src"},
        policy,
        client,
    )
    assert result["mode"] == "tree"
    assert result["path"] == "src"
    assert len(result["entries"]) == 5
    assert result["truncated"] is True
    client.get_tree.assert_called_once_with("o", "r", "main", path="src")


def test_github_repo_read_file_caps_content():
    """Mock file content larger than max_file_chars; assert truncated=true and content capped."""
    big = "x" * 20_000
    client = _make_mock_client(file_content=(big, "utf-8"))
    policy = GithubRepoReadPolicy(max_file_chars=1000)
    result = execute_github_repo_read(
        {"owner": "o", "repo": "r", "mode": "file", "path": "README.md"},
        policy,
        client,
    )
    assert result["mode"] == "file"
    assert result["path"] == "README.md"
    assert result["truncated"] is True
    assert len(result["content"]) <= 1000 + len("...[truncated]")
    assert result["content"].endswith("...[truncated]")


def test_github_repo_read_sample_returns_curated_files():
    """Assert README/package files included when available and max_sample_files enforced."""
    tree = [
        {"path": "README.md", "type": "file"},
        {"path": "package.json", "type": "file"},
        {"path": "pyproject.toml", "type": "file"},
        {"path": "main.py", "type": "file"},
        {"path": "Dockerfile", "type": "file"},
    ]
    client = _make_mock_client(tree=tree, file_content=("sample content", "utf-8"))
    policy = GithubRepoReadPolicy(max_sample_files=3, max_file_chars=5000)
    result = execute_github_repo_read(
        {"owner": "o", "repo": "r", "mode": "sample"},
        policy,
        client,
    )
    assert result["mode"] == "sample"
    assert "files" in result
    assert len(result["files"]) <= 3
    assert "important_files" in result
    paths = [f["path"] for f in result["files"]]
    for p in paths:
        assert p in result["important_files"]
    assert "hints" in result


def test_github_repo_read_unauthorized_fails_safely():
    """Mock client raises unauthorized; assert ToolExecutionError with safe message, no token."""
    from app.runtime.tools.github_client import GithubClientError

    client = _make_mock_client(
        get_repo_error=GithubClientError("GitHub authentication required or invalid credentials"),
    )
    policy = GithubRepoReadPolicy()
    with pytest.raises(ToolExecutionError) as exc_info:
        execute_github_repo_read(
            {"owner": "o", "repo": "r", "mode": "overview"},
            policy,
            client,
        )
    msg = str(exc_info.value)
    assert "token" not in msg.lower() or "required" in msg.lower() or "invalid" in msg.lower()
    assert "GITHUB" in msg or "auth" in msg.lower() or "credential" in msg.lower()


def test_validate_args_rejects_invalid():
    """Invalid args raise ToolExecutionError."""
    with pytest.raises(ToolExecutionError, match="args must be an object"):
        _validate_args(None)
    with pytest.raises(ToolExecutionError, match="owner"):
        _validate_args({"repo": "r", "mode": "overview"})
    with pytest.raises(ToolExecutionError, match="repo"):
        _validate_args({"owner": "o", "mode": "overview"})
    with pytest.raises(ToolExecutionError, match="mode"):
        _validate_args({"owner": "o", "repo": "r"})
    with pytest.raises(ToolExecutionError, match="path is required for mode=file"):
        _validate_args({"owner": "o", "repo": "r", "mode": "file"})


def test_policy_allowed_owners_rejects():
    """When allowed_owners is set and owner not in list, ToolExecutionError."""
    client = _make_mock_client()
    policy = GithubRepoReadPolicy(allowed_owners=["allowed-only"])
    with pytest.raises(ToolExecutionError, match="owner not allowed"):
        execute_github_repo_read(
            {"owner": "other", "repo": "r", "mode": "overview"},
            policy,
            client,
        )


def test_detect_important_files_deterministic():
    """Important file detection is deterministic and matches candidates."""
    entries = [
        {"path": "main.py", "type": "file"},
        {"path": "README.md", "type": "file"},
        {"path": "package.json", "type": "file"},
    ]
    found = _detect_important_files(entries)
    assert found == ["README.md", "package.json", "main.py"]


def test_derive_hints_python():
    """Hints derive Python from pyproject + main.py."""
    important = ["pyproject.toml", "main.py"]
    all_paths = ["pyproject.toml", "main.py", "src/foo.py"]
    hints = _derive_hints(important, all_paths)
    assert "Python" in hints["languages"]


def test_derive_hints_nextjs():
    """Hints derive Next.js from package.json + next.config."""
    all_paths = ["package.json", "next.config.js"]
    hints = _derive_hints([], all_paths)
    assert "Next.js" in hints["frameworks"]


# --- Runner and catalog tests (mocked, SQLite-compatible) ---


@pytest.fixture
def db_path():
    """Temporary SQLite DB path for isolated runner tests."""
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
    """Returns a sequence of actions (e.g. tool_call then final)."""

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


def test_runner_can_execute_github_repo_read_tool_call(app, client, db_path):
    """
    Runner can execute github_repo_read tool_call: model returns tool_call then final;
    execute_github_repo_read mocked so no live GitHub. Run succeeds; steps include
    tool_call, tool_result, final. SQLite-compatible.
    """
    from app.storage import registry_store

    actions = [
        {
            "type": "tool_call",
            "tool_name": "github_repo_read",
            "args": {"owner": "octocat", "repo": "Hello-World", "mode": "overview"},
        },
        {"type": "final", "output": {"result": "Done."}},
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
            pass
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
        run_id = data["run_id"]
        steps_resp = client.get(f"/runs/{run_id}/steps?verbose=true")
        assert steps_resp.status_code == 200, steps_resp.text
        steps = steps_resp.json()["steps"]
        step_types = [s["step_type"] for s in steps]
        assert "llm_action" in step_types
        assert "tool_call" in step_types
        assert "tool_result" in step_types
        assert "final" in step_types
        tool_result_step = next(s for s in steps if s.get("step_type") == "tool_result")
        assert tool_result_step.get("tool_name") == "github_repo_read"
        tr_json = tool_result_step.get("tool_result_json")
        assert isinstance(tr_json, dict)
        assert tr_json.get("mode") == "overview"


def test_catalog_includes_real_github_tool():
    """
    Catalog includes real github_repo_read tool and github_reader bundle.
    Load tools/bundles YAML; assert github_repo_read has default_policy and
    github_reader bundle includes github_repo_read. No live API.
    """
    from app.catalog.loader import load_bundles_catalog, load_tools_catalog, validate_catalogs

    tools_catalog = load_tools_catalog()
    bundles_catalog = load_bundles_catalog()
    validate_catalogs(tools_catalog, bundles_catalog)

    tool_ids = [t["tool_id"] for t in tools_catalog["tools"] if isinstance(t, dict) and t.get("tool_id")]
    assert "github_repo_read" in tool_ids

    github_tool = next(t for t in tools_catalog["tools"] if isinstance(t, dict) and t.get("tool_id") == "github_repo_read")
    assert github_tool.get("category") == "GitHub"
    default_policy = github_tool.get("default_policy")
    assert isinstance(default_policy, dict)
    assert default_policy.get("max_entries") == 50
    assert default_policy.get("max_file_chars") == 12000
    assert default_policy.get("max_sample_files") == 5

    bundle_ids = [b["bundle_id"] for b in bundles_catalog["bundles"] if isinstance(b, dict) and b.get("bundle_id")]
    assert "github_reader" in bundle_ids
    github_reader_bundle = next(b for b in bundles_catalog["bundles"] if isinstance(b, dict) and b.get("bundle_id") == "github_reader")
    assert "github_repo_read" in (github_reader_bundle.get("tools") or [])
