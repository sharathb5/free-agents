"""
Validation/grading for repo-to-agent pipeline output.

Evaluates a single RepoToAgentResult against contract and basic quality
expectations. Does not modify the result; only inspects and classifies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from app.catalog.loader import CatalogError, load_bundles_catalog, load_tools_catalog
from app.repo_to_agent.models import RepoToAgentResult
from app.repo_to_agent.repo_tool_wrapper import RECOGNIZED_WRAPPER_KINDS

# Repo-specific path signals: (owner, repo) -> substrings we expect to see in important_files or key_paths.
# Used only for known validation repos; warnings (not errors) when output looks too generic.
_REPO_SIGNALS: Dict[Tuple[str, str], List[str]] = {
    ("psf", "requests"): [
        "pyproject.toml",
        "requests/api",
        "requests/adapters",
        "requests/sessions",
    ],
    ("encode", "httpx"): [
        "pyproject.toml",
        "httpx/_client",
        "httpx/_main",
        "requirements.txt",
    ],
    ("pallets", "flask"): [
        "flask/app.py",
        "flask/cli.py",
        "pyproject.toml",
        "flask/__main__.py",
    ],
}
_MIN_REPO_SIGNAL_MATCHES = 2  # Require at least this many signals present to avoid warning


@dataclass(frozen=True)
class ValidationResult:
    """Result of validating a single repo-to-agent output."""

    status: str  # "pass" | "pass_with_warnings" | "fail"
    errors: List[str]
    warnings: List[str]


def _allowed_bundle_ids() -> Set[str]:
    """Return set of bundle_id values from the bundles catalog."""
    catalog = load_bundles_catalog()
    out: Set[str] = set()
    for b in catalog.get("bundles") or []:
        if isinstance(b, dict):
            bid = b.get("bundle_id")
            if isinstance(bid, str) and bid.strip():
                out.add(bid.strip())
    return out


def _allowed_tool_ids() -> Set[str]:
    """Return set of tool_id values from the tools catalog. Raises CatalogError if catalog cannot be loaded."""
    catalog = load_tools_catalog()
    out: Set[str] = set()
    for t in catalog.get("tools") or []:
        if isinstance(t, dict):
            tid = t.get("tool_id")
            if isinstance(tid, str) and tid.strip():
                out.add(tid.strip())
    return out


def _check_required_non_empty_string(value: Any, field_name: str) -> List[str]:
    errors = []
    if not isinstance(value, str):
        errors.append(f"{field_name}: must be a string")
    elif not value.strip():
        errors.append(f"{field_name}: must be non-empty")
    return errors


def _check_eval_case(case: Any, index: int) -> List[str]:
    errors = []
    if not isinstance(case, dict):
        errors.append(f"starter_eval_cases[{index}]: must be an object")
        return errors
    name = case.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append(f"starter_eval_cases[{index}]: missing or empty 'name'")
    inp = case.get("input")
    if inp is None:
        errors.append(f"starter_eval_cases[{index}]: missing 'input'")
    elif isinstance(inp, str):
        if not inp.strip():
            errors.append(f"starter_eval_cases[{index}]: 'input' must be non-empty when a string")
    elif not isinstance(inp, dict):
        errors.append(f"starter_eval_cases[{index}]: 'input' must be an object or a string")
    if "expected" not in case:
        errors.append(f"starter_eval_cases[{index}]: missing 'expected'")
    return errors


def _get_attr(obj: Any, key: str) -> Any:
    """Get attribute from dict or Pydantic model."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _check_wrapped_tools(
    wrapped_repo_tools: List[Any],
    discovered_source_paths: Set[str],
) -> List[str]:
    """Validate wrapped_repo_tools: risk_level, wrapper_kind, args_schema, safe_to_auto_expose rules."""
    errors: List[str] = []
    valid_risk = {"low", "medium", "high"}
    for i, w in enumerate(wrapped_repo_tools):
        if not isinstance(w, (dict, type(None))) and not hasattr(w, "model_dump"):
            errors.append(f"wrapped_repo_tools[{i}]: must be an object")
            continue
        if w is None:
            errors.append(f"wrapped_repo_tools[{i}]: must be an object")
            continue
        prefix = f"wrapped_repo_tools[{i}]"
        source_path = (_get_attr(w, "source_path") or "").strip() if w else ""
        if not source_path:
            errors.append(f"{prefix}: source_path must be non-empty")
        risk = (str(_get_attr(w, "risk_level") or "").strip().lower()) if w else ""
        if risk not in valid_risk:
            errors.append(f"{prefix}: risk_level must be one of low, medium, high (got {risk!r})")
        wrapper_kind = (str(_get_attr(w, "wrapper_kind") or "").strip()) if w else ""
        if wrapper_kind not in RECOGNIZED_WRAPPER_KINDS:
            errors.append(f"{prefix}: wrapper_kind must be one of {sorted(RECOGNIZED_WRAPPER_KINDS)} (got {wrapper_kind!r})")
        args_schema = _get_attr(w, "args_schema") if w else None
        if args_schema is None:
            errors.append(f"{prefix}: args_schema must be present")
        elif not isinstance(args_schema, dict):
            errors.append(f"{prefix}: args_schema must be an object")
        safe = _get_attr(w, "safe_to_auto_expose") if w else False
        if risk == "high" and safe is True:
            errors.append(f"{prefix}: high-risk tools must not be marked safe_to_auto_expose=True")
    return errors


def _check_repo_sanity(
    result: RepoToAgentResult,
    owner: str,
    repo: str,
    warnings: List[str],
) -> None:
    """If (owner, repo) is a known validation repo, warn when paths lack expected repo-specific signals."""
    key = (owner.strip().lower(), repo.strip().lower())
    if key not in _REPO_SIGNALS:
        return
    signals = _REPO_SIGNALS[key]
    paths: List[str] = list(result.important_files or [])
    if result.architecture and isinstance(getattr(result.architecture, "key_paths", None), list):
        paths.extend(result.architecture.key_paths)
    matches = sum(1 for sig in signals if any(sig in p for p in paths))
    if matches < _MIN_REPO_SIGNAL_MATCHES:
        sample = ", ".join(signals[:3])
        warnings.append(
            f"Repo {owner}/{repo}: expected more repo-specific paths in important_files/key_paths "
            f"(e.g. {sample}); found {matches} matching."
        )


def validate_repo_to_agent_result(
    result: RepoToAgentResult,
    *,
    owner: Optional[str] = None,
    repo: Optional[str] = None,
) -> ValidationResult:
    """
    Validate a single repo-to-agent result. Returns status, errors, and warnings.

    - fail: any required-field or contract check failed.
    - pass_with_warnings: no errors, but one or more warnings.
    - pass: no errors and no warnings.

    If owner and repo are provided and match a known validation repo (e.g. psf/requests),
    adds optional warnings when important_files/key_paths lack expected repo-specific signals.
    """
    errors: List[str] = []
    warnings: List[str] = []

    # Required / non-empty fields
    errors.extend(_check_required_non_empty_string(result.repo_summary, "repo_summary"))

    if not isinstance(result.important_files, list):
        errors.append("important_files: must be a list")
    elif len(result.important_files) == 0:
        errors.append("important_files: must be non-empty")
    else:
        for i, path in enumerate(result.important_files):
            if not isinstance(path, str) or not path.strip():
                errors.append(f"important_files[{i}]: must be a non-empty string")

    if not hasattr(result, "architecture") or result.architecture is None:
        errors.append("architecture: must be present")
    else:
        arch = result.architecture
        if not isinstance(getattr(arch, "languages", None), list):
            errors.append("architecture.languages: must be a list")
        if not isinstance(getattr(arch, "key_paths", None), list):
            errors.append("architecture.key_paths: must be a list")

    errors.extend(
        _check_required_non_empty_string(result.recommended_bundle, "recommended_bundle")
    )
    if result.recommended_bundle and result.recommended_bundle.strip():
        allowed = _allowed_bundle_ids()
        if result.recommended_bundle.strip() not in allowed:
            errors.append(
                f"recommended_bundle: '{result.recommended_bundle}' is not in the bundles catalog"
            )

    spec: Dict[str, Any] = result.draft_agent_spec or {}
    if not isinstance(spec, dict):
        errors.append("draft_agent_spec: must be an object")
    else:
        name = spec.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append("draft_agent_spec: must have non-empty 'name'")
        desc = spec.get("description")
        if not isinstance(desc, str) or not desc.strip():
            errors.append("draft_agent_spec: must have non-empty 'description'")

    if not isinstance(result.starter_eval_cases, list):
        errors.append("starter_eval_cases: must be a list")
    elif len(result.starter_eval_cases) == 0:
        errors.append("starter_eval_cases: must be non-empty")
    else:
        for i, case in enumerate(result.starter_eval_cases):
            errors.extend(_check_eval_case(case, i))

    # recommended_additional_tools: must be list of non-empty strings, each a valid catalog tool_id
    if not isinstance(result.recommended_additional_tools, list):
        errors.append("recommended_additional_tools: must be a list")
    else:
        tool_ids_to_check: List[str] = []
        for i, item in enumerate(result.recommended_additional_tools):
            if not isinstance(item, str):
                errors.append(f"recommended_additional_tools[{i}]: must be a string")
            elif not item.strip():
                errors.append(f"recommended_additional_tools[{i}]: must be non-empty")
            else:
                tool_ids_to_check.append(item.strip())
        if tool_ids_to_check:
            try:
                allowed = _allowed_tool_ids()
                not_in_catalog = [tid for tid in tool_ids_to_check if tid not in allowed]
                if not_in_catalog:
                    errors.append(
                        f"recommended_additional_tools: tool IDs not in catalog: {not_in_catalog}"
                    )
            except CatalogError:
                errors.append(
                    "recommended_additional_tools: tool catalog unavailable; cannot validate tool IDs"
                )

    # wrapped_repo_tools: optional list; if present validate each entry
    discovered_source_paths: Set[str] = set()
    if hasattr(result, "discovered_repo_tools") and result.discovered_repo_tools:
        for t in result.discovered_repo_tools:
            path = getattr(t, "source_path", None) or (t.get("source_path") if isinstance(t, dict) else None)
            if isinstance(path, str) and path.strip():
                discovered_source_paths.add(path.strip())
    if hasattr(result, "wrapped_repo_tools") and result.wrapped_repo_tools is not None:
        errors.extend(
            _check_wrapped_tools(
                result.wrapped_repo_tools,
                discovered_source_paths,
            )
        )

    # Repo-specific sanity: warn when known-repo output has few expected path signals (warnings only)
    if owner and repo and not errors:
        _check_repo_sanity(result, owner, repo, warnings)

    if errors:
        status = "fail"
    elif warnings:
        status = "pass_with_warnings"
    else:
        status = "pass"

    return ValidationResult(status=status, errors=errors, warnings=warnings)
