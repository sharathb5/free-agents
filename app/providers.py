from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

from .config import get_settings
from .preset_loader import Preset


@dataclass
class ProviderResult:
    """Normalized result from a provider."""

    parsed_json: Dict[str, Any]
    raw_text: str


class BaseProvider:
    """
    Abstract provider interface.

    For simplicity and testability we make `complete_json` synchronous; FastAPI
    will execute it in a thread pool when called from async routes if needed.
    """

    def complete_json(self, prompt: str, *, schema: Mapping[str, Any]) -> ProviderResult:  # pragma: no cover - interface only
        raise NotImplementedError


class StubProvider(BaseProvider):
    """
    Deterministic provider that fabricates JSON conforming to the given schema.

    The implementation is intentionally simple but schema-aware enough for the
    canonical preset schemas used in tests.
    """

    def complete_json(self, prompt: str, *, schema: Mapping[str, Any]) -> ProviderResult:
        parsed = _generate_from_schema(schema)
        return ProviderResult(parsed_json=parsed, raw_text=json.dumps(parsed))


def _generate_from_schema(schema: Mapping[str, Any]) -> Any:
    """Very small deterministic JSON generator for Draft-07-style schemas."""
    schema_type = schema.get("type")

    if schema_type == "object":
        props = schema.get("properties", {}) or {}
        result: Dict[str, Any] = {}
        for name, sub in props.items():
            result[name] = _generate_from_schema(sub)
        # Fill required keys if they are not part of properties.
        for name in schema.get("required", []) or []:
            if name not in result:
                result[name] = None
        return result

    if schema_type == "array":
        items_schema = schema.get("items", {}) or {}
        # Always emit a single element to keep payloads small but non-empty.
        return [_generate_from_schema(items_schema)]

    if schema_type == "string":
        # Small heuristics for nicer stub data.
        title = (schema.get("title") or "").lower()
        fmt = schema.get("format")

        if "summary" in title:
            return "stub summary"
        if "bullet" in title:
            return "stub bullet"
        if fmt == "date":
            return "2099-01-01"
        return "stub"

    if schema_type == "number":
        # Try to return a value in [0, 1] when that is the intended range.
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum == 0 and maximum == 1:
            return 0.5
        return 1.0

    if schema_type == "integer":
        return 1

    if schema_type == "boolean":
        return False

    # Fallback for schemas without explicit type: generate an object.
    if "properties" in schema:
        return _generate_from_schema({"type": "object", **schema})

    return None


class OpenAIProvider(BaseProvider):
    """
    Placeholder OpenAI provider.

    The test-suite only exercises the stub provider; OpenAI integration is
    included to satisfy the contract but intentionally lightweight.
    """

    def __init__(self, api_key: str, model: Optional[str] = None) -> None:
        self.api_key = api_key
        # Default model chosen conservatively; callers may override via env
        self.model = model or "gpt-4o-mini"

    def complete_json(self, prompt: str, *, schema: Mapping[str, Any]) -> ProviderResult:  # pragma: no cover - network
        import httpx

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a JSON-only API. Respond with strictly valid JSON that matches the provided JSON Schema.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "response_format": {"type": "json_schema", "json_schema": {"name": "agent_output", "schema": schema}},
        }

        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        raw_text = data["choices"][0]["message"]["content"]

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            parsed = {}

        return ProviderResult(parsed_json=parsed, raw_text=raw_text)


OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterProvider(BaseProvider):
    """
    OpenRouter provider: one API key, many models (OpenAI, Claude, Gemini, etc.).
    """

    def __init__(self, api_key: str, model: Optional[str] = None) -> None:
        self.api_key = api_key
        self.model = model or "openai/gpt-4o-mini"

    def complete_json(self, prompt: str, *, schema: Mapping[str, Any]) -> ProviderResult:  # pragma: no cover - network
        import httpx

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a JSON-only API. Respond with strictly valid JSON that matches the provided JSON Schema.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "response_format": {"type": "json_schema", "json_schema": {"name": "agent_output", "schema": schema}},
        }

        resp = httpx.post(
            OPENROUTER_API_URL,
            headers=headers,
            json=body,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        raw_text = data["choices"][0]["message"]["content"]

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            parsed = {}

        return ProviderResult(parsed_json=parsed, raw_text=raw_text)


def build_provider() -> BaseProvider:
    """Factory that chooses the concrete provider implementation."""
    settings = get_settings()
    if settings.provider_name == "openrouter":
        api_key = _get_env("OPENROUTER_API_KEY")
        if not api_key:
            return StubProvider()
        model = _get_env("OPENROUTER_MODEL") or "openai/gpt-4o-mini"
        return OpenRouterProvider(api_key=api_key, model=model)
    if settings.provider_name == "openai":
        api_key = _get_env("OPENAI_API_KEY")
        if not api_key:
            return StubProvider()
        return OpenAIProvider(api_key=api_key)

    return StubProvider()


def _get_env(name: str) -> Optional[str]:
    import os

    return os.getenv(name) or None

