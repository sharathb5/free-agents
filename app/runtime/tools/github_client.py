"""
GitHub read-only client: repo metadata, tree listing, file contents.
Token from optional GITHUB_TOKEN env; never logged or exposed.
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("agent-gateway")

API_BASE = "https://api.github.com"
DEFAULT_TIMEOUT = 15.0
ACCEPT = "application/vnd.github.v3+json"

_DEBUG_LOG_PATH = "/Users/sharath/agent-toolbox/agent-toolbox/.cursor/debug-ced206.log"


def _debug_log(*, hypothesis_id: str, location: str, message: str, data: Dict[str, Any] | None = None, run_id: str = "pre-fix") -> None:
    # #region agent log
    try:
        import json as _json
        import time as _time

        payload: Dict[str, Any] = {
            "sessionId": "ced206",
            "timestamp": int(_time.time() * 1000),
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(_json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion agent log


class GithubClientError(Exception):
    """GitHub API error with a safe user-facing message. No token or sensitive data."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _get_token() -> Optional[str]:
    """Return GitHub token from environment. Never log or expose."""
    import os
    return os.environ.get("GITHUB_TOKEN") or None


def _headers() -> Dict[str, str]:
    h: Dict[str, str] = {"Accept": ACCEPT, "User-Agent": "free-agents/1.0"}
    token = _get_token()
    if token:
        h["Authorization"] = f"token {token}"
    return h


def _check_response(resp: httpx.Response, context: str) -> None:
    """Raise GithubClientError on non-2xx with safe messages."""
    if resp.status_code < 400:
        return
    try:
        body = resp.json()
        msg = body.get("message") if isinstance(body, dict) else None
    except Exception:
        msg = None
    if not isinstance(msg, str):
        msg = resp.text[:200] if resp.text else ""
    _debug_log(
        hypothesis_id="H1",
        location="app/runtime/tools/github_client.py:_check_response",
        message="GitHub API returned error",
        data={"context": context, "status_code": int(resp.status_code), "message_excerpt": (msg or "")[:120]},
    )
    # Safe messages only; never include token or URLs with secrets
    if resp.status_code == 401:
        raise GithubClientError("GitHub authentication required or invalid credentials")
    if resp.status_code == 403 and "rate limit" in (msg or "").lower():
        raise GithubClientError("GitHub rate limit exceeded")
    if resp.status_code == 404:
        if "not found" in (msg or "").lower() or "Not Found" in (msg or ""):
            raise GithubClientError("Repository or resource not found")
        raise GithubClientError("Repository or resource not found")
    if resp.status_code == 409:
        if "empty" in (msg or "").lower():
            raise GithubClientError("Repository is empty (no commits yet). Add files and push to enable inspection.")
        raise GithubClientError(f"Repository conflict (HTTP 409): {msg or 'request failed'}")
    if resp.status_code == 422:
        raise GithubClientError("Invalid path or ref")
    raise GithubClientError(f"{context}: request failed (HTTP {resp.status_code})")


def get_repo(owner: str, repo: str, timeout: float = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """
    Fetch repository metadata. Read-only.
    Returns dict with keys such as default_branch, private, name, full_name.
    """
    url = f"{API_BASE}/repos/{owner}/{repo}"
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url, headers=_headers())
    _check_response(resp, "get_repo")
    data = resp.json()
    if not isinstance(data, dict):
        raise GithubClientError("Invalid repository response")
    return data


def get_default_branch(owner: str, repo: str, timeout: float = DEFAULT_TIMEOUT) -> str:
    """Return the default branch name for the repository."""
    data = get_repo(owner, repo, timeout=timeout)
    branch = data.get("default_branch")
    if not isinstance(branch, str) or not branch.strip():
        raise GithubClientError("Repository has no default branch")
    return branch.strip()


def get_tree(
    owner: str,
    repo: str,
    ref: str,
    path: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> List[Dict[str, Any]]:
    """
    List contents at a path (or repo root). Read-only.
    Returns list of dicts with path, type (file/dir), size (for files).
    """
    if path is None:
        path = ""
    path = path.strip().strip("/")

    if not path:
        # Root: use Git Trees API
        commit_url = f"{API_BASE}/repos/{owner}/{repo}/commits/{ref}"
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(commit_url, headers=_headers())
        _check_response(resp, "get_tree")
        commit_data = resp.json()
        if not isinstance(commit_data, dict):
            raise GithubClientError("Invalid commit response")
        commit_obj = commit_data.get("commit")
        tree_obj = commit_obj.get("tree") if isinstance(commit_obj, dict) else None
        tree_sha = tree_obj.get("sha") if isinstance(tree_obj, dict) else None
        if not isinstance(tree_sha, str):
            raise GithubClientError("Could not resolve tree for ref")
        tree_url = f"{API_BASE}/repos/{owner}/{repo}/git/trees/{tree_sha}"
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(tree_url, headers=_headers())
        _check_response(resp, "get_tree")
        tree_data = resp.json()
        if not isinstance(tree_data, dict):
            raise GithubClientError("Invalid tree response")
        raw_tree = tree_data.get("tree")
        if not isinstance(raw_tree, list):
            return []
        return [
            {
                "path": item.get("path", ""),
                "type": "dir" if (item.get("type") == "tree") else "file",
                "size": item.get("size") if item.get("type") == "blob" else None,
            }
            for item in raw_tree
            if isinstance(item, dict) and item.get("path")
        ]

    # Non-root: use Contents API (directory listing)
    contents_url = f"{API_BASE}/repos/{owner}/{repo}/contents/{path}"
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(contents_url, headers=_headers(), params={"ref": ref})
    _check_response(resp, "get_tree")
    contents = resp.json()
    if isinstance(contents, dict):
        # Single file returned instead of directory
        raise GithubClientError("Path is a file, not a directory")
    if not isinstance(contents, list):
        return []
    return [
        {
            "path": item.get("path", item.get("name", "")),
            "type": "dir" if (item.get("type") == "dir") else "file",
            "size": item.get("size") if isinstance(item.get("size"), int) else None,
        }
        for item in contents
        if isinstance(item, dict)
    ]


def get_file(
    owner: str,
    repo: str,
    path: str,
    ref: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[str, str]:
    """
    Fetch raw file content and encoding. Read-only.
    Returns (content_str, encoding). Decodes base64 from Contents API.
    """
    if not path or not path.strip():
        raise GithubClientError("File path is required")
    path = path.strip().strip("/")
    if not path:
        raise GithubClientError("Invalid file path")
    if ref is None or not ref.strip():
        ref = get_default_branch(owner, repo, timeout=timeout)
    url = f"{API_BASE}/repos/{owner}/{repo}/contents/{path}"
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url, headers=_headers(), params={"ref": ref})
    _check_response(resp, "get_file")
    data = resp.json()
    if not isinstance(data, dict):
        raise GithubClientError("Invalid file response")
    if data.get("type") == "dir":
        raise GithubClientError("Path is a directory, not a file")
    raw = data.get("content")
    if not raw:
        raise GithubClientError("File content not found")
    encoding = "utf-8"
    if isinstance(data.get("encoding"), str) and data["encoding"].lower() == "base64":
        try:
            content = base64.b64decode(raw).decode("utf-8", errors="replace")
        except Exception:
            raise GithubClientError("Could not decode file content")
    else:
        content = raw if isinstance(raw, str) else ""
    return content, encoding


class DefaultGithubClient:
    """Default client that calls module-level functions. Implements GithubClientLike."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        self.timeout = timeout

    def get_repo(self, owner: str, repo: str) -> Dict[str, Any]:
        return get_repo(owner, repo, timeout=self.timeout)

    def get_default_branch(self, owner: str, repo: str) -> str:
        return get_default_branch(owner, repo, timeout=self.timeout)

    def get_tree(
        self,
        owner: str,
        repo: str,
        ref: str,
        path: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return get_tree(owner, repo, ref, path=path, timeout=self.timeout)

    def get_file(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: Optional[str] = None,
    ) -> tuple[str, str]:
        return get_file(owner, repo, path, ref=ref, timeout=self.timeout)
