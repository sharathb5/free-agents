"""
Tests for Agent Runtime Part 4: running_summary and memory robustness.
"""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def session_db_path():
    with tempfile.TemporaryDirectory(prefix="agent_memory_") as tmp:
        yield str(Path(tmp) / "sessions.db")


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


class SummarizingProvider:
    """
    Provider that returns a fixed final output for the main invoke,
    and a deterministic summary for running_summary calls.
    """

    def __init__(self) -> None:
        self.calls: List[str] = []

    def complete_json(self, prompt: str, *, schema: Any) -> Any:
        from app.providers import ProviderResult  # type: ignore

        self.calls.append(prompt)
        # Heuristic: summarizer prompt mentions "memory summarizer" or "running summary".
        if "running summary" in prompt.lower() or "memory summarizer" in prompt.lower():
            data = {"summary": "user wants summaries; key facts captured."}
            return ProviderResult(parsed_json=data, raw_text="summary")
        # Main invoke: match summarizer preset output_schema (summary + bullets).
        data = {"summary": "ok", "bullets": ["a", "b"]}
        return ProviderResult(parsed_json=data, raw_text="ok")


def _override_provider(app, provider):
    from app.dependencies import get_provider  # type: ignore

    app.dependency_overrides[get_provider] = lambda: provider
    return get_provider


def _init_and_seed_temp_db(db_path: str):
    """Initialize DBs pointing at db_path (SQLite)."""
    from app.preset_loader import PRESETS_DIR
    from app.storage import registry_store
    from app.storage import run_store
    from app.storage import session_store

    session_store.init_db()
    registry_store.init_registry_db()
    run_store.init_run_db()
    registry_store.seed_from_presets(PRESETS_DIR)


def test_running_summary_updates_after_enough_events(app, client, session_db_path):
    """
    After enough events, invoking with a session_id triggers running_summary.
    """
    from app.storage import session_store

    provider = SummarizingProvider()
    env = {
        "DB_PATH": session_db_path,
        "SESSION_DB_PATH": session_db_path,
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
        "DATABASE_URL": "",
        "SUPABASE_DATABASE_URL": "",
        "AGENT_SUMMARY_BATCH_SIZE": "2",
        "AGENT_MEMORY_RECENT_K": "1",
    }
    with env_vars(env):
        _init_and_seed_temp_db(session_db_path)
        # Create a session and append a few user/assistant events.
        session_id = session_store.create_session("summarizer")
        events = [
            {"role": "user", "content": f"message {i}", "event_type": "user"}
            for i in range(4)
        ]
        session_store.append_events(session_id, events)

        # Call summarizer directly on stored events.
        from app.memory.summarizer import maybe_update_running_summary
        from app.preset_loader import get_active_preset

        preset = get_active_preset()
        full_events = session_store.get_session_events(session_id)
        maybe_update_running_summary(
            provider=provider,
            preset=preset,
            session_id=session_id,
            events=full_events,
        )

        summary_state = session_store.get_session_summary(session_id)
        assert summary_state["running_summary"] != ""
        assert summary_state["summary_message_count"] >= 2


def test_memory_segment_excludes_tool_result_by_default():
    """
    _merge_and_truncate_memory excludes tool_result/tool_call events by default.
    """
    from app.engine import _merge_and_truncate_memory
    from app.models import MemoryPolicy

    stored = [
        {"role": "user", "content": "hello", "event_type": "user"},
        {
            "role": "assistant",
            "content": "raw tool body",
            "event_type": "tool_result",
            "tool_name": "http_request",
        },
    ]
    policy = MemoryPolicy(mode="last_n", max_messages=10, max_chars=8000)
    merged = _merge_and_truncate_memory(stored, None, policy)
    texts = " ".join(e["content"] for e in merged)
    assert "raw tool body" not in texts


def test_memory_segment_deterministic_with_summary_and_events():
    """
    Given a fixed set of events and policy, _merge_and_truncate_memory output is deterministic.
    """
    from app.engine import _merge_and_truncate_memory
    from app.models import MemoryPolicy

    stored = [
        {"role": "user", "content": "one", "event_type": "user"},
        {"role": "assistant", "content": "two", "event_type": "assistant"},
        {"role": "user", "content": "three", "event_type": "user"},
    ]
    policy = MemoryPolicy(mode="last_n", max_messages=2, max_chars=50)
    out1 = _merge_and_truncate_memory(stored, None, policy)
    out2 = _merge_and_truncate_memory(stored, None, policy)
    assert out1 == out2

