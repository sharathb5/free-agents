"""
Repository tool discovery: detect tools that exist in the repo (CLI, scripts, OpenAPI, MCP, etc.).

Deterministic, rule-based only. No LLM calls. Returns a list of discovered tools for the user
to choose from; the system does not automatically add them to the agent.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class DiscoveredRepoTool(BaseModel):
    """A tool detected in the repository (CLI, script, HTTP API, MCP, etc.)."""

    name: str
    tool_type: str  # "cli" | "script" | "http_api" | "mcp_server"
    command: Optional[str] = None
    description: Optional[str] = None
    source_path: str = ""
    confidence: float = 1.0


# Standard paths we look for (root or in key_paths).
OPENAPI_SPEC_NAMES = ("openapi.yaml", "openapi.json", "openapi.yml", "swagger.yaml", "swagger.json")
MCP_CONFIG_NAME = "mcp.json"
PACKAGE_JSON_NAME = "package.json"
PYPROJECT_NAME = "pyproject.toml"
CLI_FOLDERS = ("bin", "scripts", "cli", "tools", "tasks", "automation", "examples")
MAKEFILE_NAMES = ("Makefile", "makefile", "GNUmakefile")
DOCKER_SPEC_NAMES = (
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
)
# Makefile targets to ignore (internal/phony patterns).
MAKEFILE_IGNORE_TARGETS = frozenset(
    (".PHONY", "default", "all", "install", "clean", "help", "")
)


def _normalize_scout(scout: Any) -> Dict[str, Any]:
    if hasattr(scout, "model_dump"):
        return scout.model_dump()
    return dict(scout) if isinstance(scout, dict) else {}


def _normalize_arch(arch: Any) -> Dict[str, Any]:
    if hasattr(arch, "model_dump"):
        return arch.model_dump()
    return dict(arch) if isinstance(arch, dict) else {}


def get_paths_to_inspect_for_tools(
    repo_scout_output: Any,
    architecture_output: Any,
) -> Tuple[List[str], List[str]]:
    """
    Return (file_paths, folder_paths) to fetch for tool discovery.

    file_paths: paths to fetch file content (e.g. package.json, pyproject.toml).
    folder_paths: paths to list (e.g. bin, scripts, cli).
    """
    scout = _normalize_scout(repo_scout_output)
    arch = _normalize_arch(architecture_output)
    important = scout.get("important_files") or []
    key_paths = arch.get("key_paths") or []
    all_paths = set(important + key_paths)

    file_paths_set: set = set()
    for p in all_paths:
        base = (p.split("/")[-1] or "").lower()
        if base in (PACKAGE_JSON_NAME, PYPROJECT_NAME, MCP_CONFIG_NAME) or base in OPENAPI_SPEC_NAMES:
            file_paths_set.add(p)
        if base in {m.lower() for m in MAKEFILE_NAMES}:
            file_paths_set.add(p)
        if base in {d.lower() for d in DOCKER_SPEC_NAMES}:
            file_paths_set.add(p)
    for name in (PACKAGE_JSON_NAME, PYPROJECT_NAME, MCP_CONFIG_NAME) + OPENAPI_SPEC_NAMES:
        file_paths_set.add(name)
    for name in MAKEFILE_NAMES:
        file_paths_set.add(name)
    for name in DOCKER_SPEC_NAMES:
        file_paths_set.add(name)
    file_paths_set.add("agent.json")
    file_paths = sorted(file_paths_set)

    # Always inspect root plus common CLI/script folders. Keep this list tight to avoid
    # tool explosion; deeper coverage is handled by code_tool_discovery.
    folder_paths = [""] + list(CLI_FOLDERS) + ["tasks", "automation", "examples"]
    return file_paths, folder_paths


def _detect_tools_dir_json(content: str, source_path: str) -> List[DiscoveredRepoTool]:
    """Parse tools/*.json tool definition files (name, description, etc.)."""
    tools: List[DiscoveredRepoTool] = []
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return tools
    if not isinstance(data, dict):
        return tools
    name = data.get("name") or data.get("id") or ""
    if isinstance(name, str) and name.strip():
        pass
    else:
        base = source_path.split("/")[-1].replace(".json", "")
        name = base.replace("-", "_").replace(" ", "_") or "tool"
    desc = data.get("description") or ""
    if isinstance(desc, str):
        desc = desc.strip()
    tools.append(
        DiscoveredRepoTool(
            name=name.strip() if isinstance(name, str) else str(name),
            tool_type="tool_definition",
            description=desc or f"Tool from {source_path}",
            source_path=source_path,
            confidence=0.95,
        )
    )
    return tools


def _detect_agent_json_capabilities(content: str) -> List[DiscoveredRepoTool]:
    """Extract capabilities and likely_tools from agent.json."""
    tools: List[DiscoveredRepoTool] = []
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return tools
    if not isinstance(data, dict):
        return tools
    seen: set = set()
    for key in ("capabilities", "likely_tools"):
        vals = data.get(key)
        if not isinstance(vals, list):
            continue
        for v in vals:
            if not isinstance(v, str) or not v.strip():
                continue
            name = v.strip()
            if "." in name:
                name = name.split(".")[-1]
            name = name.replace("-", "_").replace(" ", "_")
            if name and name not in seen:
                seen.add(name)
                tools.append(
                    DiscoveredRepoTool(
                        name=name,
                        tool_type="capability" if key == "capabilities" else "likely_tool",
                        description=f"From agent.json {key}",
                        source_path="agent.json",
                        confidence=0.9,
                    )
                )
    return tools


def _detect_pyproject_scripts(content: str, source_path: str) -> List[DiscoveredRepoTool]:
    tools: List[DiscoveredRepoTool] = []
    # [project.scripts] or [tool.xxx] with scripts
    in_scripts = False
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("[project.scripts]"):
            in_scripts = True
            continue
        if in_scripts:
            if line.startswith("["):
                break
            # key = "module:func" or key = 'module:func'
            match = re.match(r'^([a-zA-Z0-9_-]+)\s*=\s*["\']([^"\']+)["\']', line)
            if match:
                name, _ = match.groups()
                tools.append(
                    DiscoveredRepoTool(
                        name=name,
                        tool_type="cli",
                        command=name,
                        description=f"CLI entry point from {source_path}",
                        source_path=source_path,
                        confidence=0.9,
                    )
                )
    return tools


def _detect_package_json_scripts(content: str, source_path: str) -> List[DiscoveredRepoTool]:
    tools: List[DiscoveredRepoTool] = []
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return tools
    scripts = data.get("scripts")
    if not isinstance(scripts, dict):
        return tools
    for name, cmd in scripts.items():
        if not name or not isinstance(cmd, str):
            continue
        command = f"npm run {name}" if not cmd.startswith("npm ") else cmd
        tools.append(
            DiscoveredRepoTool(
                name=name,
                tool_type="script",
                command=command,
                description=f"npm script from {source_path}",
                source_path=source_path,
                confidence=0.9,
            )
        )
    return tools


def _detect_openapi(content: str, source_path: str) -> List[DiscoveredRepoTool]:
    return [
        DiscoveredRepoTool(
            name="openapi_api",
            tool_type="http_api",
            command="HTTP API from OpenAPI spec",
            description=f"OpenAPI/Swagger spec at {source_path}",
            source_path=source_path,
            confidence=0.95,
        )
    ]


def _detect_mcp(content: str, source_path: str) -> List[DiscoveredRepoTool]:
    return [
        DiscoveredRepoTool(
            name="mcp_server",
            tool_type="mcp_server",
            command=None,
            description=f"MCP config at {source_path}",
            source_path=source_path,
            confidence=0.9,
        )
    ]


def _detect_makefile_targets(content: str, source_path: str) -> List[DiscoveredRepoTool]:
    """Parse Makefile for top-level targets (rules that look like 'target:' at start of line)."""
    tools: List[DiscoveredRepoTool] = []
    # Match line that starts with optional whitespace then a target name and colon (not a variable).
    target_re = re.compile(r"^\s*([a-zA-Z0-9_.-]+)\s*:(?:\s|$)")
    for line in content.splitlines():
        m = target_re.match(line)
        if not m:
            continue
        target = m.group(1).strip()
        if target in MAKEFILE_IGNORE_TARGETS:
            continue
        tools.append(
            DiscoveredRepoTool(
                name=target,
                tool_type="make_target",
                command=f"make {target}",
                description=f"Makefile target from {source_path}",
                source_path=source_path,
                confidence=0.85,
            )
        )
    return tools


def _detect_docker_tools(path: str) -> List[DiscoveredRepoTool]:
    """One discovered tool per Docker-related file (Dockerfile or compose file)."""
    base = path.split("/")[-1].lower()
    if base == "dockerfile":
        return [
            DiscoveredRepoTool(
                name="docker_build",
                tool_type="container_command",
                command="docker build",
                description=f"Dockerfile at {path}",
                source_path=path,
                confidence=0.9,
            )
        ]
    if base in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
        return [
            DiscoveredRepoTool(
                name="docker_compose_up",
                tool_type="container_command",
                command="docker compose up",
                description=f"Compose file at {path}",
                source_path=path,
                confidence=0.9,
            )
        ]
    return []


def _detect_python_scripts_in_folders(entries: List[Dict[str, Any]], folder_path: str) -> List[DiscoveredRepoTool]:
    """Detect .py files in tools/, scripts/, bin/ as potential Python scripts."""
    tools: List[DiscoveredRepoTool] = []
    for e in entries:
        path = (e.get("path") or e.get("name") or "").strip()
        if not path:
            continue
        typ = (e.get("type") or "file").lower()
        if typ != "file":
            continue
        if not path.endswith(".py"):
            continue
        base = path.split("/")[-1]
        if not base or base.startswith("."):
            continue
        if base == "__init__.py":
            continue
        tools.append(
            DiscoveredRepoTool(
                name=base.replace(".py", "").replace("-", "_"),
                tool_type="python_script",
                command=f"python {path}",
                description=f"Python script in {folder_path}/",
                source_path=path,
                confidence=0.65,
            )
        )
    return tools


def _detect_python_scripts_with_content(file_contents: Dict[str, str]) -> List[DiscoveredRepoTool]:
    """Upgrade or add Python script tools when file content has __main__ or shebang."""
    tools: List[DiscoveredRepoTool] = []
    for path, content in file_contents.items():
        if not path.endswith(".py"):
            continue
        parts = path.split("/")
        if not parts:
            continue
        top = (parts[0] or "").lower()
        if top not in ("tools", "scripts", "bin"):
            continue
        content_lower = content.strip().lower()
        has_main = '__name__' in content and '__main__' in content_lower
        has_shebang = content.strip().startswith("#!") and "python" in content.split("\n")[0].lower()
        if not (has_main or has_shebang):
            continue
        base = path.split("/")[-1]
        if base == "__init__.py":
            continue
        name = base.replace(".py", "").replace("-", "_")
        tools.append(
            DiscoveredRepoTool(
                name=name,
                tool_type="python_script",
                command=f"python {path}",
                description=f"Executable Python script at {path}",
                source_path=path,
                confidence=0.9,
            )
        )
    return tools


def _detect_cli_folder_entries(entries: List[Dict[str, Any]], folder_path: str) -> List[DiscoveredRepoTool]:
    """Detect executable-looking files in bin/, scripts/, cli/, tools/ (.py, .sh, .bash, .js, etc.)."""
    tools: List[DiscoveredRepoTool] = []
    exec_extensions = (".py", ".sh", ".bash", ".js", ".mjs", ".cjs")
    ignore_basenames = {
        "readme",
        "readme.md",
        "license",
        "license.md",
        "copying",
        "notice",
        "changelog",
        "changelog.md",
        "contributing",
        "contributing.md",
        "code_of_conduct",
        "code_of_conduct.md",
    }
    for e in entries:
        path = (e.get("path") or e.get("name") or "").strip()
        if not path:
            continue
        typ = (e.get("type") or "file").lower()
        if typ != "file":
            continue
        base = path.split("/")[-1]
        if not base or base.startswith("."):
            continue
        base_lower = base.lower()
        # Ignore common non-executable repo docs/metadata files.
        if base_lower in ignore_basenames:
            continue
        # .py handled by _detect_python_scripts_in_folders and _detect_python_scripts_with_content
        if base.endswith(".py"):
            continue
        # tools/*.json are tool definitions, not scripts
        if folder_path == "tools" and base.endswith(".json"):
            continue
        # Match known script extensions only.
        # Do NOT treat extensionless files as executables unless we can confirm a shebang,
        # because repo listings don't reliably provide executable permission bits.
        if any(base_lower.endswith(ext) for ext in exec_extensions):
            tool_type = "script"
            tools.append(
                DiscoveredRepoTool(
                    name=base,
                    tool_type=tool_type,
                    command=path,
                    description=f"Executable in {folder_path}/",
                    source_path=path,
                    confidence=0.7,
                )
            )
    return tools


def discover_tools_from_repo(
    repo_scout_output: Any,
    architecture_output: Any,
    file_contents: Optional[Dict[str, str]] = None,
    folder_listings: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> List[DiscoveredRepoTool]:
    """
    Scan repository files and detect tools that exist in the repo.

    Deterministic, rule-based only. No LLM.

    Args:
        repo_scout_output: RepoScoutOutput or dict (repo_summary, important_files, etc.).
        architecture_output: RepoArchitectureOutput or dict (key_paths, entrypoints, etc.).
        file_contents: Optional map path -> file content (e.g. from github_repo_read file mode).
        folder_listings: Optional map folder_path -> list of entries (path, type) from tree mode.

    Returns:
        List of DiscoveredRepoTool. Does not modify the agent; caller shows these to the user.
    """
    file_contents = file_contents or {}
    folder_listings = folder_listings or {}
    seen: set = set()
    result: List[DiscoveredRepoTool] = []

    def add(t: DiscoveredRepoTool) -> None:
        key = (t.name, t.tool_type, t.source_path)
        if key not in seen:
            seen.add(key)
            result.append(t)

    # 1. pyproject.toml [project.scripts]
    for path, content in file_contents.items():
        if path.endswith(PYPROJECT_NAME) and content:
            for t in _detect_pyproject_scripts(content, path):
                add(t)

    # 2. package.json scripts
    for path, content in file_contents.items():
        if path.endswith(PACKAGE_JSON_NAME) and content:
            for t in _detect_package_json_scripts(content, path):
                add(t)

    # 3. OpenAPI / Swagger
    for path, content in file_contents.items():
        base = path.split("/")[-1].lower()
        if base in OPENAPI_SPEC_NAMES and content.strip():
            for t in _detect_openapi(content, path):
                add(t)

    # 4. MCP
    for path, content in file_contents.items():
        if path.endswith(MCP_CONFIG_NAME) and content.strip():
            for t in _detect_mcp(content, path):
                add(t)

    # 4b. Makefile targets
    for path, content in file_contents.items():
        base = path.split("/")[-1]
        if base in MAKEFILE_NAMES and content.strip():
            for t in _detect_makefile_targets(content, path):
                add(t)

    # 4c. Docker / Compose (file presence; content not required)
    for path in file_contents.keys():
        base = (path.split("/")[-1] or "").lower()
        if base in {d.lower() for d in DOCKER_SPEC_NAMES}:
            for t in _detect_docker_tools(path):
                add(t)

    # 4d. Python scripts with __main__ or shebang (from file content)
    for t in _detect_python_scripts_with_content(file_contents):
        add(t)

    # 4e. tools/*.json (tool definition files)
    for path, content in file_contents.items():
        if "/" in path and path.startswith("tools/") and path.lower().endswith(".json") and content.strip():
            for t in _detect_tools_dir_json(content, path):
                add(t)

    # 4f. agent.json capabilities and likely_tools
    agent_content = file_contents.get("agent.json") or ""
    if agent_content.strip():
        for t in _detect_agent_json_capabilities(agent_content):
            add(t)

    # 5. bin/ scripts/ cli/ tools/ (shell scripts, js, etc.; .py via _detect_python_scripts_in_folders)
    for folder_path, entries in folder_listings.items():
        for t in _detect_cli_folder_entries(entries, folder_path):
            add(t)
        for t in _detect_python_scripts_in_folders(entries, folder_path):
            add(t)

    return result
