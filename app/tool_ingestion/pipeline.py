from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Tuple

from .extractors import RepoFiles, extractor_generic, extractor_langchain, extractor_mcp
from .models import ToolCandidate, normalize_tool_name


def _dedupe_key(c: ToolCandidate) -> Tuple[str, str, str, str]:
    return (
        c.normalized_name or normalize_tool_name(c.name),
        str(c.execution_kind or "").strip(),
        str(c.source_repo or "").strip(),
        str(c.capability_category or "").strip(),
    )


def dedupe_candidates(candidates: List[ToolCandidate]) -> List[ToolCandidate]:
    """
    Dedupe by (normalized_name, execution_kind, source_repo, capability_category).

    Deterministic preference: keep highest-confidence candidate; ties prefer longer description.
    """
    best_by_key: Dict[Tuple[str, str, str, str], ToolCandidate] = {}
    for c in candidates:
        c2 = c.with_computed_fields()
        key = _dedupe_key(c2)
        prev = best_by_key.get(key)
        if prev is None:
            best_by_key[key] = c2
            continue
        if c2.confidence > prev.confidence:
            best_by_key[key] = c2
            continue
        if c2.confidence == prev.confidence:
            if (c2.description or "") and len(c2.description or "") > len(prev.description or ""):
                best_by_key[key] = c2

    # Deterministic order: sort by key
    items = sorted(best_by_key.items(), key=lambda kv: kv[0])
    return [v for _k, v in items]


def _is_strong_schema(schema: Any) -> bool:
    if not isinstance(schema, dict) or not schema:
        return False
    if schema.get("type") != "object":
        return False
    props = schema.get("properties")
    if isinstance(props, dict) and len(props) > 0:
        return True
    addl = schema.get("additionalProperties")
    return addl is True


def _is_test_or_fixture_path(path: str) -> bool:
    """
    Heuristic to detect obvious test/demo/fixture/example code paths.
    Deterministic and purely string-based.
    """
    p = path.lower()
    # Directory-style signals
    bad_substrings = (
        "/tests/",
        "/test/",
        "/unit_tests/",
        "/integration_tests/",
        "/mock/",
        "/mocks/",
        "/fixtures/",
        "/examples/",
        "/example/",
    )
    if any(sub in p for sub in bad_substrings):
        return True

    # File-name patterns
    filename = p.rsplit("/", 1)[-1]
    junk_prefixes = ("test_", "mock_", "dummy_", "fixture_")
    if filename.startswith(junk_prefixes):
        return True
    if filename.endswith("_test.py"):
        return True
    return False


def _is_probably_junk_tool_name(name: str) -> bool:
    """
    Small deterministic blacklist of low-signal tool names.
    """
    n = (name or "").strip().lower()
    junk_exact = {
        "foo",
        "foo2",
        "bar",
        "baz",
        "dummy",
        "test",
        "test_tool",
        "a_test_tool",
        "another_tool",
        "some_tool",
        "tool_a",
        "tool_b",
        "tool_c",
        "my_tool",
        "sample_tool",
        "empty_tool",
        "parameterless",
    }
    if n in junk_exact:
        return True
    junk_prefixes = ("mock_", "dummy_")
    return n.startswith(junk_prefixes)


def _is_likely_real_cli_path(path: str) -> bool:
    """
    Detect CLI/script tools that live in real script locations rather than Makefiles or tests.
    """
    p = path.lower()
    # Positive indicators: look for path segments like script/, scripts/, bin/, cli/
    segments = p.split("/")
    good_dirs = {"script", "scripts", "bin", "cli"}
    if not any(seg in good_dirs for seg in segments[:-1]):  # ignore final filename segment
        return False

    # Negative indicators – avoid Makefiles and obvious test roots
    if p.endswith("makefile") or "/makefile" in p:
        return False
    if _is_test_or_fixture_path(p):
        return False
    return True


def _has_no_args(schema: Any) -> bool:
    """
    Treat tools as "no-arg" if their schema has no properties/required fields.
    """
    if not isinstance(schema, dict):
        return True
    props = schema.get("properties") or {}
    required = schema.get("required") or []
    return not props and not required


def promote_candidates(candidates: List[ToolCandidate]) -> List[ToolCandidate]:
    """
    Promote high-confidence candidates into platform_tools.

    V1 rule:
    - confidence >= 0.8 AND (strong args_schema OR explicit structured MCP source).
    """
    decided, promoted = decide_promotion(candidates)
    _ = decided  # callers needing reasons should use decide_promotion()
    return promoted


def decide_promotion(candidates: List[ToolCandidate]) -> Tuple[List[ToolCandidate], List[ToolCandidate]]:
    """
    Decide promotion deterministically and stamp promotion_reason onto all candidates.

    Returns (decided_candidates, promoted_candidates).
    """
    decided: List[ToolCandidate] = []
    promoted: List[ToolCandidate] = []

    for c in candidates:
        c2 = c.with_computed_fields()

        path = c2.source_path or ""
        # 1) Obvious junk/test/example sources: keep staged, never promote.
        if _is_test_or_fixture_path(path):
            reason = c2.promotion_reason or "test_fixture_not_promoted"
            decided.append(c2.model_copy(update={"promotion_reason": reason}))
            continue

        # 2) Obvious junk names: keep staged, never promote.
        if _is_probably_junk_tool_name(c2.name):
            reason = c2.promotion_reason or "junk_name_not_promoted"
            decided.append(c2.model_copy(update={"promotion_reason": reason}))
            continue

        # 3) CLI/script tools from real script locations (special threshold).
        if (
            c2.execution_kind == "cli_command"
            and c2.confidence >= 0.65
            and _is_likely_real_cli_path(path)
            and not _is_probably_junk_tool_name(c2.name)
        ):
            c2 = c2.model_copy(update={"promotion_reason": c2.promotion_reason or "cli_tool_promoted"})
            decided.append(c2)
            promoted.append(c2)
            continue

        # 4) Low-confidence tools are never promoted (except for CLI handled above).
        if c2.confidence < 0.8:
            c2 = c2.model_copy(update={"promotion_reason": c2.promotion_reason or "low_confidence_not_promoted"})
            decided.append(c2)
            continue

        strong_schema = _is_strong_schema(c2.args_schema)
        explicit_mcp = (
            c2.tool_type == "mcp_tool"
            and c2.execution_kind == "mcp_server_tool"
            and ("explicit_schema" in (c2.tags or []) or c2.confidence >= 0.95)
        )

        # 5) Strong-schema tools.
        if strong_schema:
            c2 = c2.model_copy(update={"promotion_reason": c2.promotion_reason or "args_schema_strong_promoted"})
            decided.append(c2)
            promoted.append(c2)
            continue

        # 6) Explicit MCP tools with structured schema.
        if explicit_mcp:
            c2 = c2.model_copy(update={"promotion_reason": c2.promotion_reason or "explicit_mcp_schema_promoted"})
            decided.append(c2)
            promoted.append(c2)
            continue

        # 7) No-arg useful tools (python_function or cli_command) from non-junk paths.
        if (
            c2.confidence >= 0.85
            and c2.execution_kind in ("python_function", "cli_command")
            and _has_no_args(c2.args_schema)
        ):
            c2 = c2.model_copy(update={"promotion_reason": c2.promotion_reason or "no_arg_tool_promoted"})
            decided.append(c2)
            promoted.append(c2)
            continue

        # 8) Fallback: weak schema not promoted.
        if c2.tool_type == "api_route":
            reason = c2.promotion_reason or "route_schema_insufficient_not_promoted"
        else:
            reason = c2.promotion_reason or "args_schema_weak_not_promoted"
        decided.append(c2.model_copy(update={"promotion_reason": reason}))

    return decided, promoted


def run_tool_ingestion_for_repo(source_repo: str, repo_files: RepoFiles) -> Dict[str, Any]:
    """
    Run all extractors for a single repo; return structured outputs.
    """
    lang = extractor_langchain(repo_files, source_repo)
    mcp = extractor_mcp(repo_files, source_repo)
    generic = extractor_generic(repo_files, source_repo)

    all_candidates = [*lang, *mcp, *generic]
    deduped = dedupe_candidates(all_candidates)
    decided, promoted = decide_promotion(deduped)

    by_category: Dict[str, Dict[str, int]] = defaultdict(lambda: {"extracted": 0, "promoted": 0, "skipped": 0})
    for c in decided:
        by_category[c.capability_category]["extracted"] += 1
    for c in promoted:
        by_category[c.capability_category]["promoted"] += 1
    for cat, counts in by_category.items():
        counts["skipped"] = counts["extracted"] - counts["promoted"]

    return {
        "all_candidates": all_candidates,
        "deduped": decided,
        "promoted": promoted,
        "by_category": dict(by_category),
    }

