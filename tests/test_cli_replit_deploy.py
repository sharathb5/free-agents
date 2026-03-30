"""Tests for Replit deploy helper (agent-id based deploy flow)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cli_replit_deploy import (
    _resolve_agent_spec,
    _replit_import_url,
    run_deploy_replit,
)

def test_replit_import_url_from_owner_repo_slug() -> None:
    assert _replit_import_url("myorg/cool-agent") == "https://replit.new/github.com/myorg/cool-agent"

def test_valid_agent_id_deploys_correct_repo_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = {
        "id": "langchain_ai_langgraph",
        "name": "LangGraph Agent",
        "github_url": "https://github.com/langchain-ai/langgraph.git",
        "run_command": "python3 -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-4280}",
        "required_secrets": ["OPENROUTER_API_KEY"],
    }
    monkeypatch.setattr("app.cli_replit_deploy.registry_store.get_agent", lambda agent_id: spec if agent_id == spec["id"] else None)
    monkeypatch.setattr("app.cli_replit_deploy.registry_store.list_agents", lambda **_: [])
    opened: list[str] = []
    monkeypatch.setattr("app.cli_replit_deploy.webbrowser.open", lambda url: opened.append(url))

    run_deploy_replit(spec["id"], root=tmp_path)

    assert opened == ["https://replit.new/github.com/langchain-ai/langgraph"]


def test_valid_agent_name_fuzzy_match_works(monkeypatch: pytest.MonkeyPatch) -> None:
    matched = {
        "id": "langchain_ai_langgraph",
        "name": "LangGraph Agent",
        "github_url": "https://github.com/langchain-ai/langgraph",
        "run_command": "uvicorn app.main:app",
        "required_secrets": ["OPENROUTER_API_KEY"],
    }
    monkeypatch.setattr("app.cli_replit_deploy.registry_store.get_agent", lambda agent_id: matched if agent_id == matched["id"] else None)
    monkeypatch.setattr(
        "app.cli_replit_deploy.registry_store.list_agents",
        lambda **_: [{"id": matched["id"], "name": matched["name"]}],
    )

    resolved = _resolve_agent_spec("LangGraph Agent")
    assert resolved["id"] == matched["id"]


def test_invalid_id_exits_with_clear_error_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("app.cli_replit_deploy.registry_store.get_agent", lambda _agent_id: None)
    monkeypatch.setattr("app.cli_replit_deploy.registry_store.list_agents", lambda **_: [])

    with pytest.raises(SystemExit) as exc:
        _resolve_agent_spec("does_not_exist")
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "Agent not found: does_not_exist" in captured.err


def test_dot_replit_run_command_matches_agent_spec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_cmd = "python main.py --mode production"
    spec = {
        "id": "demo_agent",
        "name": "Demo Agent",
        "github_url": "https://github.com/example/demo-agent",
        "run_command": run_cmd,
        "required_secrets": [],
    }
    monkeypatch.setattr("app.cli_replit_deploy.registry_store.get_agent", lambda agent_id: spec if agent_id == spec["id"] else None)
    monkeypatch.setattr("app.cli_replit_deploy.registry_store.list_agents", lambda **_: [])
    monkeypatch.setattr("app.cli_replit_deploy.webbrowser.open", lambda _url: True)

    run_deploy_replit(spec["id"], root=tmp_path)

    replit_text = (tmp_path / ".replit").read_text(encoding="utf-8")
    assert f'exec {run_cmd}' in replit_text


def test_deploy_falls_back_for_legacy_repo_to_agent_specs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy_spec = {
        "id": "langchain_ai_langgraph",
        "name": "sharathb5",
        "prompt": "You are an expert assistant for the langchain-ai/langgraph repository.",
        "github_url": None,
        "run_command": None,
    }
    monkeypatch.setattr(
        "app.cli_replit_deploy.registry_store.get_agent",
        lambda agent_id: legacy_spec if agent_id == legacy_spec["id"] else None,
    )
    monkeypatch.setattr("app.cli_replit_deploy.registry_store.list_agents", lambda **_: [])
    opened: list[str] = []
    monkeypatch.setattr("app.cli_replit_deploy.webbrowser.open", lambda url: opened.append(url))

    run_deploy_replit(legacy_spec["id"], root=tmp_path)

    assert opened == ["https://replit.new/github.com/langchain-ai/langgraph"]
    replit_text = (tmp_path / ".replit").read_text(encoding="utf-8")
    assert "exec python3 -m uvicorn app.main:app" in replit_text
