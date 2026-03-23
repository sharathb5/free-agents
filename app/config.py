import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel

# Load .env from the repository root (parent of the `app` package) first so uvicorn
# picks up the same file no matter which directory you start from. Then optionally
# load cwd .env if it is a different file (local overrides). override=True so values
# from these files win over pre-set shell variables (e.g. .zshrc).
_repo_root = Path(__file__).resolve().parent.parent
_disable_dotenv = os.getenv("AGENT_TOOLBOX_DISABLE_DOTENV", "").strip().lower() in ("1", "true", "yes")
if not _disable_dotenv:
    _env_candidates = [_repo_root / ".env", Path.cwd() / ".env"]
    _seen: set[Path] = set()
    for _p in _env_candidates:
        _rp = _p.resolve()
        if _rp in _seen:
            continue
        _seen.add(_rp)
        if _p.is_file():
            load_dotenv(dotenv_path=_p, override=True)


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
    clerk_secret_key: Optional[str]
    clerk_api_url: str = "https://api.clerk.com"
    github_client_id: Optional[str]
    github_client_secret: Optional[str]
    github_oauth_redirect_uri: Optional[str]
    # Extra allowed postMessage targets for GitHub OAuth popup (comma-separated origins).
    # Localhost is always allowed. Non-localhost also allowed when listed in CORS_ORIGINS (if not *).
    github_oauth_allowed_return_origins: List[str] = []
    db_path: str = "./data/gateway.db"
    session_db_path: str = "./data/sessions.db"
    cors_origins: str = "*"

    service_name: str = "agent-gateway"
    http_port: int = 4280

    # Runner limits (Agent Runtime Part 1)
    max_steps: int = 10
    max_wall_time_seconds: int = 60

    # Tool policy (Agent Runtime Part 2)
    tools_enabled: bool = True
    max_tool_calls: int = 5
    http_timeout_seconds: int = 15
    http_max_response_chars: int = 50_000
    # Max chars of tool result injected into prompt (avoids blowing context)
    max_tool_prompt_chars: int = 8_000
    # Comma-separated; empty = deny all unless preset overrides. Example: api.open-meteo.com,api.example.com
    http_allowed_domains_default: List[str] = []

    # Memory & summarization (Agent Runtime Part 4)
    memory_recent_k: int = 8
    summary_batch_size: int = 12
    summary_max_chars: int = 1_500


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
        clerk_secret_key=None,
        clerk_api_url="https://api.clerk.com",
        github_client_id=None,
        github_client_secret=None,
        github_oauth_redirect_uri=None,
        github_oauth_allowed_return_origins=[],
        db_path="./data/gateway.db",
        session_db_path="./data/sessions.db",
        cors_origins="*",
        max_steps=10,
        max_wall_time_seconds=60,
        tools_enabled=True,
        max_tool_calls=5,
        http_timeout_seconds=15,
        http_max_response_chars=50_000,
        max_tool_prompt_chars=8_000,
        http_allowed_domains_default=[],
        memory_recent_k=8,
        summary_batch_size=12,
        summary_max_chars=1_500,
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
    _raw_issuer = (os.getenv("CLERK_ISSUER") or "").strip()
    # JWT iss is usually https://xxx.clerk.accounts.dev (no trailing slash).
    clerk_issuer = _raw_issuer.rstrip("/") or None
    clerk_audience = (os.getenv("CLERK_AUDIENCE") or "").strip() or None
    clerk_authorized_parties_raw = os.getenv("CLERK_AUTHORIZED_PARTIES") or ""
    clerk_authorized_parties = [
        part.strip() for part in clerk_authorized_parties_raw.split(",") if part.strip()
    ]
    clerk_secret_key = os.getenv("CLERK_SECRET_KEY") or None
    clerk_api_url = os.getenv("CLERK_API_URL") or base.clerk_api_url
    github_client_id = (os.getenv("GITHUB_CLIENT_ID") or "").strip() or None
    github_client_secret = (os.getenv("GITHUB_CLIENT_SECRET") or "").strip() or None
    # GitHub matches redirect_uri byte-for-byte; trailing slash mismatch breaks OAuth.
    _raw_redirect = (os.getenv("GITHUB_OAUTH_REDIRECT_URI") or "").strip()
    github_oauth_redirect_uri = _raw_redirect.rstrip("/") or None
    _gh_return_raw = os.getenv("GITHUB_OAUTH_ALLOWED_RETURN_ORIGINS", "")
    github_oauth_allowed_return_origins = [
        x.strip() for x in _gh_return_raw.split(",") if x.strip()
    ]
    provider_name = (os.getenv("PROVIDER") or base.provider_name).lower()
    agent_preset = os.getenv("AGENT_PRESET") or base.agent_preset

    db_path = os.getenv("DB_PATH") or os.getenv("SESSION_DB_PATH") or base.db_path
    session_db_path = os.getenv("SESSION_DB_PATH") or db_path
    cors_origins = os.getenv("CORS_ORIGINS") or base.cors_origins
    max_steps = int(os.getenv("AGENT_MAX_STEPS", base.max_steps))
    max_wall_time_seconds = int(os.getenv("AGENT_MAX_WALL_TIME_SECONDS", base.max_wall_time_seconds))
    tools_enabled = os.getenv("AGENT_TOOLS_ENABLED", str(base.tools_enabled)).strip().lower() in ("true", "1", "yes")
    max_tool_calls = int(os.getenv("AGENT_MAX_TOOL_CALLS", base.max_tool_calls))
    http_timeout_seconds = int(os.getenv("AGENT_HTTP_TIMEOUT_SECONDS", base.http_timeout_seconds))
    http_max_response_chars = int(os.getenv("AGENT_HTTP_MAX_RESPONSE_CHARS", base.http_max_response_chars))
    max_tool_prompt_chars = int(os.getenv("AGENT_MAX_TOOL_PROMPT_CHARS", base.max_tool_prompt_chars))
    memory_recent_k = int(os.getenv("AGENT_MEMORY_RECENT_K", base.memory_recent_k))
    summary_batch_size = int(os.getenv("AGENT_SUMMARY_BATCH_SIZE", base.summary_batch_size))
    summary_max_chars = int(os.getenv("AGENT_SUMMARY_MAX_CHARS", base.summary_max_chars))
    http_allowed_raw = os.getenv("AGENT_HTTP_ALLOWED_DOMAINS", "")
    http_allowed_domains_default = [d.strip() for d in http_allowed_raw.split(",") if d.strip()] if http_allowed_raw else base.http_allowed_domains_default

    return Settings(
        agent_preset=agent_preset,
        provider_name=provider_name,
        auth_token=auth_token,
        clerk_jwks_url=clerk_jwks_url,
        clerk_jwt_key=clerk_jwt_key,
        clerk_issuer=clerk_issuer,
        clerk_audience=clerk_audience,
        clerk_authorized_parties=clerk_authorized_parties,
        clerk_secret_key=clerk_secret_key,
        clerk_api_url=clerk_api_url,
        github_client_id=github_client_id,
        github_client_secret=github_client_secret,
        github_oauth_redirect_uri=github_oauth_redirect_uri,
        github_oauth_allowed_return_origins=github_oauth_allowed_return_origins,
        db_path=db_path,
        session_db_path=session_db_path,
        cors_origins=cors_origins,
        service_name=base.service_name,
        http_port=base.http_port,
        max_steps=max_steps,
        max_wall_time_seconds=max_wall_time_seconds,
        tools_enabled=tools_enabled,
        max_tool_calls=max_tool_calls,
        http_timeout_seconds=http_timeout_seconds,
        http_max_response_chars=http_max_response_chars,
        max_tool_prompt_chars=max_tool_prompt_chars,
        http_allowed_domains_default=http_allowed_domains_default,
        memory_recent_k=memory_recent_k,
        summary_batch_size=summary_batch_size,
        summary_max_chars=summary_max_chars,
    )
