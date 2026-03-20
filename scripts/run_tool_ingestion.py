#!/usr/bin/env python3
"""
Run deterministic tool ingestion on one or more repos.

For each repo:
  - fetch files via local path or git clone
  - run extractor_langchain, extractor_mcp, extractor_generic
  - dedupe candidates and decide promotion
  - insert staging rows into tool_candidates
  - insert promoted rows into platform_tools
  - print per-repo and aggregate summary (including capability categories)

No LLM usage. No execution of repo code.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

from app.tool_ingestion.persistence import insert_platform_tools, insert_tool_candidates
from app.tool_ingestion.pipeline import run_tool_ingestion_for_repo

RepoFiles = List[Dict[str, str]]


SKIP_DIR_PREFIXES = (
    ".git",
    "node_modules",
    "dist",
    "build",
    ".next",
    "out",
    "target",
    "vendor",
    "third_party",
)

MAX_FILE_BYTES = 500_000


def _is_binary_chunk(data: bytes) -> bool:
    # Simple deterministic heuristic: null byte or very low ratio of printable chars.
    if b"\x00" in data:
        return True
    if not data:
        return False
    text_chars = sum(1 for b in data if 32 <= b <= 126 or b in (9, 10, 13))
    return (text_chars / len(data)) < 0.75


def _should_skip_dir(name: str) -> bool:
    lower = name.lower()
    return any(lower == p or lower.startswith(p + "/") for p in SKIP_DIR_PREFIXES)


def _collect_repo_files(root: Path) -> RepoFiles:
    repo_files: RepoFiles = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        # prune directories in-place
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]

        for fname in filenames:
            rel_path = rel_dir / fname if str(rel_dir) != "." else Path(fname)
            # skip obviously large artifacts
            full_path = Path(dirpath) / fname
            try:
                size = full_path.stat().st_size
            except OSError:
                continue
            if size > MAX_FILE_BYTES:
                continue
            try:
                with full_path.open("rb") as f:
                    chunk = f.read(4096)
                    if _is_binary_chunk(chunk):
                        continue
                    rest = f.read()
                    data = chunk + rest
                text = data.decode("utf-8", errors="ignore")
            except Exception:
                continue
            repo_files.append({"path": str(rel_path).replace("\\", "/"), "content": text})
    return repo_files


def _fetch_local_repo(path: str) -> Tuple[str, RepoFiles]:
    root = Path(path).resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Local path does not exist or is not a directory: {path}")
    source_repo = str(root)
    return source_repo, _collect_repo_files(root)


def _clone_github_repo(owner_repo: str) -> Tuple[str, RepoFiles]:
    """
    Clone https://github.com/{owner_repo}.git shallowly into a temp dir and collect files.
    """
    owner_repo = owner_repo.strip().rstrip("/")
    if "/" not in owner_repo:
        raise SystemExit(f"--repo must be of form owner/repo, got: {owner_repo}")
    url = f"https://github.com/{owner_repo}.git"
    tmpdir = tempfile.mkdtemp(prefix="tool_ingestion_")
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", url, tmpdir],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        source_repo = owner_repo
        repo_files = _collect_repo_files(Path(tmpdir))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return source_repo, repo_files


def _parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run tool ingestion on one or more repos.")
    parser.add_argument(
        "--repo",
        action="append",
        default=[],
        help="GitHub repo in owner/repo form (can be repeated).",
    )
    parser.add_argument(
        "--local-path",
        action="append",
        default=[],
        help="Local checkout path (can be repeated).",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    ns = _parse_args(argv or sys.argv[1:])
    targets: List[Tuple[str, str]] = []

    for r in ns.repo:
        targets.append(("github", r))
    for p in ns.local_path:
        targets.append(("local", p))

    if not targets:
        print("No repos specified. Use --repo owner/repo and/or --local-path /path/to/checkout.")
        return 1

    total_extracted = 0
    total_promoted = 0
    total_deduped = 0

    for kind, value in targets:
        if kind == "github":
            source_repo, repo_files = _clone_github_repo(value)
        else:
            source_repo, repo_files = _fetch_local_repo(value)

        print(f"\n=== Ingesting repo: {source_repo} (files: {len(repo_files)}) ===")
        summary = run_tool_ingestion_for_repo(source_repo, repo_files)

        all_candidates = summary["all_candidates"]
        deduped = summary["deduped"]
        promoted = summary["promoted"]
        by_category = summary.get("by_category", {})

        inserted_candidates = insert_tool_candidates(deduped)
        inserted_promoted = insert_platform_tools(promoted)

        print(f"Extracted candidates: {len(all_candidates)}")
        print(f"Deduped candidates:   {len(deduped)}")
        print(f"Staged (inserted):    {inserted_candidates}")
        print(f"Promoted (inserted):  {inserted_promoted}")
        print("By capability_category:")
        for cat, counts in sorted(by_category.items()):
            print(
                f"  {cat}: extracted={counts.get('extracted', 0)} "
                f"promoted={counts.get('promoted', 0)} skipped={counts.get('skipped', 0)}"
            )

        total_extracted += len(all_candidates)
        total_deduped += len(deduped)
        total_promoted += len(promoted)

    print("\n=== Summary ===")
    print(f"Total extracted: {total_extracted}")
    print(f"Total deduped:   {total_deduped}")
    print(f"Total promoted:  {total_promoted}")
    print(f"Total skipped:   {total_deduped - total_promoted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

