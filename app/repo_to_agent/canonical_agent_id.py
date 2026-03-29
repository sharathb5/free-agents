"""
Canonical Free-Agents registry id and import version for repo coordinates.

Agent ids must match registry_store: ^[a-z0-9][a-z0-9_-]{1,62}$ (length 2–63).
"""

from __future__ import annotations

import hashlib
import re
from typing import Tuple

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")
_MAX_ID_LEN = 63
_MIN_ID_LEN = 2


def _segment(label: str) -> str:
    t = (label or "").strip().lower().removesuffix(".git")
    t = re.sub(r"[^a-z0-9]+", "_", t)
    t = re.sub(r"_+", "_", t).strip("_")
    return t or "x"


def canonical_agent_id_from_repo(owner: str, repo: str) -> str:
    """
    Derive a stable registry agent id from GitHub-style owner and repo name.

    Normalization: lowercase; non [a-z0-9] runs become a single underscore;
    owner and repo segments are joined with ``_``. Result is truncated to 63
    characters (registry max id length). If the result is still invalid, falls
    back to ``a_<sha256(owner/repo)[:14]>``.
    """
    o = _segment(owner)
    r = _segment(repo)
    slug = f"{o}_{r}"
    slug = re.sub(r"_+", "_", slug).strip("_")
    if len(slug) > _MAX_ID_LEN:
        slug = slug[:_MAX_ID_LEN].rstrip("_")

    def _ensure_valid(s: str) -> str:
        if _ID_RE.match(s):
            return s
        h = hashlib.sha256(f"{owner!s}/{repo!s}".encode("utf-8")).hexdigest()[:14]
        fallback = f"a_{h}"
        if len(fallback) > _MAX_ID_LEN:
            fallback = fallback[:_MAX_ID_LEN]
        return fallback if _ID_RE.match(fallback) else "repo_import"

    slug = _ensure_valid(slug)
    if len(slug) < _MIN_ID_LEN:
        slug = _ensure_valid(f"{slug}_x")
    return slug


def deterministic_import_version(base_version: str, owner: str, repo: str) -> str:
    """
    Version string for a repo import: ``<base_prefix>-<10-char-hex>`` (max 32 chars).

    ``base_prefix`` is the part before the first hyphen in ``base_version``,
    truncated to 6 characters (workflow compatibility). The hex suffix is the
    first 10 nibbles of SHA-256 of ``{owner}/{repo}`` (UTF-8), so the same
    owner/repo always yields the same version for a given base prefix.
    """
    owner_key = str(owner or "").strip() or "unknown_owner"
    repo_key = str(repo or "").strip() or "unknown_repo"
    repo_hash = hashlib.sha256(f"{owner_key}/{repo_key}".encode("utf-8")).hexdigest()[:10]
    base_v = str(base_version or "0.1.0").strip()
    base_prefix = base_v.split("-", 1)[0][:6] if base_v else "0.1.0"
    if not base_prefix:
        base_prefix = "0.1.0"
    new_version = f"{base_prefix}-{repo_hash}"
    if len(new_version) > 32:
        new_version = new_version[:32]
    return new_version


def repo_coordinates_for_tests(owner: str, repo: str) -> Tuple[str, str]:
    """Return (canonical_id, deterministic_version) for assertions and integration tests."""
    v = deterministic_import_version("0.1.0", owner, repo)
    return canonical_agent_id_from_repo(owner, repo), v
