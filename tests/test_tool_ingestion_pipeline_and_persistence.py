from __future__ import annotations

import json
import os
from pathlib import Path

from app.tool_ingestion.models import ToolCandidate, default_args_schema
from app.tool_ingestion.pipeline import decide_promotion, dedupe_candidates, run_tool_ingestion_for_repo
from app.tool_ingestion.persistence import (
    init_tool_ingestion_db,
    insert_platform_tools,
    insert_tool_candidates,
)


def test_dedupe_prefers_higher_confidence() -> None:
    base = ToolCandidate(
        name="My Tool",
        description="a tool",
        source_repo="owner/repo",
        source_path="file.py",
        tool_type="langchain_tool",
        execution_kind="python_function",
        args_schema=default_args_schema(),
        risk_level="medium",
        tags=[],
        capability_category="code_execution",
        confidence=0.8,
        raw_snippet="",
    )
    low = base.model_copy(update={"confidence": 0.8})
    high = base.model_copy(update={"confidence": 0.95, "description": "better desc"})
    deduped = dedupe_candidates([low, high])
    assert len(deduped) == 1
    assert deduped[0].confidence == 0.95
    assert deduped[0].description == "better desc"


def test_decide_promotion_sets_reasons() -> None:
    strong_schema = default_args_schema()
    strong_schema["properties"] = {"q": {"type": "string"}}
    strong_schema["required"] = ["q"]

    good = ToolCandidate(
        name="search_docs",
        description="search",
        source_repo="owner/repo",
        source_path="tools.py",
        tool_type="langchain_tool",
        execution_kind="python_function",
        args_schema=strong_schema,
        risk_level="medium",
        tags=["search"],
        capability_category="search_retrieval",
        confidence=0.9,
        raw_snippet="",
    )
    bad = good.model_copy(update={"name": "weak", "args_schema": default_args_schema(), "confidence": 0.9})

    decided, promoted = decide_promotion([good, bad])
    assert len(promoted) == 1
    assert promoted[0].name == "search_docs"
    reasons = {c.name: c.promotion_reason for c in decided}
    assert reasons["search_docs"] == "args_schema_strong_promoted"
    assert reasons["weak"] in {"args_schema_weak_not_promoted", "route_schema_insufficient_not_promoted"}


def test_test_path_candidate_not_promoted() -> None:
    cand = ToolCandidate(
        name="test_tool",
        description="test-only tool",
        source_repo="owner/repo",
        source_path="libs/core/tests/unit_tests/test_tools.py",
        tool_type="langchain_tool",
        execution_kind="python_function",
        args_schema=default_args_schema(),
        risk_level="medium",
        tags=[],
        capability_category="code_execution",
        confidence=0.9,
        raw_snippet="",
    )
    decided, promoted = decide_promotion([cand])
    assert len(promoted) == 0
    assert decided[0].promotion_reason == "test_fixture_not_promoted"


def test_junk_name_candidate_not_promoted() -> None:
    cand = ToolCandidate(
        name="foo",
        description="junk name tool",
        source_repo="owner/repo",
        source_path="tools/runtime.py",
        tool_type="langchain_tool",
        execution_kind="python_function",
        args_schema=default_args_schema(),
        risk_level="medium",
        tags=[],
        capability_category="code_execution",
        confidence=0.9,
        raw_snippet="",
    )
    decided, promoted = decide_promotion([cand])
    assert len(promoted) == 0
    assert decided[0].promotion_reason == "junk_name_not_promoted"


def test_real_cli_script_is_promoted() -> None:
    cand = ToolCandidate(
        name="build-ui",
        description="Build UI assets",
        source_repo="owner/repo",
        source_path="script/build-ui",
        tool_type="generic_tool",
        execution_kind="cli_command",
        args_schema=default_args_schema(),
        risk_level="medium",
        tags=[],
        capability_category="code_execution",
        confidence=0.7,
        raw_snippet="",
    )
    decided, promoted = decide_promotion([cand])
    assert len(promoted) == 1
    assert promoted[0].promotion_reason == "cli_tool_promoted"


def test_no_arg_useful_tool_can_be_promoted() -> None:
    schema = default_args_schema()
    cand = ToolCandidate(
        name="check_time",
        description="Check current time",
        source_repo="owner/repo",
        source_path="runtime/time_tools.py",
        tool_type="langchain_tool",
        execution_kind="python_function",
        args_schema=schema,
        risk_level="medium",
        tags=[],
        capability_category="code_execution",
        confidence=0.9,
        raw_snippet="",
    )
    decided, promoted = decide_promotion([cand])
    assert len(promoted) == 1
    assert promoted[0].promotion_reason == "no_arg_tool_promoted"


def test_run_tool_ingestion_for_repo_shapes_summary() -> None:
    repo_files = [
        {
            "path": "tools/simple.py",
            "content": "from langchain.tools import tool\n@tool\ndef hello(name: str):\n    '''Say hi.'''\n    return name\n",
        }
    ]
    summary = run_tool_ingestion_for_repo("owner/repo", repo_files)
    assert "all_candidates" in summary and "deduped" in summary and "promoted" in summary
    assert isinstance(summary["all_candidates"], list)
    assert isinstance(summary["deduped"], list)
    assert isinstance(summary["promoted"], list)
    assert "by_category" in summary
    assert isinstance(summary["by_category"], dict)


def test_persistence_inserts_into_sqlite(tmp_path: Path, monkeypatch) -> None:
    # Use an isolated sqlite file via SUPABASE_DATABASE_URL / DATABASE_URL
    db_path = tmp_path / "test_tools.db"
    os.environ.pop("SUPABASE_DATABASE_URL", None)
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    init_tool_ingestion_db()

    strong_schema = default_args_schema()
    strong_schema["properties"] = {"x": {"type": "integer"}}
    strong_schema["required"] = ["x"]

    cand = ToolCandidate(
        name="compute_x",
        description="compute",
        source_repo="owner/repo",
        source_path="compute.py",
        tool_type="langchain_tool",
        execution_kind="python_function",
        args_schema=strong_schema,
        risk_level="medium",
        tags=["code"],
        capability_category="code_execution",
        confidence=0.9,
        raw_snippet="",
    )

    staged = insert_tool_candidates([cand])
    assert staged == 1
    promoted = insert_platform_tools([cand])
    assert promoted == 1

    # Sanity check: read back raw rows via sqlite3
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM tool_candidates")
    row = cur.fetchone()
    assert row is not None
    assert row["name"] == "compute_x"
    schema = json.loads(row["args_schema_json"])
    assert schema.get("type") == "object"

