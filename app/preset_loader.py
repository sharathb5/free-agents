from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agent-gateway")

import yaml
from jsonschema import Draft7Validator, SchemaError

from .config import get_settings
from .models import MemoryPolicy

# Preset YAML files live in the app.presets package (app/presets/*.yaml).
PRESETS_DIR = Path(__file__).parent / "presets"


def _coerce_memory_policy(raw: Any) -> MemoryPolicy:
    """Coerce YAML memory_policy dict to MemoryPolicy with defaults."""
    if raw is None:
        return MemoryPolicy(mode="last_n", max_messages=10, max_chars=8000)
    if isinstance(raw, dict):
        return MemoryPolicy(
            mode=raw.get("mode", "last_n"),
            max_messages=int(raw.get("max_messages", 10)),
            max_chars=int(raw.get("max_chars", 8000)),
            memory_include_tool_results=bool(raw.get("memory_include_tool_results", False)),
            memory_tool_result_mode=str(raw.get("memory_tool_result_mode", "summary")),
        )
    return MemoryPolicy(mode="last_n", max_messages=10, max_chars=8000)


@dataclass
class Preset:
    id: str
    version: str
    name: str
    description: str
    primitive: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    prompt: str
    supports_memory: bool = False
    memory_policy: Optional[MemoryPolicy] = None
    # Tool overrides (Agent Runtime Part 2): allowed_tools e.g. ["http_request"], http_allowed_domains for http_request
    allowed_tools: Optional[List[str]] = None
    http_allowed_domains: Optional[List[str]] = None
    # Part 5: resolved tool-specific policies and global execution limits
    tool_policies: Optional[Dict[str, Dict[str, Any]]] = None
    resolved_execution_limits: Optional[Dict[str, Any]] = None


class PresetLoadError(RuntimeError):
    """Raised when the active preset cannot be loaded or validated."""


def _read_preset_yaml(preset_id: str) -> Dict[str, Any]:
    preset_path = PRESETS_DIR / f"{preset_id}.yaml"
    if not preset_path.exists():
        raise PresetLoadError(f"Preset file not found: {preset_path}")

    with preset_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise PresetLoadError("Preset YAML must deserialize to a mapping")

    return data


def load_preset(preset_id: str) -> Preset:
    """Load and validate a preset by id."""
    raw = _read_preset_yaml(preset_id)

    try:
        input_schema = raw["input_schema"]
        output_schema = raw["output_schema"]
    except KeyError as exc:  # pragma: no cover - defensive, covered by tests indirectly
        raise PresetLoadError(f"Preset missing required field: {exc.args[0]}") from exc

    # Validate that schemas are valid Draft-07 JSON Schemas.
    try:
        Draft7Validator.check_schema(input_schema)
        Draft7Validator.check_schema(output_schema)
    except SchemaError as exc:
        raise PresetLoadError(f"Invalid JSON schema in preset '{preset_id}': {exc}") from exc

    supports_memory = bool(raw.get("supports_memory", False))
    # Only set memory_policy when present in YAML; else None (for GET /agents/{id} null when omitted).
    memory_policy = _coerce_memory_policy(raw["memory_policy"]) if raw.get("memory_policy") is not None else None
    allowed_tools = raw.get("allowed_tools")
    if allowed_tools is not None and not isinstance(allowed_tools, list):
        allowed_tools = None
    http_allowed_domains = raw.get("http_allowed_domains")
    if http_allowed_domains is not None and not isinstance(http_allowed_domains, list):
        http_allowed_domains = None
    elif http_allowed_domains is not None:
        http_allowed_domains = [str(d).strip() for d in http_allowed_domains if d]

    try:
        return Preset(
            id=str(raw["id"]),
            version=str(raw["version"]),
            name=str(raw.get("name", raw["id"])),
            description=str(raw.get("description", "")),
            primitive=str(raw["primitive"]),
            input_schema=input_schema,
            output_schema=output_schema,
            prompt=str(raw["prompt"]),
            supports_memory=supports_memory,
            memory_policy=memory_policy,
            allowed_tools=allowed_tools,
            http_allowed_domains=http_allowed_domains,
        )
    except KeyError as exc:  # pragma: no cover - defensive
        raise PresetLoadError(f"Preset missing required field: {exc.args[0]}") from exc


def get_active_preset() -> Preset:
    """Resolve the currently active preset based on the environment."""
    settings = get_settings()
    return load_preset(settings.agent_preset)


def list_preset_ids() -> List[str]:
    """Discover preset ids from app/presets/*.yaml (filename stem = id). Returns sorted list."""
    if not PRESETS_DIR.exists():
        return []
    ids = [p.stem for p in PRESETS_DIR.glob("*.yaml") if p.is_file()]
    return sorted(ids)
