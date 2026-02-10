from __future__ import annotations

import json
from importlib import resources
from typing import Any, Dict, Optional

_EXAMPLES_CACHE: Optional[Dict[str, Any]] = None


def _load_examples() -> Dict[str, Any]:
    try:
        path = resources.files("app").joinpath("examples.json")
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return data
    except FileNotFoundError:
        return {}
    except Exception:
        return {}
    return {}


def get_examples() -> Dict[str, Any]:
    global _EXAMPLES_CACHE
    if _EXAMPLES_CACHE is None:
        _EXAMPLES_CACHE = _load_examples()
    return _EXAMPLES_CACHE


def get_example(agent_id: str) -> Optional[Dict[str, Any]]:
    examples = get_examples()
    value = examples.get(agent_id)
    if isinstance(value, dict):
        return value
    return None
