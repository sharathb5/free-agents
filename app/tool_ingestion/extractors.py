from __future__ import annotations

import ast
import json
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .models import CAPABILITY_CATEGORIES, ToolCandidate, default_args_schema

RepoFile = Dict[str, str]  # {"path": "...", "content": "..."}
RepoFiles = List[RepoFile]


_KW_SEARCH = ("search", "retrieve", "retrieval", "rag", "index", "vector", "embedding", "bm25")
_KW_HTTP = ("http", "https", "api", "rest", "graphql", "request", "requests", "httpx", "axios", "fetch", "curl")
_KW_FILES = ("file", "files", "path", "filesystem", "fs", "readfile", "writefile", "mkdir", "rm", "cp", "mv")
_KW_DB = ("sql", "sqlite", "postgres", "mysql", "db", "database", "query", "select", "insert", "update", "delete", "orm")
_KW_COMM = ("email", "smtp", "slack", "discord", "twilio", "sms", "notify", "notification", "webhook", "pagerduty")


def _text_hints(*parts: Optional[str]) -> str:
    return " ".join([p.strip().lower() for p in parts if p and p.strip()])


def infer_capability_category(
    *,
    name: str,
    description: str | None,
    source_path: str,
    tool_type: str,
    execution_kind: str,
    tags: Iterable[str],
) -> str:
    """
    Deterministic single-bucket classification into one of the six required categories.
    """
    text = _text_hints(name, description or "", source_path, tool_type, execution_kind, " ".join(tags))

    def has_any(keywords: Tuple[str, ...]) -> bool:
        return any(kw in text for kw in keywords)

    if has_any(_KW_SEARCH):
        return "search_retrieval"
    if has_any(_KW_DB):
        return "structured_data"
    if has_any(_KW_HTTP):
        return "http_api_access"
    if has_any(_KW_FILES):
        return "file_filesystem"
    if has_any(_KW_COMM):
        return "communication"
    return "code_execution"


def _ast_name_or_attr(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _json_type_from_annotation(ann: Optional[ast.AST]) -> str:
    if ann is None:
        return "string"
    if isinstance(ann, ast.Name):
        n = ann.id
    elif isinstance(ann, ast.Attribute):
        n = ann.attr
    elif isinstance(ann, ast.Subscript) and isinstance(ann.value, ast.Name):
        n = ann.value.id
    else:
        n = ""
    n = (n or "").lower()
    if n in ("int", "integer"):
        return "integer"
    if n in ("float", "double", "number"):
        return "number"
    if n in ("bool", "boolean"):
        return "boolean"
    if n in ("dict", "mapping"):
        return "object"
    if n in ("list", "tuple", "set", "sequence"):
        return "array"
    return "string"


def _args_schema_from_function_def(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> Dict[str, Any]:
    schema = default_args_schema(allow_additional=False)
    props: Dict[str, Any] = {}
    required: List[str] = []

    args = list(fn.args.args)
    if args and args[0].arg in ("self", "cls"):
        args = args[1:]

    defaults = list(fn.args.defaults or [])
    defaults_by_position = {len(args) - len(defaults) + i: d for i, d in enumerate(defaults)}

    for idx, a in enumerate(args):
        name = a.arg
        typ = _json_type_from_annotation(a.annotation)
        props[name] = {"type": typ}
        if idx not in defaults_by_position:
            required.append(name)

    schema["properties"] = props
    schema["required"] = required
    schema["additionalProperties"] = False
    return schema


def _snippet_from_source(source: str, node: ast.AST, *, max_lines: int = 60) -> str:
    lines = source.splitlines()
    start = getattr(node, "lineno", 1) - 1
    end = getattr(node, "end_lineno", None)
    if isinstance(end, int):
        end0 = min(end, len(lines))
    else:
        end0 = min(start + max_lines, len(lines))
    start0 = max(0, start - 3)
    return "\n".join(lines[start0:end0])


def extractor_langchain(repo_files: RepoFiles, source_repo: str) -> List[ToolCandidate]:
    out: List[ToolCandidate] = []
    for rf in repo_files:
        path = rf.get("path") or ""
        if not path.endswith(".py"):
            continue
        content = rf.get("content") or ""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue

        # @tool decorated functions
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decorators = list(node.decorator_list or [])
            is_tool = False
            dec_name = ""
            for dec in decorators:
                if isinstance(dec, ast.Call):
                    dec_name = _ast_name_or_attr(dec.func)
                else:
                    dec_name = _ast_name_or_attr(dec)
                if dec_name == "tool":
                    is_tool = True
                    break
            if not is_tool:
                continue

            doc = ast.get_docstring(node) or ""
            desc = doc.strip().splitlines()[0].strip() if doc.strip() else ""
            args_schema = _args_schema_from_function_def(node)
            snippet = _snippet_from_source(content, node)
            name = node.name
            # decorator may specify name=...
            for dec in decorators:
                if isinstance(dec, ast.Call) and _ast_name_or_attr(dec.func) == "tool":
                    for kw in dec.keywords or []:
                        if kw.arg == "name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                            name = kw.value.value.strip() or name
            cand = ToolCandidate(
                name=name,
                description=desc,
                source_repo=source_repo,
                source_path=path,
                tool_type="langchain_tool",
                execution_kind="python_function",
                args_schema=args_schema,
                risk_level="medium",
                tags=["langchain", "decorator"],
                confidence=0.9,
                promotion_reason=None,
                raw_snippet=snippet,
            )
            cand.capability_category = infer_capability_category(
                name=cand.name,
                description=cand.description,
                source_path=cand.source_path,
                tool_type=cand.tool_type,
                execution_kind=cand.execution_kind,
                tags=cand.tags,
            )
            out.append(cand.with_computed_fields())

        # Tool(...) / StructuredTool(...)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn_name = _ast_name_or_attr(node.func)
            if fn_name not in ("Tool", "StructuredTool"):
                continue

            name = None
            desc = None
            args_schema: Dict[str, Any] = default_args_schema(allow_additional=True)
            explicit_schema = False

            for kw in node.keywords or []:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    name = kw.value.value.strip()
                if kw.arg in ("description", "desc") and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    desc = kw.value.value.strip()
                if kw.arg in ("args_schema", "args_schema_json", "input_schema"):
                    explicit_schema = True
                    if isinstance(kw.value, ast.Dict):
                        # Best-effort static extraction for literal dict schemas.
                        try:
                            lit = ast.literal_eval(kw.value)
                            if isinstance(lit, dict):
                                args_schema = lit
                        except Exception:
                            pass

            if name is None:
                # positional string literal
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    name = str(node.args[0].value).strip()
            if not name:
                continue

            snippet = _snippet_from_source(content, node)
            confidence = 0.86 if explicit_schema else 0.82
            tags = ["langchain", "call", fn_name.lower()]
            cand = ToolCandidate(
                name=name,
                description=(desc or ""),
                source_repo=source_repo,
                source_path=path,
                tool_type="langchain_tool",
                execution_kind="python_function",
                args_schema=args_schema,
                risk_level="medium",
                tags=tags,
                confidence=confidence,
                promotion_reason=None,
                raw_snippet=snippet,
            )
            cand.capability_category = infer_capability_category(
                name=cand.name,
                description=cand.description,
                source_path=cand.source_path,
                tool_type=cand.tool_type,
                execution_kind=cand.execution_kind,
                tags=cand.tags,
            )
            out.append(cand.with_computed_fields())

    return out


def _iter_json_candidates(repo_files: RepoFiles) -> Iterable[Tuple[str, Any, str]]:
    for rf in repo_files:
        path = rf.get("path") or ""
        if not path.lower().endswith(".json"):
            continue
        content = rf.get("content") or ""
        try:
            obj = json.loads(content)
        except Exception:
            continue
        yield path, obj, content


def extractor_mcp(repo_files: RepoFiles, source_repo: str) -> List[ToolCandidate]:
    out: List[ToolCandidate] = []

    for path, obj, raw in _iter_json_candidates(repo_files):
        p = path.lower()
        if "mcp" not in p and not p.endswith("mcp.json") and not p.endswith("mcp.config.json"):
            continue
        if not isinstance(obj, dict):
            continue

        tools = obj.get("tools")
        if not isinstance(tools, list):
            continue

        for t in tools:
            if not isinstance(t, dict):
                continue
            name = t.get("name") or t.get("tool") or t.get("id")
            if not isinstance(name, str) or not name.strip():
                continue
            name = name.strip()
            desc = t.get("description") or t.get("desc") or ""
            if not isinstance(desc, str):
                desc = ""
            schema = t.get("input_schema") or t.get("inputSchema") or t.get("schema") or t.get("args_schema")
            args_schema = default_args_schema(allow_additional=True)
            explicit_schema = False
            if isinstance(schema, dict) and schema:
                args_schema = schema
                explicit_schema = True
            confidence = 0.95 if explicit_schema else 0.85
            tags = ["mcp", "manifest"]
            if explicit_schema:
                tags.append("explicit_schema")
            cand = ToolCandidate(
                name=name,
                description=desc.strip(),
                source_repo=source_repo,
                source_path=path,
                tool_type="mcp_tool",
                execution_kind="mcp_server_tool",
                args_schema=args_schema,
                risk_level="medium",
                tags=tags,
                confidence=confidence,
                raw_snippet=raw if len(raw) <= 8000 else raw[:8000],
            )
            cand.capability_category = infer_capability_category(
                name=cand.name,
                description=cand.description,
                source_path=cand.source_path,
                tool_type=cand.tool_type,
                execution_kind=cand.execution_kind,
                tags=cand.tags,
            )
            out.append(cand.with_computed_fields())

    # Heuristic code-based MCP patterns (low confidence)
    mcp_pattern = re.compile(r"\.tool\(\s*(?P<q>['\"])(?P<name>[^'\"]+)(?P=q)\s*\)")
    for rf in repo_files:
        path = rf.get("path") or ""
        if not path.endswith(".py"):
            continue
        content = rf.get("content") or ""
        if "mcp" not in content.lower():
            continue
        for m in mcp_pattern.finditer(content):
            name = m.group("name").strip()
            if not name:
                continue
            cand = ToolCandidate(
                name=name,
                description="",
                source_repo=source_repo,
                source_path=path,
                tool_type="mcp_tool",
                execution_kind="mcp_server_tool",
                args_schema=default_args_schema(allow_additional=True),
                risk_level="medium",
                tags=["mcp", "heuristic"],
                confidence=0.75,
                raw_snippet=content[max(0, m.start() - 200) : m.end() + 200],
            )
            cand.capability_category = infer_capability_category(
                name=cand.name,
                description=cand.description,
                source_path=cand.source_path,
                tool_type=cand.tool_type,
                execution_kind=cand.execution_kind,
                tags=cand.tags,
            )
            out.append(cand.with_computed_fields())

    return out


_MAKE_TARGET_RE = re.compile(r"^(?P<target>[A-Za-z0-9][A-Za-z0-9_.-]*):")


def _extract_make_targets(content: str) -> List[str]:
    targets: List[str] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _MAKE_TARGET_RE.match(line)
        if not m:
            continue
        t = m.group("target")
        if t in (".PHONY",):
            continue
        if "%" in t:
            continue
        if t.startswith("."):
            continue
        targets.append(t)
    return targets


def _extract_fastapi_routes(content: str) -> List[Tuple[str, str]]:
    """
    Return list of (method, path) for obvious FastAPI-style decorators:
      @app.get("/x") / @router.post("/y")
    """
    routes: List[Tuple[str, str]] = []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return routes
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list or []:
            if not isinstance(dec, ast.Call):
                continue
            if not isinstance(dec.func, ast.Attribute):
                continue
            method = dec.func.attr.lower()
            if method not in ("get", "post", "put", "patch", "delete", "options", "head"):
                continue
            if not dec.args:
                continue
            if isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
                path = dec.args[0].value
                routes.append((method, path))
    return routes


def _schema_for_route(method: str, route_path: str) -> Dict[str, Any]:
    # Very small V1 schema: only path params like /items/{id}
    schema = default_args_schema(allow_additional=False)
    props: Dict[str, Any] = {
        "method": {"type": "string", "enum": [method.upper()]},
        "path": {"type": "string", "enum": [route_path]},
    }
    required = ["method", "path"]
    for param in re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", route_path):
        props[param] = {"type": "string"}
        required.append(param)
    schema["properties"] = props
    schema["required"] = required
    schema["additionalProperties"] = False
    return schema


def extractor_generic(repo_files: RepoFiles, source_repo: str) -> List[ToolCandidate]:
    out: List[ToolCandidate] = []

    for rf in repo_files:
        path = rf.get("path") or ""
        content = rf.get("content") or ""

        # Makefiles
        if path.endswith("Makefile") or path.lower().endswith(".mk"):
            for tgt in _extract_make_targets(content):
                cand = ToolCandidate(
                    name=f"make_{tgt}",
                    description=f"Make target '{tgt}'",
                    source_repo=source_repo,
                    source_path=path,
                    tool_type="make_target",
                    execution_kind="cli_command",
                    args_schema=default_args_schema(allow_additional=True),
                    risk_level="medium",
                    tags=["make", "cli"],
                    confidence=0.7,
                    raw_snippet="\n".join(content.splitlines()[:200]),
                )
                cand.capability_category = infer_capability_category(
                    name=cand.name,
                    description=cand.description,
                    source_path=cand.source_path,
                    tool_type=cand.tool_type,
                    execution_kind=cand.execution_kind,
                    tags=cand.tags,
                )
                out.append(cand.with_computed_fields())
            continue

        # CLI scripts via shebang
        if content.startswith("#!") and ("/python" in content.splitlines()[0] or "/bash" in content.splitlines()[0]):
            name = path.split("/")[-1]
            cand = ToolCandidate(
                name=name,
                description="CLI script",
                source_repo=source_repo,
                source_path=path,
                tool_type="cli",
                execution_kind="cli_command",
                args_schema=default_args_schema(allow_additional=True),
                risk_level="high",
                tags=["cli", "script"],
                confidence=0.65,
                raw_snippet="\n".join(content.splitlines()[:200]),
            )
            cand.capability_category = infer_capability_category(
                name=cand.name,
                description=cand.description,
                source_path=cand.source_path,
                tool_type=cand.tool_type,
                execution_kind=cand.execution_kind,
                tags=cand.tags,
            )
            out.append(cand.with_computed_fields())

        # FastAPI-style routes (stage; conservative promotion later)
        if path.endswith(".py") and ("fastapi" in content.lower() or "@app." in content or "@router." in content):
            for method, route_path in _extract_fastapi_routes(content):
                schema = _schema_for_route(method, route_path)
                name = f"{method}_{route_path.strip('/').replace('/', '_').replace('{', '').replace('}', '') or 'root'}"
                cand = ToolCandidate(
                    name=name,
                    description=f"HTTP route {method.upper()} {route_path}",
                    source_repo=source_repo,
                    source_path=path,
                    tool_type="api_route",
                    execution_kind="http_request",
                    args_schema=schema,
                    risk_level="medium",
                    tags=["api", "http", "route"],
                    confidence=0.75,
                    raw_snippet="\n".join(content.splitlines()[:240]),
                )
                cand.capability_category = infer_capability_category(
                    name=cand.name,
                    description=cand.description,
                    source_path=cand.source_path,
                    tool_type=cand.tool_type,
                    execution_kind=cand.execution_kind,
                    tags=cand.tags,
                )
                out.append(cand.with_computed_fields())

    # Ensure all outputs have valid category (defensive)
    final: List[ToolCandidate] = []
    for c in out:
        if c.capability_category not in CAPABILITY_CATEGORIES:
            c = c.model_copy(update={"capability_category": "code_execution"}).with_computed_fields()
        final.append(c)
    return final

