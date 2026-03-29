"""Unit tests for canonical_agent_id_from_repo and deterministic_import_version."""

from __future__ import annotations

import hashlib
import re

import pytest

from app.repo_to_agent.canonical_agent_id import (
    canonical_agent_id_from_repo,
    deterministic_import_version,
)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")


def test_canonical_id_uppercase_and_dots_normalized() -> None:
    cid = canonical_agent_id_from_repo("MyOrg", "Some.Repo.Name")
    assert cid == "myorg_some_repo_name"
    assert _ID_RE.match(cid)


def test_canonical_id_git_suffix_stripped() -> None:
    assert canonical_agent_id_from_repo("acme", "widget.git") == "acme_widget"


def test_canonical_id_long_owner_repo_truncated_to_63() -> None:
    o = "a" * 40
    r = "b" * 40
    cid = canonical_agent_id_from_repo(o, r)
    assert len(cid) <= 63
    assert _ID_RE.match(cid)


def test_canonical_id_hyphens_become_underscores() -> None:
    assert (
        canonical_agent_id_from_repo("langchain-ai", "open-agent-platform")
        == "langchain_ai_open_agent_platform"
    )


def test_deterministic_version_stable_for_same_repo() -> None:
    v1 = deterministic_import_version("0.1.0", "langchain-ai", "open-agent-platform")
    v2 = deterministic_import_version("0.1.0", "langchain-ai", "open-agent-platform")
    assert v1 == v2
    h = hashlib.sha256(b"langchain-ai/open-agent-platform").hexdigest()[:10]
    assert v1 == f"0.1.0-{h}"
    assert len(v1) <= 32


def test_deterministic_version_different_repos_differ() -> None:
    a = deterministic_import_version("0.1.0", "o", "r1")
    b = deterministic_import_version("0.1.0", "o", "r2")
    assert a != b


@pytest.mark.parametrize(
    "owner,repo",
    [
        ("x", "y"),
        ("", ""),
        ("123", "456"),
    ],
)
def test_canonical_id_always_matches_registry_pattern(owner: str, repo: str) -> None:
    cid = canonical_agent_id_from_repo(owner, repo)
    assert _ID_RE.match(cid), cid
