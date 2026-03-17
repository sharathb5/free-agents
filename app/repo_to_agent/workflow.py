from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from app.catalog.loader import CatalogError, load_bundles_catalog, load_tools_catalog

from .models import (
    AgentDraftOutput,
    AgentReviewOutput,
    DiscoveredRepoTool,
    RepoArchitectureOutput,
    RepoScoutOutput,
    RepoToAgentResult,
    RunTelemetry,
    StepTelemetry,
    WrappedRepoTool,
)
from .repo_tool_wrapper import wrap_discovered_tools
from .code_tool_discovery import discover_code_defined_tools, merge_discovered_tools
from .templates import (
    AGENT_DESIGNER_TEMPLATE,
    AGENT_REVIEWER_TEMPLATE,
    CODE_TOOL_DISCOVERY_TEMPLATE,
    REPO_ARCHITECT_TEMPLATE,
    REPO_SCOUT_TEMPLATE,
    REPO_TOOL_DISCOVERY_TEMPLATE,
    AgentTemplate,
)

logger = logging.getLogger(__name__)


@dataclass
class RepoWorkflowPlan:
    """
    Declarative plan for the repo-to-agent workflow.

    This captures the normalized repo coordinates and the ordered list of
    specialist step identifiers to run. It is intentionally execution- and
    SDK-agnostic.
    """

    owner: str
    repo: str
    ref: Optional[str] = None
    url: Optional[str] = None
    steps: List[str] = field(default_factory=list)


def _parse_github_url(url: str) -> Dict[str, Optional[str]]:
    """
    Best-effort extraction of owner/repo from a GitHub URL.

    Supports URLs like:
      - https://github.com/owner/repo
      - https://github.com/owner/repo.git
      - https://github.com/owner/repo/tree/branch
    """
    parsed = urlparse(url)
    if not parsed.netloc or "github.com" not in parsed.netloc:
        return {"owner": None, "repo": None}
    # Strip leading slash and split path segments
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2:
        return {"owner": None, "repo": None}
    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    return {"owner": owner or None, "repo": repo or None}


def build_repo_workflow(repo_input: Dict[str, Any]) -> RepoWorkflowPlan:
    """
    Normalize repo input and return an ordered workflow plan.

    Accepted input keys:
      - owner: GitHub owner/org/user (required if url not provided)
      - repo: GitHub repository name (required if url not provided)
      - ref: optional git ref (branch, tag, or SHA)
      - url: optional GitHub URL; owner/repo may be derived from this when omitted

    This function does not execute any tools or SDK calls.
    """
    if not isinstance(repo_input, dict):
        raise TypeError("repo_input must be a dict")

    owner = repo_input.get("owner")
    repo = repo_input.get("repo")
    ref = repo_input.get("ref")
    url = repo_input.get("url")

    if url and (not owner or not repo):
        parsed = _parse_github_url(str(url))
        owner = owner or parsed.get("owner")
        repo = repo or parsed.get("repo")

    if not isinstance(owner, str) or not owner.strip():
        raise ValueError("owner is required (or must be derivable from url)")
    if not isinstance(repo, str) or not repo.strip():
        raise ValueError("repo is required (or must be derivable from url)")

    owner = owner.strip()
    repo = repo.strip()
    ref = str(ref).strip() if isinstance(ref, str) and ref.strip() else None
    url_str = str(url).strip() if isinstance(url, str) and url.strip() else None

    steps = [
        "repo_scout",
        "repo_architect",
        "repo_tool_discovery",
        "code_tool_discovery",
        "repo_tool_wrapper",
        "agent_designer",
        "agent_reviewer",
    ]

    return RepoWorkflowPlan(
        owner=owner,
        repo=repo,
        ref=ref,
        url=url_str,
        steps=steps,
    )


def is_large_repo(
    scout: RepoScoutOutput,
    arch: RepoArchitectureOutput | None = None,
) -> bool:
    """
    Heuristic to flag large/wide repos for routing and telemetry.

    Inputs are derived from the validated scout/architect outputs so callers can
    reuse this in routing decisions or observability without duplicating logic.
    """
    important_files_count = len(scout.important_files or [])
    language_hints_count = len(scout.language_hints or [])
    framework_hints_count = len(scout.framework_hints or [])
    key_paths_count = len(arch.key_paths) if arch is not None and arch.key_paths is not None else 0

    return (
        important_files_count > 200
        or key_paths_count > 150
        or language_hints_count > 5
        or framework_hints_count > 5
    )


def run_repo_to_agent_workflow(
    plan: RepoWorkflowPlan,
    runner: Callable[..., Dict[str, Any] | tuple[Dict[str, Any], list]],
) -> RepoToAgentResult:
    """
    Execute the repo-to-agent workflow using the provided runner.

    The runner is responsible for executing a single specialist template:
        runner(template, input_payload, step_telemetry=None) -> dict | (dict, list)

    Execution order (fixed):
      1. repo_scout
      2. repo_architect
      3. agent_designer
      4. agent_reviewer

    This function is SDK-agnostic and does not call any tools directly.
    It validates each specialist's output against the corresponding
    Pydantic model and aggregates into RepoToAgentResult.
    """
    if not callable(runner):
        raise TypeError("runner must be callable")

    t0 = time.monotonic()
    steps_list: List[StepTelemetry] = []
    repo_size_hint: Dict[str, Any] = {}

    base_input: Dict[str, Any] = {
        "owner": plan.owner,
        "repo": plan.repo,
    }
    if plan.ref:
        base_input["ref"] = plan.ref

    fallback_notes: List[str] = []

    def _unpack(raw: Any) -> Dict[str, Any]:
        """If runner returned (data, extra_notes), collect notes and return data."""
        if isinstance(raw, tuple) and len(raw) == 2:
            data, notes = raw
            if isinstance(notes, list):
                fallback_notes.extend(notes)
            return data
        return raw

    def _run_step(template: AgentTemplate, input_payload: Dict[str, Any]) -> Dict[str, Any]:
        step_telemetry: Dict[str, Any] = {
            "step_name": template.id,
            "backend_used": "internal",
            "fallback_triggered": False,
            "tool_calls_count": None,
            "duration_ms": 0,
        }
        step_start = time.monotonic()
        raw = runner(template, input_payload, step_telemetry)
        step_telemetry["duration_ms"] = int((time.monotonic() - step_start) * 1000)
        steps_list.append(StepTelemetry(**step_telemetry))
        return _unpack(raw)

    # 1. repo_scout
    scout_input: Dict[str, Any] = dict(base_input)
    scout_raw = _run_step(REPO_SCOUT_TEMPLATE, scout_input)
    scout_output = RepoScoutOutput.model_validate(scout_raw)
    repo_size_hint["important_files_count"] = len(scout_output.important_files)
    repo_size_hint["language_hints_count"] = len(scout_output.language_hints)
    repo_size_hint["framework_hints_count"] = len(scout_output.framework_hints)

    # 2. repo_architect (repo coords + scout output)
    architect_input: Dict[str, Any] = dict(base_input)
    architect_input["scout_summary"] = scout_output.model_dump()
    architect_raw = _run_step(REPO_ARCHITECT_TEMPLATE, architect_input)
    architect_output = RepoArchitectureOutput.model_validate(architect_raw)
    repo_size_hint["key_paths_count"] = len(architect_output.key_paths)

    # 3. repo_tool_discovery (deterministic; runner returns discovered_tools)
    discovery_input: Dict[str, Any] = dict(base_input)
    discovery_input["scout"] = scout_output.model_dump()
    discovery_input["architecture"] = architect_output.model_dump()
    discovery_raw = _run_step(REPO_TOOL_DISCOVERY_TEMPLATE, discovery_input)
    discovered_tools_raw = discovery_raw.get("discovered_tools") or []
    manifest_tools = [DiscoveredRepoTool.model_validate(t) for t in discovered_tools_raw]

    # 4. code_tool_discovery (deterministic; runner fetches source paths and returns code_tools)
    code_discovery_raw = _run_step(CODE_TOOL_DISCOVERY_TEMPLATE, discovery_input)
    code_tools_raw = code_discovery_raw.get("code_tools") or []
    code_tools = [DiscoveredRepoTool.model_validate(t) for t in code_tools_raw]
    discovered_repo_tools = merge_discovered_tools(manifest_tools, code_tools)

    # 5. repo_tool_wrapper (deterministic; in-process; no runner call)
    wrapped_repo_tools: List[WrappedRepoTool] = wrap_discovered_tools(discovered_repo_tools)

    # 6. agent_designer (repo coords + scout + architecture + discovered + wrapped tools for awareness only)
    designer_input: Dict[str, Any] = dict(base_input)
    designer_input["scout"] = scout_output.model_dump()
    designer_input["architecture"] = architect_output.model_dump()
    designer_input["discovered_repo_tools"] = [t.model_dump() for t in discovered_repo_tools]
    designer_input["wrapped_repo_tools"] = [t.model_dump() for t in wrapped_repo_tools]
    draft_raw = _run_step(AGENT_DESIGNER_TEMPLATE, designer_input)
    draft_output = AgentDraftOutput.model_validate(draft_raw)

    # Normalize recommended_bundle to a valid bundle_id from the real catalog.
    # Prompting should keep this valid, but we add this lightweight guardrail so
    # invalid free-form bundle names don't propagate downstream.
    normalized_note: str | None = None
    try:
        bundles_catalog = load_bundles_catalog()
        allowed_bundle_ids = {
            b.get("bundle_id").strip()
            for b in (bundles_catalog.get("bundles") or [])
            if isinstance(b, dict)
            and isinstance(b.get("bundle_id"), str)
            and b.get("bundle_id").strip()
        }
    except CatalogError:
        allowed_bundle_ids = set()
        bundles_catalog = {}

    recommended_bundle_raw = (draft_output.recommended_bundle or "").strip()
    if allowed_bundle_ids and recommended_bundle_raw not in allowed_bundle_ids:
        fallback = "repo_to_agent" if "repo_to_agent" in allowed_bundle_ids else "no_tools_writer"
        normalized_note = (
            f"Normalized recommended_bundle from {recommended_bundle_raw!r} to {fallback!r} "
            f"(not found in bundles catalog)."
        )
        draft_output = draft_output.model_copy(update={"recommended_bundle": fallback})

    # Filter recommended_additional_tools: only allow catalog tool_ids and remove
    # tools already in the selected bundle. Append a review_note if anything was removed.
    tools_filter_note: str | None = None
    try:
        tools_catalog = load_tools_catalog()
        allowed_tool_ids = {
            t.get("tool_id").strip()
            for t in (tools_catalog.get("tools") or [])
            if isinstance(t, dict) and isinstance(t.get("tool_id"), str) and t.get("tool_id").strip()
        }
    except CatalogError:
        allowed_tool_ids = set()

    if allowed_tool_ids:
        bundle_tools: set[str] = set()
        for b in (bundles_catalog.get("bundles") or []):
            if isinstance(b, dict) and b.get("bundle_id") == draft_output.recommended_bundle:
                bundle_tools = set(b.get("tools") or [])
                break

        raw_tools = draft_output.recommended_additional_tools or []
        invalid = [t for t in raw_tools if isinstance(t, str) and t.strip() and t.strip() not in allowed_tool_ids]
        redundant = [
            t for t in raw_tools
            if isinstance(t, str) and t.strip() and t.strip() in allowed_tool_ids and t.strip() in bundle_tools
        ]
        valid_ordered = [
            t.strip()
            for t in raw_tools
            if isinstance(t, str) and t.strip() and t.strip() in allowed_tool_ids and t.strip() not in bundle_tools
        ]

        if invalid or redundant:
            parts = []
            if invalid:
                parts.append(f"Removed invalid tool IDs: {invalid}")
            if redundant:
                parts.append(f"Removed redundant tools already in bundle: {redundant}")
            tools_filter_note = " ".join(parts)
            draft_output = draft_output.model_copy(update={"recommended_additional_tools": valid_ordered})

    # 7. agent_reviewer (repo coords + scout + architecture + draft)
    reviewer_input: Dict[str, Any] = dict(base_input)
    reviewer_input["scout"] = scout_output.model_dump()
    reviewer_input["architecture"] = architect_output.model_dump()
    reviewer_input["draft"] = draft_output.model_dump()
    review_raw = _run_step(AGENT_REVIEWER_TEMPLATE, reviewer_input)
    review_output = AgentReviewOutput.model_validate(review_raw)

    total_duration_ms = int((time.monotonic() - t0) * 1000)
    run_telemetry = RunTelemetry(
        steps=steps_list,
        repo_size_hint=repo_size_hint,
        total_duration_ms=total_duration_ms,
    )
    logger.info(
        "repo_to_agent_telemetry",
        extra={"telemetry": run_telemetry.model_dump()},
    )

    # Aggregate into RepoToAgentResult
    review_notes = list(review_output.review_notes or [])
    review_notes.extend(fallback_notes)
    if normalized_note:
        review_notes.append(normalized_note)
    if tools_filter_note:
        review_notes.append(tools_filter_note)
    return RepoToAgentResult(
        repo_summary=scout_output.repo_summary,
        architecture=architect_output,
        important_files=scout_output.important_files,
        recommended_bundle=draft_output.recommended_bundle,
        recommended_additional_tools=draft_output.recommended_additional_tools,
        draft_agent_spec=draft_output.draft_agent_spec,
        starter_eval_cases=draft_output.starter_eval_cases,
        review_notes=review_notes,
        discovered_repo_tools=discovered_repo_tools,
        wrapped_repo_tools=wrapped_repo_tools,
        discovered_manifest_tools=manifest_tools,
        discovered_code_tools=code_tools,
        telemetry=run_telemetry,
    )


