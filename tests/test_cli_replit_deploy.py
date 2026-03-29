"""Tests for Replit deploy helper (git remote parsing, GitHub URL normalization)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.cli_replit_deploy import (
    _discover_github_https_url,
    _normalize_git_remote_to_https,
    _parse_git_remote_v_fetch,
    _replit_import_url,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("git@github.com:org/repo.git", "https://github.com/org/repo"),
        ("git@github.com:org/repo", "https://github.com/org/repo"),
        ("https://github.com/org/repo.git", "https://github.com/org/repo"),
        ("https://github.com/org/repo", "https://github.com/org/repo"),
        ("http://github.com/org/repo", "https://github.com/org/repo"),
        ("ssh://git@github.com/org/repo.git", "https://github.com/org/repo"),
        ("git://github.com/org/repo", "https://github.com/org/repo"),
    ],
)
def test_normalize_git_remote_to_https(raw: str, expected: str) -> None:
    assert _normalize_git_remote_to_https(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "https://gitlab.com/a/b.git",
        "not-a-url",
        "",
    ],
)
def test_normalize_git_remote_rejects_non_github(raw: str) -> None:
    assert _normalize_git_remote_to_https(raw) is None


def test_parse_git_remote_v_fetch() -> None:
    assert _parse_git_remote_v_fetch("origin\thttps://github.com/o/r.git (fetch)") == (
        "origin",
        "https://github.com/o/r.git",
    )
    assert _parse_git_remote_v_fetch("fork  git@github.com:o/r.git (fetch)") == ("fork", "git@github.com:o/r.git")
    assert _parse_git_remote_v_fetch("origin\thttps://github.com/o/r.git (push)") is None


def test_replit_import_url() -> None:
    assert _replit_import_url("https://github.com/myorg/cool-agent") == (
        "https://replit.new/github.com/myorg/cool-agent"
    )


def test_discover_github_https_prefers_origin() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        import subprocess

        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(
            ["git", "remote", "add", "upstream", "https://github.com/up/stream.git"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/me/product.git"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        assert _discover_github_https_url(root) == "https://github.com/me/product"
