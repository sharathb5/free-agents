"""
Eval runner (Part 6): execute eval suites using the existing runtime path.

Reuses run_runner, run_store, registry_store. Provider is passed in (same
dependency path as agents/runs routers).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.config import get_settings
from app.registry_adapter import spec_to_preset
from app.runtime.runner import run_runner
from app.runtime.tools.registry import DefaultToolRegistry
from app.storage import eval_store
from app.storage import registry_store
from app.storage import run_store

from app.evals.matchers import score_case


class EvalSuiteNotFound(RuntimeError):
    """Raised when eval suite does not exist."""


def run_eval_suite(
    eval_suite_id: str,
    provider: Any,
    *,
    agent_version_override: Optional[str] = None,
    eval_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run an eval suite synchronously. Reuses the existing runtime execution path.

    Args:
        eval_suite_id: ID of the eval suite.
        provider: Provider instance (same as agents/runs routers use).
        agent_version_override: Optional override for agent version.
        eval_run_id: Optional. When provided (e.g. from wait=false flow), use this run instead of creating one.

    Returns:
        Eval run dict with status, summary_json, and id.

    Raises:
        EvalSuiteNotFound: If suite does not exist.
        AgentNotFound: If agent does not exist in registry.
    """
    suite = eval_store.get_eval_suite(eval_suite_id)
    if suite is None:
        raise EvalSuiteNotFound(f"Eval suite not found: {eval_suite_id}")

    agent_id = suite["agent_id"]
    agent_version = agent_version_override if agent_version_override is not None else suite.get("agent_version")

    spec = registry_store.get_agent(agent_id, version=agent_version)
    if spec is None:
        raise registry_store.AgentNotFound(f"Agent not found: {agent_id}")

    preset = spec_to_preset(spec)
    resolved_version = spec.get("version", "latest")

    tools_enabled = get_settings().tools_enabled
    tool_registry = DefaultToolRegistry() if tools_enabled else None
    limits = getattr(preset, "resolved_execution_limits", None) or {}

    if eval_run_id:
        eval_run = eval_store.get_eval_run(eval_run_id) or {"id": eval_run_id}
    else:
        eval_run = eval_store.create_eval_run(
            eval_suite_id,
            agent_id,
            agent_version=resolved_version,
        )
        eval_run_id = eval_run["id"]
        eval_store.set_eval_run_status(eval_run_id, "running")

    cases: List[Dict[str, Any]] = suite.get("cases_json") or []
    total_cases = len(cases)
    passed = 0
    failed = 0
    errored = 0
    scores: List[float] = []

    try:
        for case_index, case in enumerate(cases):
            case_input = case.get("input")
            if not isinstance(case_input, dict):
                case_input = {}
            session_id = case.get("session_id") if isinstance(case.get("session_id"), str) else None

            run = run_store.create_run(agent_id, resolved_version, session_id, case_input)
            run_id = run["id"]

            try:
                run_runner(
                    preset=preset,
                    provider=provider,
                    input_payload=case_input,
                    run_id=run_id,
                    session_id=session_id,
                    request_id=None,
                    tool_registry=tool_registry,
                    max_steps=limits.get("max_steps"),
                    max_wall_time_seconds=limits.get("max_wall_time_seconds"),
                )
            except Exception as e:
                eval_store.append_eval_case_result(
                    eval_run_id,
                    case_index=case_index,
                    status="error",
                    score=0.0,
                    matcher_type=case.get("matcher", {}).get("type", "unknown") or "unknown",
                    message=str(e)[:500],
                    run_id=run_id,
                )
                errored += 1
                continue

            run_after = run_store.get_run(run_id)
            actual = run_after.get("output_json") if run_after else None

            if run_after and run_after.get("status") == "failed":
                eval_store.append_eval_case_result(
                    eval_run_id,
                    case_index=case_index,
                    status="error",
                    score=0.0,
                    matcher_type=case.get("matcher", {}).get("type", "unknown") or "unknown",
                    message=run_after.get("error") or "Run failed",
                    run_id=run_id,
                )
                errored += 1
                continue

            expected = case.get("expected")
            matcher = case.get("matcher") or {}
            if not isinstance(matcher, dict):
                matcher = {"type": "exact_json"}

            result = score_case(expected, actual, matcher)
            status = result["status"]
            score = result["score"]
            message = result.get("message")

            eval_store.append_eval_case_result(
                eval_run_id,
                case_index=case_index,
                status=status,
                score=score,
                matcher_type=matcher.get("type", "exact_json"),
                expected_json=expected,
                actual_json=actual,
                message=message,
                run_id=run_id,
            )

            if status == "passed":
                passed += 1
            elif status == "error":
                errored += 1
            else:
                failed += 1
            scores.append(score)

        completed_cases = passed + failed + errored
        average_score = sum(scores) / len(scores) if scores else 0.0
        pass_rate = passed / total_cases if total_cases > 0 else 0.0

        summary = {
            "total_cases": total_cases,
            "passed": passed,
            "failed": failed,
            "errored": errored,
            "completed_cases": completed_cases,
            "average_score": average_score,
            "pass_rate": pass_rate,
        }
        eval_store.set_eval_run_status(eval_run_id, "succeeded", summary_json=summary)

    except Exception as e:
        eval_store.set_eval_run_status(
            eval_run_id,
            "failed",
            error=str(e)[:1000],
        )
        raise

    return eval_store.get_eval_run(eval_run_id) or eval_run
