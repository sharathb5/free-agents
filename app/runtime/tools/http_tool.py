"""
HTTP tool: safe, allowlisted, budgeted outbound requests.

- Validates args (method, url, headers, query, json, data).
- Requires https unless localhost (when allowed).
- Domain allowlist (exact or suffix match).
- Strips Authorization/Cookie. Applies timeout and response cap.
- Returns redacted/capped result; raises ToolExecutionError on policy/network errors.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from app.utils.redaction import redact_secrets

logger = logging.getLogger("agent-gateway")

VALID_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
USER_AGENT = "free-agents/1.0"
FORBIDDEN_HEADERS = frozenset({"authorization", "cookie"})


class ToolExecutionError(Exception):
    """Raised when tool execution fails (policy, network, timeout). Safe message only."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass
class HttpPolicy:
    timeout_seconds: int
    max_response_chars: int
    allowed_domains: List[str]
    allow_localhost: bool = False


def _validate_args(args: Any) -> Dict[str, Any]:
    """Validate and normalize http_request args. Raises ToolExecutionError if invalid."""
    if not isinstance(args, dict):
        raise ToolExecutionError("http_request args must be an object")
    method = args.get("method", "GET")
    if not isinstance(method, str):
        raise ToolExecutionError("method must be a string")
    method = method.upper().strip()
    if method not in VALID_METHODS:
        raise ToolExecutionError(f"method must be one of {sorted(VALID_METHODS)}")
    url = args.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ToolExecutionError("url is required and must be a non-empty string")
    url = url.strip()
    headers = args.get("headers")
    if headers is not None and not isinstance(headers, dict):
        raise ToolExecutionError("headers must be an object if present")
    query = args.get("query")
    if query is not None and not isinstance(query, dict):
        raise ToolExecutionError("query must be an object if present")
    body_json = args.get("json")
    body_data = args.get("data")
    if body_json is not None and body_data is not None:
        raise ToolExecutionError("cannot set both json and data")
    return {
        "method": method,
        "url": url,
        "headers": dict(headers) if headers else {},
        "query": dict(query) if query else {},
        "json": body_json,
        "data": body_data,
    }


def _url_allowed(url: str, policy: HttpPolicy) -> None:
    """Require https (or localhost if allowed). Require domain in allowlist. Raises ToolExecutionError."""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
    except Exception as e:
        raise ToolExecutionError("invalid url") from e
    scheme = (parsed.scheme or "").lower()
    hostname = (parsed.hostname or "").lower().strip()
    if not hostname:
        raise ToolExecutionError("url must have a hostname")

    if hostname in ("localhost", "127.0.0.1", "::1"):
        if not policy.allow_localhost:
            raise ToolExecutionError("localhost is not allowed")
        return
    if scheme != "https":
        raise ToolExecutionError("url must use https")

    allowed = policy.allowed_domains
    if not allowed:
        raise ToolExecutionError("no domains allowed for http_request")
    for d in allowed:
        d = d.lower().strip()
        if d.startswith("."):
            if hostname == d[1:] or hostname.endswith(d):
                return
        else:
            if hostname == d:
                return
    raise ToolExecutionError(f"domain not allowed: {hostname}")


def _sanitize_headers(headers: Dict[str, Any]) -> Dict[str, str]:
    """Remove forbidden headers; return string-valued dict."""
    out: Dict[str, str] = {}
    for k, v in headers.items():
        if k.lower() in FORBIDDEN_HEADERS:
            continue
        if isinstance(v, str):
            out[str(k)] = v
    out.setdefault("User-Agent", USER_AGENT)
    return out


def execute_http_request(args: Dict[str, Any], policy: HttpPolicy) -> Dict[str, Any]:
    """
    Execute one HTTP request. Validates args, enforces policy, returns redacted/capped result.

    Returns dict with: status_code, headers (redacted), text (capped), truncated (bool).
    On non-2xx still returns this structure; on network/timeout/policy error raises ToolExecutionError.
    """
    normalized = _validate_args(args)
    _url_allowed(normalized["url"], policy)

    method = normalized["method"]
    url = normalized["url"]
    headers = _sanitize_headers(normalized["headers"])
    params = normalized["query"] if normalized["query"] else None
    json_body = normalized["json"]
    data_body = normalized["data"]
    if data_body is not None and not isinstance(data_body, str):
        data_body = str(data_body)

    request_kw: Dict[str, Any] = {"method": method, "url": url, "headers": headers, "params": params}
    if method != "GET":
        if json_body is not None:
            request_kw["json"] = json_body
        elif data_body is not None:
            request_kw["content"] = data_body.encode("utf-8") if isinstance(data_body, str) else data_body

    try:
        with httpx.Client(timeout=policy.timeout_seconds) as client:
            resp = client.request(**request_kw)
    except httpx.TimeoutException as e:
        raise ToolExecutionError("http request timed out") from e
    except httpx.RequestError as e:
        raise ToolExecutionError("http request failed") from e

    # Cap response body
    try:
        text = resp.text
    except Exception:
        text = ""
    truncated = False
    if len(text) > policy.max_response_chars:
        text = text[: policy.max_response_chars] + "...[truncated]"
        truncated = True

    # Build response headers dict (redact later)
    resp_headers: Dict[str, Any] = dict(resp.headers)

    result: Dict[str, Any] = {
        "status_code": resp.status_code,
        "headers": resp_headers,
        "text": text,
        "truncated": truncated,
    }
    return redact_secrets(result)


def normalize_http_result_for_model(
    full_result: Dict[str, Any],
    url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Reduce HTTP tool result for model consumption: status_code, content_type, body, truncated, url.
    Drops large header maps to save tokens and avoid noise.
    """
    headers = full_result.get("headers") or {}
    if isinstance(headers, dict):
        content_type = (
            headers.get("content-type")
            or headers.get("Content-Type")
            or ""
        )
        if not isinstance(content_type, str):
            content_type = str(content_type) if content_type else ""
    else:
        content_type = ""
    out: Dict[str, Any] = {
        "status_code": full_result.get("status_code"),
        "content_type": content_type,
        "body": full_result.get("text", ""),
        "truncated": bool(full_result.get("truncated", False)),
    }
    if url is not None:
        out["url"] = url
    return out
