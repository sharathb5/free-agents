from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REDACTED = "[REDACTED]"
_SENSITIVE_KEY_PATTERN = re.compile(r"(token|secret|password|api[_-]?key|authorization|cookie)", re.IGNORECASE)
_URL_SECRET_PARAMS = {"token", "api_key"}


def cap_text(s: str, max_chars: int) -> str:
    """Cap text to max_chars with a truncation suffix."""
    if max_chars <= 0:
        return ""
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "...[truncated]"


def _redact_url_query(value: str) -> str:
    """Redact token-like query params in URLs while preserving other params."""
    try:
        split = urlsplit(value)
    except Exception:
        return value
    if not split.scheme or not split.netloc:
        return value

    if not split.query:
        return value

    params = parse_qsl(split.query, keep_blank_values=True)
    changed = False
    redacted_params = []
    for key, val in params:
        if key.lower() in _URL_SECRET_PARAMS:
            redacted_params.append((key, REDACTED))
            changed = True
        else:
            redacted_params.append((key, val))
    if not changed:
        return value

    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(redacted_params), split.fragment))


def redact_secrets(obj: Any) -> Any:
    """Recursively redact secrets from dict/list/string values."""
    if isinstance(obj, dict):
        out: dict[Any, Any] = {}
        for key, value in obj.items():
            key_str = str(key)
            key_lower = key_str.lower()
            if _SENSITIVE_KEY_PATTERN.search(key_str):
                out[key] = REDACTED
                continue

            # Header maps are frequently nested and should always redact these names.
            if key_lower == "headers" and isinstance(value, dict):
                headers_out: dict[Any, Any] = {}
                for header_key, header_value in value.items():
                    if str(header_key).lower() in {"authorization", "cookie"}:
                        headers_out[header_key] = REDACTED
                    else:
                        headers_out[header_key] = redact_secrets(header_value)
                out[key] = headers_out
                continue

            out[key] = redact_secrets(value)
        return out

    if isinstance(obj, list):
        return [redact_secrets(item) for item in obj]

    if isinstance(obj, str):
        return _redact_url_query(obj)

    return obj
