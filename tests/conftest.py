from __future__ import annotations

import os

import pytest

# Ensure tests are hermetic as early as possible (at import time), before any
# application modules read env vars and attempt Postgres connections.
os.environ["AGENT_TOOLBOX_DISABLE_DOTENV"] = "1"
os.environ.pop("DATABASE_URL", None)
os.environ.pop("SUPABASE_DATABASE_URL", None)


@pytest.fixture(autouse=True)
def _force_local_sqlite_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Double-ensure tests never attempt external Postgres."""
    monkeypatch.setenv("AGENT_TOOLBOX_DISABLE_DOTENV", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_DATABASE_URL", raising=False)

