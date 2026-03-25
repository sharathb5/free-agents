"""
GitHub repo read tool: read-only inspection with overview, tree, file, sample modes.
Uses GithubClientLike for API access; policy enforces caps and optional allowlists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

from app.utils.redaction import cap_text, redact_secrets

from .http_tool import ToolExecutionError

# Deterministic order for important-file detection (top-level and common paths).
IMPORTANT_FILE_CANDIDATES = [
    "README.md",
    "AGENTS.md",
    "CONCEPTS.md",
    "CONTRIBUTING.md",
    "agent.json",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "setup.py",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "openapi.json",
    "openapi.yaml",
    "openapi.yml",
    "src/main.py",
    "main.py",
    "app.py",
    "server.py",
    "index.js",
    "src/index.ts",
    "src/index.tsx",
    "prompts/system_prompt.md",
]

VALID_MODES = frozenset({"overview", "tree", "file", "sample"})


class GithubClientLike(Protocol):
    """Protocol for GitHub read-only client (real or mock)."""

    def get_repo(self, owner: str, repo: str) -> Dict[str, Any]:
        ...

    def get_default_branch(self, owner: str, repo: str) -> str:
        ...

    def get_tree(
        self,
        owner: str,
        repo: str,
        ref: str,
        path: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        ...

    def get_file(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: Optional[str] = None,
    ) -> tuple[str, str]:
        ...


@dataclass
class GithubRepoReadPolicy:
    """Policy for github_repo_read: caps and optional allowlists."""

    max_entries: int = 50
    max_file_chars: int = 12_000
    max_sample_files: int = 5
    allow_private_repos: bool = True
    allowed_owners: Optional[List[str]] = None
    allowed_repos: Optional[List[str]] = None
    include_hidden_files: bool = False


def _detect_important_files(
    entries: List[Dict[str, Any]],
    prefix: str = "",
    include_hidden: bool = False,
) -> List[str]:
    """Return paths that match IMPORTANT_FILE_CANDIDATES, in deterministic order."""
    found: List[str] = []
    # Compare case-insensitively so repos with readme.md/ReadMe.md still surface
    # core files in scout outputs and downstream validation.
    for cand in IMPORTANT_FILE_CANDIDATES:
        cand_lower = cand.lower()
        for e in entries:
            p = (e.get("path") or e.get("name") or "").strip()
            if not p:
                continue
            if not include_hidden and p.split("/")[-1].startswith("."):
                continue
            p_lower = p.lower()
            if p_lower == cand_lower or p_lower.endswith("/" + cand_lower):
                found.append(p)
                break
    # Keep deterministic ordering by candidate list; no extra sorting.
    return found


def _derive_hints(
    important_files: List[str],
    all_paths: List[str],
) -> Dict[str, List[str]]:
    """Derive language/framework hints from file names only. Deterministic."""
    languages: List[str] = []
    frameworks: List[str] = []
    paths_set = set(all_paths)
    path_names = [p.split("/")[-1].lower() for p in all_paths]

    if any(
        f in path_names or any(p.endswith(f) for p in paths_set)
        for f in ("pyproject.toml", "requirements.txt", "setup.py")
    ):
        if any("main.py" in p or "app.py" in p for p in paths_set) or any(
            p.endswith("main.py") or p.endswith("app.py") for p in paths_set
        ):
            languages.append("Python")
    if "package.json" in path_names or any(p.endswith("package.json") for p in paths_set):
        languages.append("JavaScript")
        if any("next.config" in p for p in paths_set):
            frameworks.append("Next.js")
        if any("vue.config" in p or "vite.config" in p for p in paths_set):
            frameworks.append("Vue")
    if any(
        p.endswith("openapi.json") or p.endswith("openapi.yaml") or p.endswith("openapi.yml")
        for p in paths_set
    ):
        frameworks.append("API service")
    if any(p.endswith("Dockerfile") for p in paths_set):
        frameworks.append("Docker")

    return {"languages": sorted(languages), "frameworks": sorted(frameworks)}


def _repo_payload(repo_data: Dict[str, Any]) -> Dict[str, Any]:
    """Build safe repo summary for output (no token/sensitive)."""
    owner_obj = repo_data.get("owner")
    owner_login = owner_obj.get("login") if isinstance(owner_obj, dict) else None
    return {
        "owner": owner_login,
        "name": repo_data.get("name"),
        "default_branch": repo_data.get("default_branch"),
        "private": bool(repo_data.get("private", False)),
    }


def _validate_args(args: Any) -> Dict[str, Any]:
    """Validate and normalize tool args. Raises ToolExecutionError if invalid."""
    if not isinstance(args, dict):
        raise ToolExecutionError("github_repo_read args must be an object")
    owner = args.get("owner")
    if not isinstance(owner, str) or not owner.strip():
        raise ToolExecutionError("owner is required and must be a non-empty string")
    repo = args.get("repo")
    if not isinstance(repo, str) or not repo.strip():
        raise ToolExecutionError("repo is required and must be a non-empty string")
    mode = args.get("mode")
    if not isinstance(mode, str) or mode.strip().lower() not in VALID_MODES:
        raise ToolExecutionError(
            f"mode is required and must be one of: {sorted(VALID_MODES)}"
        )
    mode = mode.strip().lower()
    path = args.get("path")
    if path is not None and not isinstance(path, str):
        raise ToolExecutionError("path must be a string when provided")
    path = (path or "").strip().strip("/") if path is not None else ""
    if mode == "file" and not path:
        raise ToolExecutionError("path is required for mode=file")
    max_entries = args.get("max_entries")
    if max_entries is not None:
        try:
            max_entries = int(max_entries)
        except (TypeError, ValueError):
            raise ToolExecutionError("max_entries must be an integer")
    max_file_chars = args.get("max_file_chars")
    if max_file_chars is not None:
        try:
            max_file_chars = int(max_file_chars)
        except (TypeError, ValueError):
            raise ToolExecutionError("max_file_chars must be an integer")
    ref = args.get("ref")
    if ref is not None and not isinstance(ref, str):
        raise ToolExecutionError("ref must be a string when provided")
    ref = (ref or "").strip() if ref else None
    return {
        "owner": owner.strip(),
        "repo": repo.strip(),
        "mode": mode,
        "path": path,
        "ref": ref,
        "max_entries": max_entries,
        "max_file_chars": max_file_chars,
    }


def execute_github_repo_read(
    args: Dict[str, Any],
    policy: GithubRepoReadPolicy,
    client: GithubClientLike,
) -> Dict[str, Any]:
    """
    Execute github_repo_read: validate args, enforce policy, call client, return structured JSON.
    Raises ToolExecutionError on validation or client errors (safe messages only).
    """
    from app.runtime.tools.github_client import GithubClientError

    norm = _validate_args(args)
    owner = norm["owner"]
    repo = norm["repo"]
    mode = norm["mode"]
    path = norm["path"]
    ref = norm["ref"]
    max_entries = norm["max_entries"]
    max_file_chars = norm["max_file_chars"]

    if policy.allowed_owners is not None and owner not in policy.allowed_owners:
        raise ToolExecutionError("owner not allowed")
    repo_key = f"{owner}/{repo}"
    if policy.allowed_repos is not None and repo_key not in policy.allowed_repos:
        raise ToolExecutionError("repo not allowed")

    effective_max_entries = policy.max_entries
    if max_entries is not None and max_entries >= 0:
        effective_max_entries = min(max_entries, policy.max_entries)
    effective_max_file_chars = policy.max_file_chars
    if max_file_chars is not None and max_file_chars >= 0:
        effective_max_file_chars = min(max_file_chars, policy.max_file_chars)

    try:
        repo_data = client.get_repo(owner, repo)
    except GithubClientError as e:
        raise ToolExecutionError(e.message) from e

    repo_out = _repo_payload(repo_data)
    default_ref = ref or client.get_default_branch(owner, repo)

    if mode == "overview":
        try:
            tree = client.get_tree(owner, repo, default_ref, path=None)
        except GithubClientError as e:
            raise ToolExecutionError(e.message) from e
        if not policy.include_hidden_files:
            tree = [e for e in tree if not (e.get("path") or "").split("/")[-1].startswith(".")]
        top_level = tree[:effective_max_entries]
        important = _detect_important_files(tree, include_hidden=policy.include_hidden_files)
        all_paths = [e.get("path", "") for e in tree if e.get("path")]
        hints = _derive_hints(important, all_paths)
        result = {
            "mode": "overview",
            "repo": repo_out,
            "top_level": [{"path": e.get("path", ""), "type": e.get("type", "file")} for e in top_level],
            "important_files": important,
            "hints": hints,
            "truncated": len(tree) > effective_max_entries,
        }
        return redact_secrets(result)

    if mode == "tree":
        try:
            tree = client.get_tree(owner, repo, default_ref, path=path or None)
        except GithubClientError as e:
            raise ToolExecutionError(e.message) from e
        if not policy.include_hidden_files:
            tree = [e for e in tree if not (e.get("path") or "").split("/")[-1].startswith(".")]
        entries = tree[:effective_max_entries]
        result = {
            "mode": "tree",
            "repo": repo_out,
            "path": path or "/",
            "entries": [
                {"path": e.get("path", ""), "type": e.get("type", "file"), "size": e.get("size")}
                for e in entries
            ],
            "truncated": len(tree) > effective_max_entries,
        }
        return redact_secrets(result)

    if mode == "file":
        try:
            content, encoding = client.get_file(owner, repo, path, ref=default_ref)
        except GithubClientError as e:
            raise ToolExecutionError(e.message) from e
        truncated = len(content) > effective_max_file_chars
        content = cap_text(content, effective_max_file_chars)
        result = {
            "mode": "file",
            "repo": repo_out,
            "path": path,
            "content": content,
            "truncated": truncated,
            "encoding": encoding,
        }
        return redact_secrets(result)

    if mode == "sample":
        try:
            tree = client.get_tree(owner, repo, default_ref, path=None)
        except GithubClientError as e:
            raise ToolExecutionError(e.message) from e
        important = _detect_important_files(tree, include_hidden=policy.include_hidden_files)
        sample_paths = important[: policy.max_sample_files]
        files_out: List[Dict[str, Any]] = []
        for p in sample_paths:
            try:
                content, _ = client.get_file(owner, repo, p, ref=default_ref)
            except GithubClientError:
                continue
            truncated = len(content) > effective_max_file_chars
            content = cap_text(content, effective_max_file_chars)
            files_out.append({"path": p, "content": content, "truncated": truncated})
        all_paths = [e.get("path", "") for e in tree if e.get("path")]
        hints = _derive_hints(important, all_paths)
        result = {
            "mode": "sample",
            "repo": repo_out,
            "files": files_out,
            "important_files": important,
            "hints": hints,
        }
        return redact_secrets(result)

    raise ToolExecutionError(f"Unsupported mode: {mode}")
