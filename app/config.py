import os
from functools import lru_cache
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel

# Load .env from current directory so PROVIDER and API keys are set automatically.
load_dotenv()


class Settings(BaseModel):
    """Runtime configuration loaded from environment variables."""

    agent_preset: str
    provider_name: str
    auth_token: Optional[str]
    clerk_jwks_url: Optional[str]
    clerk_jwt_key: Optional[str]
    clerk_issuer: Optional[str]
    clerk_audience: Optional[str]
    clerk_authorized_parties: List[str]
    db_path: str = "./data/gateway.db"
    session_db_path: str = "./data/sessions.db"
    cors_origins: str = "*"

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
    return Settings(
        agent_preset="summarizer",
        provider_name="stub",
        auth_token=None,
        clerk_jwks_url=None,
        clerk_jwt_key=None,
        clerk_issuer=None,
        clerk_audience=None,
        clerk_authorized_parties=[],
        db_path="./data/gateway.db",
        session_db_path="./data/sessions.db",
        cors_origins="*",
    )


def get_settings() -> Settings:
    """
    Return Settings built from the *current* environment.

    Tests mutate os.environ at runtime via the `env_vars` helper, so we must
    read directly from the environment on each call instead of caching.
    """

    base = _base_settings()
    auth_token = os.getenv("AUTH_TOKEN") or None
    clerk_jwks_url = os.getenv("CLERK_JWKS_URL") or None
    clerk_jwt_key = os.getenv("CLERK_JWT_KEY") or None
    clerk_issuer = os.getenv("CLERK_ISSUER") or None
    clerk_audience = os.getenv("CLERK_AUDIENCE") or None
    clerk_authorized_parties_raw = os.getenv("CLERK_AUTHORIZED_PARTIES") or ""
    clerk_authorized_parties = [
        part.strip() for part in clerk_authorized_parties_raw.split(",") if part.strip()
    ]
    provider_name = (os.getenv("PROVIDER") or base.provider_name).lower()
    agent_preset = os.getenv("AGENT_PRESET") or base.agent_preset

    db_path = os.getenv("DB_PATH") or os.getenv("SESSION_DB_PATH") or base.db_path
    session_db_path = os.getenv("SESSION_DB_PATH") or db_path
    cors_origins = os.getenv("CORS_ORIGINS") or base.cors_origins

    return Settings(
        agent_preset=agent_preset,
        provider_name=provider_name,
        auth_token=auth_token,
        clerk_jwks_url=clerk_jwks_url,
        clerk_jwt_key=clerk_jwt_key,
        clerk_issuer=clerk_issuer,
        clerk_audience=clerk_audience,
        clerk_authorized_parties=clerk_authorized_parties,
        db_path=db_path,
        session_db_path=session_db_path,
        cors_origins=cors_origins,
        service_name=base.service_name,
        http_port=base.http_port,
    )
