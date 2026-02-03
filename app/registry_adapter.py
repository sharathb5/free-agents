from __future__ import annotations

from typing import Any, Dict

from .models import MemoryPolicy
from .preset_loader import Preset, _coerce_memory_policy


def spec_to_preset(spec: Dict[str, Any]) -> Preset:
    """
    Convert a registry spec dict into a Preset instance.
    """
    memory_policy = None
    if spec.get("memory_policy") is not None:
        if isinstance(spec.get("memory_policy"), dict):
            memory_policy = _coerce_memory_policy(spec.get("memory_policy"))
        elif isinstance(spec.get("memory_policy"), MemoryPolicy):
            memory_policy = spec.get("memory_policy")

    return Preset(
        id=str(spec["id"]),
        version=str(spec["version"]),
        name=str(spec.get("name", spec["id"])),
        description=str(spec.get("description", "")),
        primitive=str(spec["primitive"]),
        input_schema=spec["input_schema"],
        output_schema=spec["output_schema"],
        prompt=str(spec["prompt"]),
        supports_memory=bool(spec.get("supports_memory", False)),
        memory_policy=memory_policy,
    )
