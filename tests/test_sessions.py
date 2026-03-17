"""
Context + Session Memory — Sessions API tests.

Contract (from plan): POST /sessions → 201 + session_id;
POST /sessions/{id}/events → 200 + { ok, session_id, appended };
GET /sessions/{id} → 200 + session_id, agent_id, created_at, events, running_summary;
GET /sessions/{id} → 404 for unknown id.

Tests use a temporary DB via SESSION_DB_PATH. Isolated and deterministic.
"""

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    """FastAPI app from runtime."""
    from app.main import app as fastapi_app  # type: ignore
    return fastapi_app


@pytest.fixture
def session_db_path():
    """Temporary directory and DB path for session store. Deleted after test."""
    with tempfile.TemporaryDirectory(prefix="agent_session_test_") as tmp:
        yield str(Path(tmp) / "sessions.db")


@pytest.fixture
def client_with_session_db(app, session_db_path):
    """TestClient with SESSION_DB_PATH and AGENT_PRESET set for session tests."""
    env = {
        "SESSION_DB_PATH": session_db_path,
        "AUTH_TOKEN": "",
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
    }
    old = {}
    for k, v in env.items():
        old[k] = os.environ.get(k)
        os.environ[k] = v
    try:
        yield TestClient(app)
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# --- T1: POST /sessions → 201, body has session_id ---------------------------------

def test_post_sessions_returns_201_with_session_id(client_with_session_db):
    """
    POST /sessions must return 201 Created and body must include session_id (string).
    """
    resp = client_with_session_db.post("/sessions")
    # If route not yet implemented, we get 404; test encodes desired contract.
    assert resp.status_code == 201, (
        f"POST /sessions expected 201, got {resp.status_code}. "
        "Ensure sessions route is implemented and returns 201 with session_id."
    )
    data = resp.json()
    assert "session_id" in data
    assert isinstance(data["session_id"], str)
    assert len(data["session_id"]) > 0


# --- T2: POST /sessions/{id}/events → 200, body { ok, session_id, appended } -------

def test_post_sessions_id_events_returns_200_with_ok_session_id_appended(client_with_session_db):
    """
    POST /sessions/{id}/events with {"events": [{ "role": "user", "content": "hi" }]}
    must return 200 and body { ok: true, session_id, appended: N }.
    """
    # Create session first.
    create = client_with_session_db.post("/sessions")
    if create.status_code != 201:
        pytest.skip("POST /sessions not implemented; cannot test events")
    session_id = create.json()["session_id"]

    resp = client_with_session_db.post(
        f"/sessions/{session_id}/events",
        json={"events": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert data.get("session_id") == session_id
    assert "appended" in data
    assert isinstance(data["appended"], int)
    assert data["appended"] == 1


# --- T3: GET /sessions/{id} → 200 with session_id, agent_id, created_at, events, running_summary

def test_get_sessions_id_returns_200_with_session_fields(client_with_session_db):
    """
    After creating a session and appending one event, GET /sessions/{id}
    must return 200 with session_id, agent_id, created_at, events, running_summary.
    """
    create = client_with_session_db.post("/sessions")
    if create.status_code != 201:
        pytest.skip("POST /sessions not implemented")
    session_id = create.json()["session_id"]

    client_with_session_db.post(
        f"/sessions/{session_id}/events",
        json={"events": [{"role": "user", "content": "hello"}]},
    )

    resp = client_with_session_db.get(f"/sessions/{session_id}")
    assert resp.status_code == 200
    data = resp.json()
    for key in ("session_id", "agent_id", "created_at", "events", "running_summary"):
        assert key in data, f"GET /sessions/{{id}} must include '{key}'"
    assert data["session_id"] == session_id
    assert isinstance(data["events"], list)
    assert len(data["events"]) >= 1


# --- T4: GET /sessions/{id} → 404 for unknown id ----------------------------------

def test_get_sessions_id_returns_404_for_unknown_id(client_with_session_db):
    """
    GET /sessions/{id} for a non-existent session_id must return 404.
    """
    resp = client_with_session_db.get("/sessions/nonexistent-session-id-12345")
    assert resp.status_code == 404


def test_post_sessions_events_idempotency_key_avoids_duplicates(client_with_session_db):
    """
    Appending with the same idempotency_key twice should not duplicate events.
    """
    create = client_with_session_db.post("/sessions")
    if create.status_code != 201:
        pytest.skip("POST /sessions not implemented")
    session_id = create.json()["session_id"]

    first = client_with_session_db.post(
        f"/sessions/{session_id}/events",
        json={
            "events": [{"role": "user", "content": "once"}],
            "idempotency_key": "evt-1",
        },
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["appended"] == 1
    assert first_body["duplicated"] is False

    second = client_with_session_db.post(
        f"/sessions/{session_id}/events",
        json={
            "events": [{"role": "user", "content": "once"}],
            "idempotency_key": "evt-1",
        },
    )
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["appended"] == 0
    assert second_body["duplicated"] is True

    session = client_with_session_db.get(f"/sessions/{session_id}")
    assert session.status_code == 200
    events = session.json()["events"]
    assert len(events) == 1


def test_event_type_is_inferred_when_null(client_with_session_db):
    """
    Back-compat: event_type null/missing should infer from role.
    """
    create = client_with_session_db.post("/sessions")
    if create.status_code != 201:
        pytest.skip("POST /sessions not implemented")
    session_id = create.json()["session_id"]

    client_with_session_db.post(
        f"/sessions/{session_id}/events",
        json={
            "events": [
                {"role": "assistant", "content": "a1"},
                {"role": "tool", "content": "t1"},
            ]
        },
    )
    session = client_with_session_db.get(f"/sessions/{session_id}")
    assert session.status_code == 200
    events = session.json()["events"]
    assert events[0]["event_type"] == "assistant"
    assert events[1]["event_type"] == "system"
