import os
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel

# Load .env from current directory so PROVIDER and API keys are set automatically.
load_dotenv()


class Settings(BaseModel):
    """Runtime configuration loaded from environment variables."""

    agent_preset: str
    provider_name: str
    auth_token: Optional[str]

    service_name: str = "agent-gateway"
    http_port: int = 4280


@lru_cache(maxsize=1)
def _base_settings() -> Settings:
    """
    Base settings lookup.

    NOTE: We intentionally *do not* cache environment values that may change
    between tests – `get_settings` below re-creates Settings each time from
    the current environment. This helper only stores defaults.
    """

    # These are just defaults; `get_settings` will override fields from env.
    return Settings(agent_preset="summarizer", provider_name="stub", auth_token=None)


def get_settings() -> Settings:
    """
    Return Settings built from the *current* environment.

    Tests mutate os.environ at runtime via the `env_vars` helper, so we must
    read directly from the environment on each call instead of caching.
    """

    base = _base_settings()
    auth_token = os.getenv("AUTH_TOKEN") or None
    provider_name = (os.getenv("PROVIDER") or base.provider_name).lower()
    agent_preset = os.getenv("AGENT_PRESET") or base.agent_preset

    return Settings(
        agent_preset=agent_preset,
        provider_name=provider_name,
        auth_token=auth_token,
        service_name=base.service_name,
        http_port=base.http_port,
    )

