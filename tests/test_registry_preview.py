"""Integration tests for registry preview_register_agent and POST /agents/register preview endpoints."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from app.repo_to_agent.canonical_agent_id import (
    canonical_agent_id_from_repo,
    deterministic_import_version,
)


@pytest.fixture
def app():
    from app.main import app as fastapi_app

    return fastapi_app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def gateway_db_path() -> str:
    import tempfile

    with tempfile.TemporaryDirectory(prefix="gateway_preview_") as tmp:
        yield str(Path(tmp) / "gateway.db")


@contextmanager
def env_vars(env: Dict[str, str]):
    old: Dict[str, Any] = {}
    for key, value in env.items():
        old[key] = os.environ.get(key)
        os.environ[key] = value
    try:
        yield
    finally:
        for key, prev in old.items():
            if prev is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prev


def _make_valid_spec(agent_id: str, version: str) -> Dict[str, Any]:
    return {
        "id": agent_id,
        "version": version,
        "name": f"{agent_id} name",
        "description": f"{agent_id} description",
        "primitive": "transform",
        "input_schema": {
            "type": "object",
            "required": ["text"],
            "properties": {"text": {"type": "string", "title": "Text input"}},
        },
        "output_schema": {
            "type": "object",
            "required": ["summary"],
            "properties": {"summary": {"type": "string", "title": "Summary text"}},
        },
        "prompt": "You are a helpful test agent.",
        "supports_memory": True,
        "memory_policy": {
            "mode": "last_n",
            "max_messages": 2,
            "max_chars": 8000,
        },
    }


def test_preview_register_agent_conflict_after_insert(gateway_db_path: str) -> None:
    from app.storage import registry_store

    spec = _make_valid_spec("preview-agent", "1.0.0")
    with env_vars(
        {
            "DB_PATH": gateway_db_path,
            "SESSION_DB_PATH": gateway_db_path,
            "DATABASE_URL": "",
            "SUPABASE_DATABASE_URL": "",
        }
    ):
        registry_store.init_registry_db()
        first = registry_store.preview_register_agent(spec, owner_user_id=None)
        assert first["would_register"] is True
        assert first["would_conflict"] is False
        registry_store.register_agent(spec, owner_user_id=None)
        second = registry_store.preview_register_agent(spec, owner_user_id=None)
        assert second["would_register"] is False
        assert second["would_conflict"] is True
        assert second["existing"] is not None
        assert second["existing"]["agent_id"] == "preview-agent"
        assert second["existing"]["version"] == "1.0.0"


def test_post_register_preview_and_dry_run(client: TestClient, gateway_db_path: str) -> None:
    spec = _make_valid_spec("api-preview-agent", "2.0.0")
    env = {
        "DB_PATH": gateway_db_path,
        "SESSION_DB_PATH": gateway_db_path,
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
    }
    with env_vars(env):
        r1 = client.post("/agents/register/preview", json={"spec": spec})
        assert r1.status_code == 200
        b1 = r1.json()
        assert b1.get("ok") is True
        assert b1.get("dry_run") is True
        assert b1.get("would_register") is True
        assert b1.get("would_conflict") is False

        r2 = client.post("/agents/register?dry_run=true", json={"spec": spec})
        assert r2.status_code == 200
        assert r2.json().get("would_register") is True

        r3 = client.post("/agents/register", json={"spec": spec})
        assert r3.status_code == 200

        r4 = client.post("/agents/register/preview", json={"spec": spec})
        assert r4.status_code == 200
        b4 = r4.json()
        assert b4.get("would_conflict") is True
        assert b4.get("would_register") is False
        assert b4.get("existing", {}).get("version") == "2.0.0"


def test_same_repo_coordinates_same_preview_twice(gateway_db_path: str) -> None:
    """Same owner/repo → same (id, version); second register hits AgentVersionExists."""
    from app.storage import registry_store

    owner, repo = "acme-corp", "billing_svc"
    aid = canonical_agent_id_from_repo(owner, repo)
    ver = deterministic_import_version("0.1.0", owner, repo)
    spec = _make_valid_spec(aid, ver)
    with env_vars(
        {
            "DB_PATH": gateway_db_path,
            "SESSION_DB_PATH": gateway_db_path,
            "DATABASE_URL": "",
            "SUPABASE_DATABASE_URL": "",
        }
    ):
        registry_store.init_registry_db()
        p1 = registry_store.preview_register_agent(spec, owner_user_id=None)
        p2 = registry_store.preview_register_agent(spec, owner_user_id=None)
        assert p1["normalized"] == p2["normalized"]
        assert p1["would_register"] is True
        registry_store.register_agent(spec, owner_user_id=None)
        with pytest.raises(registry_store.AgentVersionExists):
            registry_store.register_agent(spec, owner_user_id=None)
