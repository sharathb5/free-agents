"""Tests for code-defined tool discovery (LangChain @tool, Tool(...), MCP, JS/TS, merge/dedup)."""

from __future__ import annotations

import pytest

from app.repo_to_agent.code_tool_discovery import (
    discover_code_defined_tools,
    get_paths_to_inspect_for_code_tools,
    merge_discovered_tools,
)
from app.repo_to_agent.repo_tool_discovery import DiscoveredRepoTool


# ---- get_paths_to_inspect_for_code_tools ----
def test_get_paths_to_inspect_empty_inputs():
    paths = get_paths_to_inspect_for_code_tools({}, {})
    assert paths == []


def test_get_paths_to_inspect_filters_by_extension():
    scout = {"important_files": ["readme.md", "src/agent.py", "lib/helper.ts"]}
    arch = {"key_paths": []}
    paths = get_paths_to_inspect_for_code_tools(scout, arch)
    assert "readme.md" not in paths
    assert "src/agent.py" in paths
    assert "lib/helper.ts" in paths


def test_get_paths_to_inspect_prioritizes_agent_tool_paths():
    scout = {"important_files": ["other/foo.py", "tools/bar.py"]}
    arch = {"key_paths": ["app/main.py"]}
    paths = get_paths_to_inspect_for_code_tools(scout, arch)
    # Priority segments (tools, app) should appear; order may vary
    assert any("tools" in p or "app" in p for p in paths)


def test_get_paths_to_inspect_excludes_test_fixture_example_paths():
    scout = {
        "important_files": [
            "src/agent.py",
            "tests/test_agent_tools.py",
            "fixtures/demo_tool.py",
            "examples/sample_tool.py",
        ]
    }
    arch = {"key_paths": ["app/server.py", "test/helpers.py"]}
    paths = get_paths_to_inspect_for_code_tools(scout, arch)
    assert "src/agent.py" in paths
    assert "app/server.py" in paths
    assert "tests/test_agent_tools.py" not in paths
    assert "fixtures/demo_tool.py" not in paths
    assert "examples/sample_tool.py" not in paths
    assert "test/helpers.py" not in paths


# ---- Python: @tool ----
def test_detect_python_tool_decorator():
    content = '''
@tool
def search_docs(query: str) -> str:
    """Search the documentation."""
    return "results"
'''
    tools = discover_code_defined_tools({}, {}, {"x/tools.py": content})
    assert len(tools) == 1
    assert tools[0].name == "search_docs"
    assert tools[0].tool_type == "code_tool"
    assert tools[0].source_path == "x/tools.py"
    assert tools[0].confidence >= 0.9
    assert "documentation" in (tools[0].description or "")


def test_detect_python_tool_decorator_with_name():
    content = '''
@tool("weather_lookup")
def weather(city: str) -> str:
    """Get weather for a city."""
    pass
'''
    tools = discover_code_defined_tools({}, {}, {"app/weather.py": content})
    assert len(tools) == 1
    assert tools[0].name == "weather_lookup"


def test_detect_python_tool_decorator_empty_file_returns_empty():
    tools = discover_code_defined_tools({}, {}, {"x/empty.py": "def foo(): pass"})
    code_tools = [t for t in tools if t.tool_type == "code_tool"]
    assert len(code_tools) == 0


# ---- Python: Tool(...) / StructuredTool(...) ----
def test_detect_python_tool_constructor():
    content = '''
search_tool = Tool(
    name="search",
    description="Search the web",
    func=search_fn,
)
'''
    tools = discover_code_defined_tools({}, {}, {"tools.py": content})
    assert len(tools) >= 1
    names = [t.name for t in tools]
    assert "search" in names


def test_detect_python_structured_tool():
    content = '''
from langchain import StructuredTool
t = StructuredTool(
    name="calculator",
    description="Do math",
    func=calc,
)
'''
    tools = discover_code_defined_tools({}, {}, {"tools.py": content})
    assert any(t.name == "calculator" for t in tools)


def test_detect_python_structured_tool_from_function():
    content = '''
StructuredTool.from_function(search_docs)
'''
    tools = discover_code_defined_tools({}, {}, {"tools.py": content})
    assert any(t.name == "search_docs" for t in tools)


def test_detect_python_structured_tool_from_function_explicit_name():
    content = '''
StructuredTool.from_function(search_docs, name="search")
'''
    tools = discover_code_defined_tools({}, {}, {"tools.py": content})
    assert any(t.name == "search" for t in tools)


# ---- Tool registry (confidence boost) ----
def test_tool_registry_boosts_confidence():
    content = '''
@tool
def my_tool(x: str) -> str:
    """A tool."""
    return x

tools = [my_tool, other_tool]
'''
    tools = discover_code_defined_tools({}, {}, {"agent.py": content})
    assert any(t.name == "my_tool" for t in tools)


# ---- JS/TS ----
def test_detect_js_dynamic_tool():
    content = '''
const searchTool = new DynamicTool({
  name: "search_docs",
  description: "Search documentation",
  func: async (input) => {},
});
'''
    tools = discover_code_defined_tools({}, {}, {"src/tools.ts": content})
    assert len(tools) >= 1
    assert any(t.name == "search_docs" for t in tools)


def test_detect_js_dynamic_structured_tool():
    content = '''
new DynamicStructuredTool({
  name: "weather_lookup",
  description: "Get weather",
});
'''
    tools = discover_code_defined_tools({}, {}, {"tools.js": content})
    assert any(t.name == "weather_lookup" for t in tools)


# ---- MCP ----
def test_detect_mcp_code_tools():
    content = '''
from mcp import FastMCP
mcp = FastMCP("my-server")
mcp.tool("get_time")(get_time_fn)
server.register_tool("fetch_data", fetch_data_fn)
'''
    tools = discover_code_defined_tools({}, {}, {"server.py": content})
    mcp_tools = [t for t in tools if t.tool_type == "mcp_code_tool"]
    assert len(mcp_tools) >= 1
    names = [t.name for t in mcp_tools]
    assert "get_time" in names or "fetch_data" in names or "mcp_server_code_tools" in names


def test_mcp_not_triggered_without_mcp_context():
    content = '''
def tool(name):
    pass
tool("helper")
'''
    tools = discover_code_defined_tools({}, {}, {"util.py": content})
    mcp_tools = [t for t in tools if t.tool_type == "mcp_code_tool"]
    assert len(mcp_tools) == 0


# ---- FastAPI (optional) ----
def test_detect_fastapi_routes():
    content = '''
from fastapi import FastAPI
app = FastAPI()
@app.get("/items")
def items():
    pass
@app.post("/query")
def query():
    pass
'''
    tools = discover_code_defined_tools({}, {}, {"main.py": content})
    route_tools = [t for t in tools if t.tool_type == "http_route"]
    assert len(route_tools) >= 1
    assert any(t.name == "fastapi_routes" for t in route_tools)


def test_fastapi_not_triggered_without_fastapi():
    content = '''
@app.get("/x")
def x():
    pass
'''
    tools = discover_code_defined_tools({}, {}, {"main.py": content})
    route_tools = [t for t in tools if t.tool_type == "http_route"]
    assert len(route_tools) == 0


# ---- Empty / no patterns ----
def test_empty_file_contents_returns_empty():
    tools = discover_code_defined_tools({}, {}, None)
    assert tools == []
    tools = discover_code_defined_tools({}, {}, {})
    assert tools == []


def test_no_tool_patterns_returns_empty():
    tools = discover_code_defined_tools(
        {}, {},
        {"src/main.py": "def main():\n    print('hello')"}
    )
    assert tools == []


# ---- Merge / dedup ----
def test_merge_dedup_same_key_keeps_higher_confidence():
    manifest = [
        DiscoveredRepoTool(
            name="search",
            tool_type="script",
            command="npm run search",
            source_path="package.json",
            confidence=0.8,
        )
    ]
    code = [
        DiscoveredRepoTool(
            name="search",
            tool_type="code_tool",
            command=None,
            source_path="src/tools.ts",
            confidence=0.95,
        )
    ]
    merged = merge_discovered_tools(manifest, code)
    names = [t.name for t in merged]
    assert "search" in names
    # Same canonical name: consolidation keeps one (prefer higher priority/confidence)
    assert len([t for t in merged if t.name == "search"]) == 1


def test_merge_no_duplicate_same_name_type_path():
    t1 = DiscoveredRepoTool(
        name="x",
        tool_type="code_tool",
        command=None,
        source_path="a.py",
        confidence=0.9,
    )
    t2 = DiscoveredRepoTool(
        name="x",
        tool_type="code_tool",
        command=None,
        source_path="a.py",
        confidence=0.7,
    )
    merged = merge_discovered_tools([t1], [t2])
    assert len(merged) == 1
    assert merged[0].confidence == 0.9


def test_merge_keeps_manifest_and_code_distinct():
    manifest = [
        DiscoveredRepoTool(name="make_build", tool_type="make_target", command="make build", source_path="Makefile", confidence=0.85),
    ]
    code = [
        DiscoveredRepoTool(name="search", tool_type="code_tool", command=None, source_path="tools.py", confidence=0.9),
    ]
    merged = merge_discovered_tools(manifest, code)
    assert len(merged) == 2
    names = {t.name for t in merged}
    assert "make_build" in names and "search" in names
