from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml
from jsonschema import Draft7Validator, SchemaError

from .config import get_settings


# Preset YAML files live in the app.presets package (app/presets/*.yaml).
PRESETS_DIR = Path(__file__).parent / "presets"


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
        )
    except KeyError as exc:  # pragma: no cover - defensive
        raise PresetLoadError(f"Preset missing required field: {exc.args[0]}") from exc


def get_active_preset() -> Preset:
    """Resolve the currently active preset based on the environment."""
    settings = get_settings()
    return load_preset(settings.agent_preset)
