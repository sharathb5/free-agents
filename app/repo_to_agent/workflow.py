from __future__ import annotations

import logging
import json
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
from .canonical_agent_id import canonical_agent_id_from_repo, deterministic_import_version
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

_DEBUG_LOG_PATH = "/Users/sharath/agent-toolbox/agent-toolbox/.cursor/debug-db76a9.log"


def _debug_log(*, hypothesis_id: str, location: str, message: str, data: Dict[str, Any] | None = None, run_id: str = "pre-fix") -> None:
    # #region agent log
    try:
        payload: Dict[str, Any] = {
            "sessionId": "db76a9",
            "timestamp": int(time.time() * 1000),
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion agent log


def _safe_trim(s: Any, max_len: int = 200) -> str:
    out = str(s or "")
    return out[:max_len]


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
    _debug_log(
        hypothesis_id="H5",
        location="app/repo_to_agent/workflow.py:repo_scout",
        message="Repo scout output",
        data={
            "stage": "scout",
            "important_files_count": len(scout_output.important_files),
            "important_files": scout_output.important_files[:20],
            "repo_summary_head": _safe_trim(scout_output.repo_summary, 180),
        },
    )
    repo_size_hint["important_files_count"] = len(scout_output.important_files)
    repo_size_hint["language_hints_count"] = len(scout_output.language_hints)
    repo_size_hint["framework_hints_count"] = len(scout_output.framework_hints)

    # 2. repo_architect (repo coords + scout output)
    architect_input: Dict[str, Any] = dict(base_input)
    architect_input["scout_summary"] = scout_output.model_dump()
    architect_raw = _run_step(REPO_ARCHITECT_TEMPLATE, architect_input)
    architect_output = RepoArchitectureOutput.model_validate(architect_raw)
    _debug_log(
        hypothesis_id="H5",
        location="app/repo_to_agent/workflow.py:repo_architect",
        message="Repo architect output",
        data={
            "stage": "architect",
            "key_paths_count": len(architect_output.key_paths),
            "key_paths": architect_output.key_paths[:30],
            "entrypoints": architect_output.entrypoints[:10],
        },
    )
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
    _debug_log(
        hypothesis_id="H7",
        location="app/repo_to_agent/workflow.py:discovery_merge",
        message="Discovery merge result",
        data={
            "stage": "discovery_merge",
            "manifest_tools_count": len(manifest_tools),
            "manifest_tools": [{"name": t.name, "tool_type": t.tool_type, "source_path": t.source_path} for t in manifest_tools],
            "code_tools_count": len(code_tools),
            "code_tools": [{"name": t.name, "tool_type": t.tool_type, "source_path": t.source_path} for t in code_tools],
            "discovered_repo_tools_count": len(discovered_repo_tools),
            "discovered_repo_tools": [{"name": t.name, "tool_type": t.tool_type, "source_path": t.source_path} for t in discovered_repo_tools],
        },
    )

    # 5. repo_tool_wrapper (deterministic; in-process; no runner call)
    wrapped_repo_tools: List[WrappedRepoTool] = wrap_discovered_tools(discovered_repo_tools)

    # 5b. Contract import (deterministic): if repo contains agent.json and/or prompts/system_prompt.md,
    # treat them as authoritative for id/name/description/prompt/tags/schemas (instead of overfitting to repo code paths).
    contract_overrides: Dict[str, Any] = {}
    contract_notes: List[str] = []
    agent_obj: Dict[str, Any] = {}
    contract_bundle_override: Optional[str] = None
    contract_tools_override: Optional[List[str]] = None
    try:
        from app.preset_loader import Preset
        from app.runtime.tools.registry import DefaultToolRegistry, build_run_context

        preset = Preset(
            id="repo_contract_import",
            version="internal",
            name="repo_contract_import",
            description="Deterministic contract importer (agent.json + prompts).",
            primitive="repo_contract_import",
            input_schema={"type": "object", "properties": {}, "additionalProperties": True},
            output_schema={"type": "object", "properties": {}, "additionalProperties": True},
            prompt="",
            supports_memory=False,
            memory_policy=None,
            allowed_tools=["github_repo_read"],
            http_allowed_domains=None,
            tool_policies={"github_repo_read": {"max_entries": 200, "max_file_chars": 20_000}},
            resolved_execution_limits={"max_tool_calls": 12},
        )
        run_context = build_run_context(run_id=f"repo_contract_import_{plan.owner}_{plan.repo}", preset=preset)
        registry = DefaultToolRegistry()

        def _read_file(path: str) -> str:
            out = registry.execute(
                "github_repo_read",
                {"owner": plan.owner, "repo": plan.repo, "mode": "file", "path": path, **({"ref": plan.ref} if plan.ref else {})},
                run_context,
            )
            content = out.get("content") or ""
            return content if isinstance(content, str) else ""

        agent_json_text = _read_file("agent.json")
        system_prompt_text = _read_file("prompts/system_prompt.md")
        contract_notes.append(f"contract_import: agent.json bytes={len(agent_json_text)} prompt bytes={len(system_prompt_text)}")
        agent_obj: Dict[str, Any] = {}
        if agent_json_text.strip():
            try:
                parsed = json.loads(agent_json_text)
                if isinstance(parsed, dict):
                    agent_obj = parsed
            except Exception as exc:
                contract_notes.append(f"contract_import: agent.json parse failed: {type(exc).__name__}")
        if agent_obj:
            # Map agent.json fields into our draft_agent_spec shape.
            if isinstance(agent_obj.get("id"), str) and agent_obj["id"].strip():
                contract_overrides["id"] = agent_obj["id"].strip()
            if isinstance(agent_obj.get("name"), str) and agent_obj["name"].strip():
                contract_overrides["name"] = agent_obj["name"].strip()
            if isinstance(agent_obj.get("description"), str) and agent_obj["description"].strip():
                contract_overrides["description"] = agent_obj["description"].strip()
            if isinstance(agent_obj.get("tags"), list):
                contract_overrides["tags"] = [str(t).strip() for t in agent_obj["tags"] if str(t).strip()]
            if isinstance(agent_obj.get("input_schema"), dict):
                contract_overrides["input_schema"] = agent_obj["input_schema"]
            if isinstance(agent_obj.get("output_schema"), dict):
                contract_overrides["output_schema"] = agent_obj["output_schema"]
            # Primitive mapping: pass through transform/extract/classify/structured_agent.
            prim = agent_obj.get("primitive")
            if isinstance(prim, str) and prim.strip():
                prim_raw = prim.strip()
                if prim_raw in {"transform", "extract", "classify", "structured_agent"}:
                    contract_overrides["primitive"] = prim_raw
                else:
                    contract_notes.append(f"contract_import: primitive {prim_raw!r} not supported; using transform")
                    contract_overrides["primitive"] = "transform"
        if system_prompt_text.strip():
            prompt_text = system_prompt_text.strip()
            if prompt_text.startswith("# "):
                first_nl = prompt_text.find("\n")
                if first_nl > 0 and "system prompt" in prompt_text[:first_nl].lower():
                    prompt_text = prompt_text[first_nl:].lstrip("\n")
            contract_overrides["prompt"] = prompt_text
        if isinstance(agent_obj.get("supports_memory"), bool):
            contract_overrides["supports_memory"] = agent_obj["supports_memory"]
        if isinstance(agent_obj.get("memory"), dict) and agent_obj["memory"]:
            mem = agent_obj["memory"]
            mode = str(mem.get("type") or "last_n").lower()
            if "summary" in mode or "buffer" in mode:
                mode = "last_n"
            contract_overrides["memory_policy"] = {
                "mode": mode,
                "max_messages": int(mem.get("max_items") or mem.get("max_messages") or 10),
                "max_chars": int(mem.get("max_chars") or 8000),
            }
    except Exception as exc:
        contract_notes.append(f"contract_import: skipped due to error: {type(exc).__name__}")

    if agent_obj:
        caps = agent_obj.get("capabilities") or []
        if isinstance(caps, list) and any(
            isinstance(c, str) and ("github" in c.lower() or "file" in c.lower() or "search" in c.lower() or "changelog" in c.lower())
            for c in caps
        ):
            contract_bundle_override = "github_reader"
            contract_notes.append("contract_import: bundle github_reader from agent.json capabilities")
        tool_ids = []
        for c in caps:
            if isinstance(c, str) and c.strip():
                tid = c.strip().replace("-", "_").replace(" ", "_")
                if tid in ("github_repo_read", "http_request"):
                    tool_ids.append(tid)
                elif "github" in tid.lower():
                    tool_ids.append("github_repo_read")
        if tool_ids:
            contract_tools_override = list(dict.fromkeys(tool_ids))

    _debug_log(
        hypothesis_id="H5",
        location="app/repo_to_agent/workflow.py:contract_import",
        message="Contract import attempt",
        data={
            "stage": "contract_import",
            "overrides_keys": sorted(list(contract_overrides.keys())),
            "notes": contract_notes[:5],
            "contract_bundle_override": contract_bundle_override,
            "contract_tools_override": contract_tools_override,
            "agent_json_capabilities": agent_obj.get("capabilities") if agent_obj else None,
            "agent_json_likely_tools": agent_obj.get("likely_tools") if agent_obj else None,
        },
    )

    # 6. agent_designer (repo coords + scout + architecture + discovered + wrapped tools for awareness only)
    designer_input: Dict[str, Any] = dict(base_input)
    designer_input["scout"] = scout_output.model_dump()
    designer_input["architecture"] = architect_output.model_dump()
    designer_input["discovered_repo_tools"] = [t.model_dump() for t in discovered_repo_tools]
    designer_input["wrapped_repo_tools"] = [t.model_dump() for t in wrapped_repo_tools]
    draft_raw = _run_step(AGENT_DESIGNER_TEMPLATE, designer_input)
    draft_output = AgentDraftOutput.model_validate(draft_raw)
    _debug_log(
        hypothesis_id="H5",
        location="app/repo_to_agent/workflow.py:agent_designer",
        message="Agent designer output (summary)",
        data={
            "recommended_bundle": draft_output.recommended_bundle,
            "recommended_additional_tools_count": len(draft_output.recommended_additional_tools or []),
            "draft_id": (draft_output.draft_agent_spec or {}).get("id"),
            "draft_name_head": _safe_trim((draft_output.draft_agent_spec or {}).get("name"), 80),
            "desc_head": _safe_trim((draft_output.draft_agent_spec or {}).get("description"), 140),
            "prompt_head": _safe_trim((draft_output.draft_agent_spec or {}).get("prompt"), 160),
        },
    )

    # Apply contract overrides (if any) so we don't overfit to implementation files.
    if contract_overrides and isinstance(draft_output.draft_agent_spec, dict):
        merged = dict(draft_output.draft_agent_spec)
        merged.update(contract_overrides)
        draft_output = draft_output.model_copy(update={"draft_agent_spec": merged})
        if contract_notes:
            fallback_notes.extend(contract_notes)
    if contract_bundle_override:
        draft_output = draft_output.model_copy(update={"recommended_bundle": contract_bundle_override})
    if contract_tools_override is not None:
        draft_output = draft_output.model_copy(update={"recommended_additional_tools": contract_tools_override})

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

    # Canonical registry id + deterministic version per repo coordinates so:
    # - Different repos never share the same agent id.
    # - Re-importing the same owner/repo yields the same (id, version) pair
    #   (register again → AGENT_VERSION_EXISTS; use preview/dry_run or bump version).
    try:
        if isinstance(draft_output.draft_agent_spec, dict):
            owner_key = str(plan.owner or "").strip() or "unknown_owner"
            repo_key = str(plan.repo or "").strip() or "unknown_repo"
            base_version = str(draft_output.draft_agent_spec.get("version") or "0.1.0").strip()
            new_version = deterministic_import_version(base_version, owner_key, repo_key)
            canonical_id = canonical_agent_id_from_repo(owner_key, repo_key)
            updated_spec = dict(draft_output.draft_agent_spec)
            updated_spec["version"] = new_version
            updated_spec["id"] = canonical_id
            draft_output = draft_output.model_copy(update={"draft_agent_spec": updated_spec})
    except Exception:
        # Non-fatal: if normalization fails, keep the designer output as-is.
        pass

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

    # When inspection failed (empty repo, HTTP 409, etc.), surface it clearly so the UI
    # does not present the fallback draft as if it came from the repo.
    if not discovered_repo_tools and not scout_output.important_files:
        summary_lower = (scout_output.repo_summary or "").lower()
        if "could not inspect" in summary_lower or "inspection error" in summary_lower or "no accessible" in summary_lower:
            review_notes.append(
                "Repository inspection failed (e.g. empty repo or HTTP 409). Using default draft. "
                "Add files and commit to the repo to enable full inspection."
            )

    # Tool tracking: summary of what each stage produced (for debugging backend vs frontend)
    _debug_log(
        hypothesis_id="H7",
        location="app/repo_to_agent/workflow.py:tool_tracking_pipeline",
        message="Tool tracking pipeline summary",
        data={
            "stage": "final_result",
            "scout_important_files": scout_output.important_files[:25],
            "architect_key_paths": architect_output.key_paths[:25],
            "manifest_tools": [t.name for t in manifest_tools],
            "code_tools": [t.name for t in code_tools],
            "discovered_repo_tools": [t.name for t in discovered_repo_tools],
            "wrapped_repo_tools": [t.name for t in wrapped_repo_tools],
            "recommended_bundle": draft_output.recommended_bundle,
            "recommended_additional_tools": draft_output.recommended_additional_tools,
        },
    )
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


