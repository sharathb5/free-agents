"""Tests for repository tool discovery (tools that exist in the repo)."""

from __future__ import annotations

import pytest

from app.repo_to_agent.repo_tool_discovery import (
    discover_tools_from_repo,
    get_paths_to_inspect_for_tools,
    DiscoveredRepoTool,
)


def test_detect_package_json_scripts() -> None:
    """Repo containing package.json with scripts -> expect npm scripts detected."""
    scout = {"repo_summary": "JS project", "important_files": ["package.json"], "language_hints": ["JavaScript"], "framework_hints": []}
    arch = {"languages": ["JavaScript"], "frameworks": [], "services": [], "entrypoints": [], "integrations": [], "key_paths": []}
    file_contents = {
        "package.json": """{
            "name": "my-app",
            "scripts": {
                "build": "tsc",
                "start": "node dist/index.js",
                "test": "jest",
                "build-docs": "typedoc"
            }
        }""",
    }
    result = discover_tools_from_repo(scout, arch, file_contents=file_contents)
    script_tools = [t for t in result if t.tool_type == "script"]
    assert len(script_tools) >= 4
    names = {t.name for t in script_tools}
    assert "build" in names
    assert "start" in names
    assert "test" in names
    assert "build-docs" in names
    for t in script_tools:
        assert t.command is not None
        assert "npm run" in t.command or t.command == "npm run " + t.name
        assert t.source_path == "package.json"
        assert 0 <= t.confidence <= 1


def test_detect_pyproject_scripts() -> None:
    """Repo containing pyproject.toml with [project.scripts] -> expect CLI tools detected."""
    scout = {"repo_summary": "Python CLI", "important_files": ["pyproject.toml"], "language_hints": ["Python"], "framework_hints": []}
    arch = {"languages": ["Python"], "frameworks": [], "services": [], "entrypoints": [], "integrations": [], "key_paths": []}
    file_contents = {
        "pyproject.toml": """
[project]
name = "mycli"
version = "0.1.0"

[project.scripts]
mycli = "package.cli:main"
requests_cli = "requests.__main__:main"
""",
    }
    result = discover_tools_from_repo(scout, arch, file_contents=file_contents)
    cli_tools = [t for t in result if t.tool_type == "cli"]
    assert len(cli_tools) >= 2
    names = {t.name for t in cli_tools}
    assert "mycli" in names
    assert "requests_cli" in names
    for t in cli_tools:
        assert t.command == t.name
        assert t.source_path == "pyproject.toml"
        assert t.confidence == 0.9


def test_detect_openapi() -> None:
    """Repo containing openapi.yaml -> expect http_api tool detected."""
    scout = {"repo_summary": "API service", "important_files": ["openapi.yaml"], "language_hints": [], "framework_hints": ["API service"]}
    arch = {"languages": [], "frameworks": [], "services": ["api"], "entrypoints": [], "integrations": [], "key_paths": ["openapi.yaml"]}
    file_contents = {
        "openapi.yaml": "openapi: 3.0.0\ninfo:\n  title: Test API\n  version: 1.0.0\npaths:\n  /health:\n    get:\n      summary: Health check\n",
    }
    result = discover_tools_from_repo(scout, arch, file_contents=file_contents)
    api_tools = [t for t in result if t.tool_type == "http_api"]
    assert len(api_tools) == 1
    assert api_tools[0].name == "openapi_api"
    assert api_tools[0].command == "HTTP API from OpenAPI spec"
    assert api_tools[0].source_path == "openapi.yaml"


def test_detect_openapi_json() -> None:
    """Repo containing openapi.json -> expect http_api tool detected."""
    scout = {"repo_summary": "API", "important_files": ["openapi.json"], "language_hints": [], "framework_hints": []}
    arch = {"languages": [], "frameworks": [], "services": [], "entrypoints": [], "integrations": [], "key_paths": []}
    file_contents = {"openapi.json": '{"openapi":"3.0.0","info":{"title":"API"}}'}
    result = discover_tools_from_repo(scout, arch, file_contents=file_contents)
    api_tools = [t for t in result if t.tool_type == "http_api"]
    assert len(api_tools) == 1
    assert api_tools[0].source_path == "openapi.json"


def test_detect_mcp() -> None:
    """Repo containing mcp.json -> expect mcp_server tool detected."""
    scout = {"repo_summary": "MCP server", "important_files": ["mcp.json"], "language_hints": [], "framework_hints": []}
    arch = {"languages": [], "frameworks": [], "services": [], "entrypoints": [], "integrations": [], "key_paths": []}
    file_contents = {"mcp.json": "{}"}
    result = discover_tools_from_repo(scout, arch, file_contents=file_contents)
    mcp_tools = [t for t in result if t.tool_type == "mcp_server"]
    assert len(mcp_tools) == 1
    assert mcp_tools[0].name == "mcp_server"
    assert mcp_tools[0].source_path == "mcp.json"


def test_detect_cli_folder_entries() -> None:
    """Repo with bin/ or scripts/ folder -> expect tools for executable files (.sh, no-ext; .py as python_script)."""
    scout = {"repo_summary": "CLI project", "important_files": [], "language_hints": ["Python"], "framework_hints": []}
    arch = {"languages": ["Python"], "frameworks": [], "services": [], "entrypoints": [], "integrations": [], "key_paths": ["bin/run", "scripts/build.sh"]}
    folder_listings = {
        "bin": [
            {"path": "bin/run", "type": "file"},
            {"path": "bin/helper.py", "type": "file"},
        ],
        "scripts": [
            {"path": "scripts/build.sh", "type": "file"},
            {"path": "scripts/README", "type": "file"},
        ],
    }
    result = discover_tools_from_repo(scout, arch, folder_listings=folder_listings)
    script_tools = [t for t in result if t.tool_type == "script" and t.source_path.startswith(("bin/", "scripts/"))]
    python_tools = [t for t in result if t.tool_type == "python_script" and t.source_path.startswith(("bin/", "scripts/"))]
    assert len(script_tools) >= 1
    assert len(python_tools) >= 1 or "run" in {t.name for t in script_tools}
    names = {t.name for t in script_tools + python_tools}
    assert "build.sh" in names or "run" in names or "helper" in names


def test_get_paths_to_inspect_for_tools() -> None:
    """get_paths_to_inspect_for_tools returns file paths and folder paths."""
    scout = {"important_files": ["package.json", "src/package.json"], "language_hints": []}
    arch = {"key_paths": ["openapi.yaml", "bin/run"]}
    file_paths, folder_paths = get_paths_to_inspect_for_tools(scout, arch)
    assert "package.json" in file_paths
    assert "openapi.yaml" in file_paths
    assert "pyproject.toml" in file_paths
    assert "mcp.json" in file_paths
    assert "bin" in folder_paths
    assert "scripts" in folder_paths
    assert "cli" in folder_paths
    assert "tools" in folder_paths
    assert "Makefile" in file_paths or "makefile" in file_paths
    assert "Dockerfile" in file_paths
    assert "docker-compose.yml" in file_paths


def test_discover_tools_from_repo_empty_without_files() -> None:
    """Without file_contents or folder_listings, discovery returns empty or path-only detections."""
    scout = {"repo_summary": "Repo", "important_files": [], "language_hints": [], "framework_hints": []}
    arch = {"languages": [], "frameworks": [], "services": [], "entrypoints": [], "integrations": [], "key_paths": []}
    result = discover_tools_from_repo(scout, arch)
    assert isinstance(result, list)
    # No file content -> no package.json/pyproject/openapi/mcp tools; no folder listings -> no bin/scripts/cli
    assert len(result) == 0


def test_detect_makefile_targets() -> None:
    """Makefile with targets -> expect make_target tools."""
    scout = {"repo_summary": "C project", "important_files": ["Makefile"], "language_hints": ["C"], "framework_hints": []}
    arch = {"languages": ["C"], "frameworks": [], "services": [], "entrypoints": [], "integrations": [], "key_paths": ["Makefile"]}
    file_contents = {
        "Makefile": """
.PHONY: all clean
all:
\tcc -o main main.c
build: all
test:
\t./test_runner
lint:
\tclang-format -i *.c
""",
    }
    result = discover_tools_from_repo(scout, arch, file_contents=file_contents)
    make_tools = [t for t in result if t.tool_type == "make_target"]
    names = {t.name for t in make_tools}
    assert "build" in names
    assert "test" in names
    assert "lint" in names
    assert "all" not in names  # .PHONY / common ignored
    for t in make_tools:
        assert t.command == f"make {t.name}"
        assert t.source_path == "Makefile"


def test_detect_docker() -> None:
    """Dockerfile and compose files present -> expect container_command tools."""
    scout = {"repo_summary": "App", "important_files": ["Dockerfile"], "language_hints": [], "framework_hints": []}
    arch = {"key_paths": ["Dockerfile", "docker-compose.yml"], "languages": [], "frameworks": [], "services": [], "entrypoints": [], "integrations": []}
    file_contents = {
        "Dockerfile": "FROM node:18\nWORKDIR /app\nCOPY . .\nRUN npm install\n",
        "docker-compose.yml": "services:\n  web:\n    build: .\n",
    }
    result = discover_tools_from_repo(scout, arch, file_contents=file_contents)
    container = [t for t in result if t.tool_type == "container_command"]
    assert len(container) >= 1
    names = {t.name for t in container}
    assert "docker_build" in names or "docker_compose_up" in names


def test_detect_python_scripts_with_main() -> None:
    """Python file in scripts/ with __name__ == __main__ -> python_script with higher confidence."""
    scout = {"repo_summary": "Python", "important_files": [], "language_hints": ["Python"], "framework_hints": []}
    arch = {"languages": ["Python"], "frameworks": [], "services": [], "entrypoints": [], "integrations": [], "key_paths": []}
    file_contents = {
        "scripts/run_me.py": "#!/usr/bin/env python3\nimport sys\nif __name__ == \"__main__\":\n    main()\n",
    }
    result = discover_tools_from_repo(scout, arch, file_contents=file_contents)
    py_tools = [t for t in result if t.tool_type == "python_script" and "run_me" in (t.name or "")]
    assert len(py_tools) >= 1
    assert py_tools[0].confidence >= 0.9
    assert "python" in (py_tools[0].command or "")


def test_discovered_repo_tool_serialization() -> None:
    """DiscoveredRepoTool is Pydantic and serializes for API output."""
    t = DiscoveredRepoTool(
        name="build_docs",
        tool_type="script",
        command="npm run build-docs",
        description="Build docs",
        source_path="package.json",
        confidence=0.9,
    )
    d = t.model_dump()
    assert d["name"] == "build_docs"
    assert d["tool_type"] == "script"
    assert d["command"] == "npm run build-docs"
    assert d["source_path"] == "package.json"
    assert d["confidence"] == 0.9
