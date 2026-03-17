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

    allowed_tools = spec.get("allowed_tools")
    if allowed_tools is not None and not isinstance(allowed_tools, list):
        allowed_tools = None
    http_allowed_domains = spec.get("http_allowed_domains")
    if http_allowed_domains is not None and isinstance(http_allowed_domains, list):
        http_allowed_domains = [str(d).strip() for d in http_allowed_domains if d]
    else:
        http_allowed_domains = None
    tool_policies = spec.get("tool_policies")
    if tool_policies is not None and not isinstance(tool_policies, dict):
        tool_policies = None
    resolved_execution_limits = spec.get("resolved_execution_limits")
    if resolved_execution_limits is not None and not isinstance(resolved_execution_limits, dict):
        resolved_execution_limits = None

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
        allowed_tools=allowed_tools,
        http_allowed_domains=http_allowed_domains,
        tool_policies=tool_policies,
        resolved_execution_limits=resolved_execution_limits,
    )
