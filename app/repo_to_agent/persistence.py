"""
Repo-to-agent persistence handoff layer.

Prepares a payload suitable for storing repo analysis artifacts, normalized
draft agent spec, and starter eval cases. When validation passes, can persist
the normalized agent to the registry via persist_if_valid / persist_validated_agent.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from app.storage.registry_store import register_agent

from .agent_spec_bridge import normalize_draft_agent_spec, validate_draft_agent_spec_for_registry
from .models import RepoToAgentResult
from .validation import validate_repo_to_agent_result


def prepare_repo_to_agent_persistence_payload(result: RepoToAgentResult) -> Dict[str, Any]:
    """
    Build a payload suitable for persisting repo-to-agent results.

    Includes:
      - repo_analysis: summary, architecture, important_files, recommended_bundle/tools.
      - normalized_draft_agent_spec: registry-compatible spec (from agent_spec_bridge).
      - starter_eval_cases: as-is for later eval suite creation.

    Does not write to the database. Callers should use this dict with their
    existing storage layer when ready.

    TODO: Persist to repo_analysis / draft_agent table when clean path exists.
    TODO: Create starter eval suite from starter_eval_cases when eval store supports it.
    """
    try:
        normalized_spec = normalize_draft_agent_spec(result.draft_agent_spec)
    except Exception:
        normalized_spec = result.draft_agent_spec

    return {
        "repo_analysis": {
            "repo_summary": result.repo_summary,
            "architecture": result.architecture.model_dump(),
            "important_files": result.important_files,
            "recommended_bundle": result.recommended_bundle,
            "recommended_additional_tools": result.recommended_additional_tools,
            "review_notes": result.review_notes,
        },
        "normalized_draft_agent_spec": normalized_spec,
        "starter_eval_cases": list(result.starter_eval_cases),
    }


def persist_validated_agent(
    result: RepoToAgentResult,
    owner: str,
    repo: str,
) -> Tuple[str, str]:
    """
    Normalize the draft agent spec and register it in the registry.

    Call only when the result has already passed validation (e.g. status
    pass or pass_with_warnings). Enriches the normalized spec with
    repo_owner, repo_name, eval_cases, and bundle_id from the result.

    Returns (agent_id, version). Raises AgentSpecInvalid if the draft spec
    fails structural validation, or AgentVersionExists if (id, version) exists.
    """
    normalized = validate_draft_agent_spec_for_registry(result.draft_agent_spec)
    normalized["repo_owner"] = owner.strip()
    normalized["repo_name"] = repo.strip()
    normalized["eval_cases"] = list(result.starter_eval_cases)
    if result.recommended_bundle and not normalized.get("bundle_id"):
        normalized["bundle_id"] = result.recommended_bundle.strip()
    return register_agent(normalized)


def persist_if_valid(
    result: RepoToAgentResult,
    owner: str,
    repo: str,
) -> Optional[Tuple[str, str]]:
    """
    If validation passes (pass or pass_with_warnings), normalize and register
    the agent; otherwise do not persist.

    Returns (agent_id, version) when persisted, None when not persisted
    (validation failed or spec invalid).
    """
    vr = validate_repo_to_agent_result(result, owner=owner, repo=repo)
    if vr.status == "fail":
        return None
    try:
        return persist_validated_agent(result, owner, repo)
    except Exception:
        return None
