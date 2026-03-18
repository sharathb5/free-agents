from __future__ import annotations

from textwrap import dedent

from app.tool_ingestion.extractors import RepoFiles, extractor_generic, extractor_langchain, extractor_mcp
from app.tool_ingestion.models import CAPABILITY_CATEGORIES


def _paths(cands):
    return sorted({c.source_path for c in cands})


def test_extractor_langchain_decorator_and_tool_call() -> None:
    src = dedent(
        """
        from langchain.tools import tool, StructuredTool

        @tool
        def add(x: int, y: int) -> int:
            '''Add two numbers.'''
            return x + y

        calc = StructuredTool(
            name="calc_tool",
            description="Calculator tool",
        )
        """
    )
    repo_files: RepoFiles = [{"path": "tools/langchain_tools.py", "content": src}]

    out = extractor_langchain(repo_files, source_repo="owner/repo")
    names = {c.name for c in out}
    assert "add" in names
    assert "calc_tool" in names
    add_tool = next(c for c in out if c.name == "add")
    assert add_tool.description.startswith("Add two numbers")
    assert add_tool.args_schema.get("type") == "object"
    assert set(add_tool.args_schema.get("required") or []) == {"x", "y"}
    assert add_tool.capability_category in CAPABILITY_CATEGORIES


def test_extractor_mcp_manifest_tools() -> None:
    manifest = {
        "name": "demo-mcp",
        "tools": [
            {
                "name": "do_search",
                "description": "Search docs",
                "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
            },
            {
                "name": "weak_schema_tool",
                "description": "Loose schema",
            },
        ],
    }
    import json as _json

    repo_files: RepoFiles = [{"path": "mcp.json", "content": _json.dumps(manifest)}]
    out = extractor_mcp(repo_files, source_repo="owner/repo")
    names = {c.name for c in out}
    assert "do_search" in names
    t = next(c for c in out if c.name == "do_search")
    assert t.execution_kind == "mcp_server_tool"
    assert t.tool_type == "mcp_tool"
    assert t.capability_category in CAPABILITY_CATEGORIES


def test_extractor_generic_makefile_and_routes() -> None:
    make_src = dedent(
        """
        .PHONY: all
        all: build

        build:
        \techo building
        """
    )
    api_src = dedent(
        """
        from fastapi import FastAPI
        app = FastAPI()

        @app.get("/items/{item_id}")
        def read_item(item_id: str):
            return {"id": item_id}
        """
    )
    repo_files: RepoFiles = [
        {"path": "Makefile", "content": make_src},
        {"path": "app/api.py", "content": api_src},
    ]
    out = extractor_generic(repo_files, source_repo="owner/repo")
    names = {c.name for c in out}
    assert any(n.startswith("make_") for n in names)
    assert any("get_items" in n or "get_items_item_id" in n or "get_items_items_item_id" in n for n in names)
    for c in out:
        assert c.capability_category in CAPABILITY_CATEGORIES

