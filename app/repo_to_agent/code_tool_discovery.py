"""
Code-defined tool discovery: detect tools defined in source code (LangChain @tool, Tool(...), MCP, etc.).

Deterministic, rule-based only. No LLM. No code execution. Text/regex inspection only.
Returns DiscoveredRepoTool objects for merging with manifest/file-based discovery.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .repo_tool_discovery import DiscoveredRepoTool

# Source extensions we inspect for code-defined tools.
CODE_EXTENSIONS = (".py", ".ts", ".tsx", ".js", ".jsx")

# Path segments and name substrings that suggest agent/tool/MCP code.
PRIORITY_PATH_SEGMENTS = ("agents", "tools", "src", "app", "server")
PRIORITY_NAME_SUBSTRINGS = ("agent", "tool", "mcp", "server", "assistant", "workflow")

# Low-signal paths that are often noisy in demo output (fixtures/examples/tests).
EXCLUDED_PATH_SEGMENTS = (
    "tests",
    "test",
    "__tests__",
    "fixtures",
    "fixture",
    "examples",
    "example",
    "sample",
    "samples",
    "mock",
    "mocks",
)

# Confidence values.
CONF_HIGH = 0.9
CONF_MEDIUM = 0.75
CONF_LOW = 0.5


def _normalize_scout(scout: Any) -> Dict[str, Any]:
    if hasattr(scout, "model_dump"):
        return scout.model_dump()
    return dict(scout) if isinstance(scout, dict) else {}


def _normalize_arch(arch: Any) -> Dict[str, Any]:
    if hasattr(arch, "model_dump"):
        return arch.model_dump()
    return dict(arch) if isinstance(arch, dict) else {}


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if x is not None and str(x).strip()]
    return [str(value).strip()] if str(value).strip() else []


def get_paths_to_inspect_for_code_tools(scout: Any, arch: Any) -> List[str]:
    """
    Produce a conservative list of likely source file paths to fetch for code tool detection.

    Uses important_files, key_paths, entrypoints, and known source folders.
    Prioritizes paths that look like agent/tool/MCP code; only includes .py, .ts, .tsx, .js, .jsx.
    """
    scout_d = _normalize_scout(scout)
    arch_d = _normalize_arch(arch)
    important = _as_list(scout_d.get("important_files"))
    key_paths = _as_list(arch_d.get("key_paths"))
    entrypoints = _as_list(arch_d.get("entrypoints"))
    all_paths = set(important + key_paths + entrypoints)

    # Collect paths that are source files we care about.
    candidates: List[tuple[int, str]] = []  # (priority_lower_is_better, path)
    for p in all_paths:
        p_lower = p.lower()
        if not any(p_lower.endswith(ext) for ext in CODE_EXTENSIONS):
            continue
        parts = [s.lower() for s in p.split("/") if s]
        if any(seg in parts for seg in EXCLUDED_PATH_SEGMENTS):
            continue
        priority = 100
        for seg in PRIORITY_PATH_SEGMENTS:
            if seg in parts:
                priority = min(priority, 10)
                break
        base = (parts[-1] or "") if parts else ""
        for kw in PRIORITY_NAME_SUBSTRINGS:
            if kw in base:
                priority = min(priority, 20)
                break
        candidates.append((priority, p))

    # Sort by priority then path; return unique paths.
    candidates.sort(key=lambda x: (x[0], x[1]))
    seen: set[str] = set()
    out: List[str] = []
    for _, path in candidates:
        if path not in seen:
            seen.add(path)
            out.append(path)
    return out


# ---- Python: @tool decorator ----
_RE_TOOL_DECORATOR = re.compile(
    r"@tool\s*(?:\(\s*[\"']([^\"']+)[\"']\s*\))?\s*\n\s*def\s+(\w+)\s*\(",
    re.MULTILINE,
)


def _detect_python_tool_decorator(content: str, source_path: str) -> List[DiscoveredRepoTool]:
    tools: List[DiscoveredRepoTool] = []
    for m in _RE_TOOL_DECORATOR.finditer(content):
        explicit_name = m.group(1)
        func_name = m.group(2)
        name = (explicit_name or func_name or "").strip() or "unknown"
        if not name:
            continue
        # Best-effort docstring: next non-empty triple-quoted string after the match
        rest = content[m.end() :]
        desc = "Code-defined tool detected via @tool decorator"
        doc_match = re.search(r'"""([^"]*?)"""|\'\'\'([^\']*?)\'\'\'', rest, re.DOTALL)
        if doc_match:
            doc = (doc_match.group(1) or doc_match.group(2) or "").strip()
            if doc:
                desc = doc.split("\n")[0].strip()[:500]
        tools.append(
            DiscoveredRepoTool(
                name=name,
                tool_type="code_tool",
                command=None,
                description=desc,
                source_path=source_path,
                confidence=CONF_HIGH,
            )
        )
    return tools


# ---- Python: Tool(name=...) ----
_RE_TOOL_NAME = re.compile(
    r"Tool\s*\(\s*name\s*=\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
_RE_STRUCTURED_TOOL_NAME = re.compile(
    r"StructuredTool\s*\(\s*name\s*=\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
_RE_STRUCTURED_TOOL_DESC = re.compile(
    r"StructuredTool\s*\([^)]*description\s*=\s*[\"']([^\"']*)[\"']",
    re.IGNORECASE | re.DOTALL,
)
_RE_TOOL_DESC = re.compile(
    r"Tool\s*\([^)]*description\s*=\s*[\"']([^\"']*)[\"']",
    re.IGNORECASE | re.DOTALL,
)


def _detect_python_tool_constructor(content: str, source_path: str) -> List[DiscoveredRepoTool]:
    tools: List[DiscoveredRepoTool] = []
    seen_names: set[str] = set()

    for pattern, desc_pattern in [
        (_RE_TOOL_NAME, _RE_TOOL_DESC),
        (_RE_STRUCTURED_TOOL_NAME, _RE_STRUCTURED_TOOL_DESC),
    ]:
        for m in pattern.finditer(content):
            name = (m.group(1) or "").strip()
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            desc = "Code-defined tool (Tool/StructuredTool)"
            dm = desc_pattern.search(content, max(0, m.start() - 200), m.end() + 500)
            if dm:
                d = (dm.group(1) or "").strip()
                if d:
                    desc = d.split("\n")[0].strip()[:500]
            tools.append(
                DiscoveredRepoTool(
                    name=name,
                    tool_type="code_tool",
                    command=None,
                    description=desc,
                    source_path=source_path,
                    confidence=CONF_HIGH,
                )
            )
    return tools


# ---- Python: StructuredTool.from_function ----
# Prefer explicit name= when present; else capture function name.
_RE_FROM_FUNCTION_EXPLICIT = re.compile(
    r"StructuredTool\s*\.\s*from_function\s*\([^)]*name\s*=\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
_RE_FROM_FUNCTION_FUNC = re.compile(
    r"StructuredTool\s*\.\s*from_function\s*\(\s*(\w+)",
    re.IGNORECASE,
)


def _detect_python_from_function(content: str, source_path: str) -> List[DiscoveredRepoTool]:
    tools: List[DiscoveredRepoTool] = []
    seen: set[str] = set()
    # Explicit name= first
    for m in _RE_FROM_FUNCTION_EXPLICIT.finditer(content):
        name = (m.group(1) or "").strip()
        if name and name not in seen:
            seen.add(name)
            tools.append(
                DiscoveredRepoTool(
                    name=name,
                    tool_type="code_tool",
                    command=None,
                    description="Code-defined tool (StructuredTool.from_function)",
                    source_path=source_path,
                    confidence=CONF_HIGH,
                )
            )
    # Then function name (when no name= in that call)
    for m in _RE_FROM_FUNCTION_FUNC.finditer(content):
        # Only accept if this call doesn't have name= (avoid duplicate with different name)
        start, end = m.span()
        chunk = content[start : end + 120]
        if "name=" in chunk:
            continue
        name = (m.group(1) or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        tools.append(
            DiscoveredRepoTool(
                name=name,
                tool_type="code_tool",
                command=None,
                description="Code-defined tool (StructuredTool.from_function)",
                source_path=source_path,
                confidence=CONF_HIGH,
            )
        )
    return tools


# ---- Python: tool registry (boost only; optional registry note) ----
_RE_TOOLS_LIST = re.compile(
    r"(?:^|\s)(?:tools|agent_tools|available_tools)\s*=\s*\[",
    re.MULTILINE,
)


def _has_tool_registry(content: str) -> bool:
    return _RE_TOOLS_LIST.search(content) is not None


# ---- JS/TS: new DynamicTool / DynamicStructuredTool ----
_RE_JS_DYNAMIC_TOOL = re.compile(
    r"new\s+DynamicTool\s*\(\s*\{[^}]*name\s*:\s*[\"']([^\"']+)[\"']",
    re.MULTILINE | re.DOTALL,
)
_RE_JS_DYNAMIC_STRUCTURED = re.compile(
    r"new\s+DynamicStructuredTool\s*\(\s*\{[^}]*name\s*:\s*[\"']([^\"']+)[\"']",
    re.MULTILINE | re.DOTALL,
)
_RE_JS_DYNAMIC_DESC = re.compile(
    r"name\s*:\s*[\"'][^\"']+[\"']\s*,\s*description\s*:\s*[\"']([^\"']*)[\"']",
    re.MULTILINE,
)


def _detect_js_dynamic_tool(content: str, source_path: str) -> List[DiscoveredRepoTool]:
    tools: List[DiscoveredRepoTool] = []
    seen: set[str] = set()
    for pattern in (_RE_JS_DYNAMIC_TOOL, _RE_JS_DYNAMIC_STRUCTURED):
        for m in pattern.finditer(content):
            name = (m.group(1) or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            desc = "Code-defined tool (DynamicTool/DynamicStructuredTool)"
            # Look for description near this match
            span = content[max(0, m.start() - 50) : m.end() + 300]
            dm = _RE_JS_DYNAMIC_DESC.search(span)
            if dm and dm.group(1):
                desc = dm.group(1).strip()[:500]
            tools.append(
                DiscoveredRepoTool(
                    name=name,
                    tool_type="code_tool",
                    command=None,
                    description=desc,
                    source_path=source_path,
                    confidence=CONF_HIGH,
                )
            )
    return tools


# ---- MCP: only when MCP context is present ----
_MCP_INDICATORS = re.compile(
    r"FastMCP|MCPServer|createMcpServer|mcp\.tool|server\.tool|register_tool|registerTool|"
    r"Model Context Protocol|MCP server",
    re.IGNORECASE,
)
_RE_MCP_TOOL_CALL = re.compile(
    r"(?:server|mcp|fast_mcp)\s*\.\s*(?:tool|register_tool)\s*\(\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
_RE_JS_REGISTER_TOOL = re.compile(
    r"registerTool\s*\(\s*[\"']([^\"']+)[\"']|\.tool\s*\(\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)


def _detect_mcp_code_tools(content: str, source_path: str) -> List[DiscoveredRepoTool]:
    if not _MCP_INDICATORS.search(content):
        return []
    tools: List[DiscoveredRepoTool] = []
    seen: set[str] = set()
    for m in _RE_MCP_TOOL_CALL.finditer(content):
        name = (m.group(1) or "").strip()
        if name and name not in seen:
            seen.add(name)
            tools.append(
                DiscoveredRepoTool(
                    name=name,
                    tool_type="mcp_code_tool",
                    command=None,
                    description="MCP tool registration detected in code",
                    source_path=source_path,
                    confidence=CONF_MEDIUM,
                )
            )
    for m in _RE_JS_REGISTER_TOOL.finditer(content):
        name = (m.group(1) or m.group(2) or "").strip()
        if name and name not in seen:
            seen.add(name)
            tools.append(
                DiscoveredRepoTool(
                    name=name,
                    tool_type="mcp_code_tool",
                    command=None,
                    description="MCP tool registration detected in code",
                    source_path=source_path,
                    confidence=CONF_MEDIUM,
                )
            )
    # If we found MCP indicators but no named tools, one conservative entry
    if not tools and _MCP_INDICATORS.search(content):
        tools.append(
            DiscoveredRepoTool(
                name="mcp_server_code_tools",
                tool_type="mcp_code_tool",
                command=None,
                description="MCP tool registration patterns detected in code",
                source_path=source_path,
                confidence=CONF_LOW,
            )
        )
    return tools


# ---- Optional: FastAPI routes (capability signal) ----
_RE_FASTAPI_ROUTE = re.compile(
    r"@(?:app|router)\s*\.(?:get|post|put|delete|patch)\s*\(\s*[\"'][^\"']+[\"']",
    re.MULTILINE,
)


def _detect_fastapi_routes(content: str, source_path: str) -> List[DiscoveredRepoTool]:
    if "fastapi" not in content.lower() and "FastAPI" not in content:
        return []
    if not _RE_FASTAPI_ROUTE.search(content):
        return []
    return [
        DiscoveredRepoTool(
            name="fastapi_routes",
            tool_type="http_route",
            command=None,
            description="FastAPI route definitions detected",
            source_path=source_path,
            confidence=CONF_MEDIUM,
        )
    ]


def _boost_confidence_for_registry(
    result: List[DiscoveredRepoTool],
    path: str,
    has_registry: bool,
) -> None:
    if not has_registry:
        return
    for t in result:
        if t.source_path == path and t.confidence < CONF_HIGH:
            t.confidence = min(CONF_HIGH, t.confidence + 0.05)


def discover_code_defined_tools(
    scout_output: Any,
    architecture_output: Any,
    file_contents: Optional[Dict[str, str]] = None,
) -> List[DiscoveredRepoTool]:
    """
    Scan fetched source files and detect code-defined tools (no execution, text-only).

    Args:
        scout_output: RepoScoutOutput or dict.
        architecture_output: RepoArchitectureOutput or dict.
        file_contents: Optional map path -> file content. If None, returns [].

    Returns:
        List of DiscoveredRepoTool (code_tool, mcp_code_tool, http_route).
    """
    file_contents = file_contents or {}
    result: List[DiscoveredRepoTool] = []
    seen_key: set[tuple[str, str, str]] = set()

    def add(t: DiscoveredRepoTool) -> None:
        key = (t.name, t.tool_type, t.source_path)
        if key in seen_key:
            return
        seen_key.add(key)
        result.append(t)

    for path, content in file_contents.items():
        if not content or not isinstance(content, str):
            continue
        path_lower = path.lower()
        if not any(path_lower.endswith(ext) for ext in CODE_EXTENSIONS):
            continue

        if path_lower.endswith(".py"):
            for t in _detect_python_tool_decorator(content, path):
                add(t)
            for t in _detect_python_tool_constructor(content, path):
                add(t)
            for t in _detect_python_from_function(content, path):
                add(t)
            has_reg = _has_tool_registry(content)
            _boost_confidence_for_registry(result, path, has_reg)
            for t in _detect_mcp_code_tools(content, path):
                add(t)
            for t in _detect_fastapi_routes(content, path):
                add(t)
        else:
            for t in _detect_js_dynamic_tool(content, path):
                add(t)
            for t in _detect_mcp_code_tools(content, path):
                add(t)

    return result


_TOOL_TYPE_PRIORITY: Dict[str, int] = {
    "tool_definition": 4,
    "cli": 3,
    "script": 3,
    "python_script": 3,
    "make_target": 3,
    "http_api": 3,
    "mcp_server": 3,
    "code_tool": 3,
    "capability": 2,
    "likely_tool": 1,
}


def _canonical_tool_name(name: str) -> str:
    """Normalize tool name for deduplication."""
    return (name or "").strip().lower().replace("-", "_").replace(" ", "_") or ""


def merge_discovered_tools(
    manifest_tools: List[DiscoveredRepoTool],
    code_tools: List[DiscoveredRepoTool],
) -> List[DiscoveredRepoTool]:
    """
    Merge manifest/file-based and code-defined discoveries with consolidation.

    When the same tool appears from multiple sources (e.g. github_search from
    tools/*.json and agent.json capabilities), prefer tool_definition > capability
    > likely_tool. This reduces noise and duplicates in the extracted tool list.
    """
    combined = list(manifest_tools) + list(code_tools)
    by_canonical: Dict[str, DiscoveredRepoTool] = {}
    for t in combined:
        canon = _canonical_tool_name(t.name)
        if not canon:
            continue
        priority = _TOOL_TYPE_PRIORITY.get(t.tool_type, 0)
        existing = by_canonical.get(canon)
        existing_priority = _TOOL_TYPE_PRIORITY.get(existing.tool_type, 0) if existing else -1
        if existing is None or priority > existing_priority:
            by_canonical[canon] = t
        elif priority == existing_priority and (t.confidence or 0) > (existing.confidence or 0):
            by_canonical[canon] = t
    return list(by_canonical.values())
