"""
Repo-to-agent application entry flow.

Top-level helper that builds the repo workflow, selects the execution backend,
and returns a RepoToAgentResult. Kept thin so an OpenAI backend can be added later.
"""

from __future__ import annotations

import concurrent.futures
import os
from typing import Any, Dict

from .exceptions import is_should_fallback_to_internal, StepTimeoutError
from .internal_runner import run_specialist_with_internal_runner
from .models import RepoToAgentResult
from .workflow import is_large_repo
from .openai_adapter import (
    REPO_TO_AGENT_STEP_TIMEOUT_SECONDS,
    run_specialist_with_openai_agent,
)
from .service import generate_agent_from_repo


def _import_async_openai_client() -> Any:
    """Lazy import boundary for OpenAI client (patchable in tests)."""
    from openai import AsyncOpenAI  # type: ignore[import-not-found]

    return AsyncOpenAI


def run_repo_to_agent(
    repo_input: Dict[str, Any],
    execution_backend: str = "internal",
) -> RepoToAgentResult:
    """
    Run the full repo-to-agent workflow and return an aggregated result.

    - repo_input: dict with owner, repo, and optional ref or url (same as build_repo_workflow).
    - execution_backend: "internal" uses the deterministic internal runner (no OpenAI SDK).
      Other backends (e.g. "openai") can be added later.

    Returns RepoToAgentResult suitable for persistence and review flows.
    """
    if execution_backend == "internal":
        runner = run_specialist_with_internal_runner
        return generate_agent_from_repo(repo_input, runner)

    if execution_backend == "openai":
        # Hybrid mode for initial integration:
        # - OpenAI Agents SDK for specialists we have wired (repo_scout, repo_architect, agent_designer)
        # - Internal deterministic runner for the remaining specialist (agent_reviewer)
        AsyncOpenAI = _import_async_openai_client()
        client = AsyncOpenAI()

        step_timeout = int(
            os.environ.get(
                "REPO_TO_AGENT_STEP_TIMEOUT_SECONDS",
                str(REPO_TO_AGENT_STEP_TIMEOUT_SECONDS),
            )
        )

        def runner(
            template: Any,
            input_payload: Dict[str, Any],
            step_telemetry: Dict[str, Any] | None = None,
        ) -> Dict[str, Any] | tuple[Dict[str, Any], list[str]]:
            tid = getattr(template, "id", "")
            openai_runners = {
                "repo_scout": lambda: run_specialist_with_openai_agent(template, input_payload, client, step_telemetry),
                "repo_architect": lambda: run_specialist_with_openai_agent(template, input_payload, client, step_telemetry),
                "agent_designer": lambda: run_specialist_with_openai_agent(template, input_payload, client, step_telemetry),
            }
            if tid in openai_runners:
                # Large-repo routing rule: for architect, bypass OpenAI when the
                # scout summary already indicates a very large/broad repo.
                if tid == "repo_architect":
                    scout_summary = input_payload.get("scout_summary") or {}
                    try:
                        from .models import RepoScoutOutput, RepoArchitectureOutput

                        scout_output = RepoScoutOutput.model_validate(scout_summary)
                        # Architect output is not available yet; routing is based on
                        # the scout signal alone.
                        if is_large_repo(scout_output, None):
                            if step_telemetry is not None:
                                step_telemetry["backend_used"] = "internal"
                                step_telemetry["fallback_triggered"] = False
                            note = "repo_architect ran via internal runner due to large repo routing rule"
                            return (
                                run_specialist_with_internal_runner(
                                    template, input_payload, step_telemetry
                                ),
                                [note],
                            )
                    except Exception:
                        # If heuristic evaluation fails, fall back to normal routing.
                        pass
                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                        future = ex.submit(openai_runners[tid])
                        try:
                            return future.result(timeout=step_timeout)
                        except concurrent.futures.TimeoutError:
                            raise StepTimeoutError(
                                f"{tid} step exceeded timeout of {step_timeout}s"
                            ) from None
                except Exception as exc:
                    if tid in ("repo_scout", "repo_architect") and is_should_fallback_to_internal(exc):
                        if step_telemetry is not None:
                            step_telemetry["fallback_triggered"] = True
                            step_telemetry["backend_used"] = "internal"
                        reason = "step timeout" if isinstance(exc, StepTimeoutError) else "max turns exceeded"
                        fallback_note = f"{tid} used internal fallback ({reason})"
                        return run_specialist_with_internal_runner(template, input_payload, step_telemetry), [fallback_note]
                    raise
            return run_specialist_with_internal_runner(template, input_payload, step_telemetry)

        return generate_agent_from_repo(repo_input, runner)

    raise ValueError(f"Unsupported execution_backend: {execution_backend}")
