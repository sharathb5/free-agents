"""
Tests for repo-to-agent result validation (grader).
"""

from __future__ import annotations

import pytest

from app.repo_to_agent.models import RepoArchitectureOutput, RepoToAgentResult, WrappedRepoTool
from app.repo_to_agent.validation import ValidationResult, validate_repo_to_agent_result


def _minimal_result(
    *,
    repo_summary: str = "A Python library.",
    important_files: list[str] | None = None,
    recommended_bundle: str = "no_tools_writer",
    draft_name: str = "Test Agent",
    draft_description: str = "Helps with the repo.",
    starter_eval_cases: list[dict] | None = None,
) -> RepoToAgentResult:
    if important_files is None:
        important_files = ["README.md"]
    if starter_eval_cases is None:
        starter_eval_cases = [
            {"name": "eval1", "input": {"task": "Do X"}, "expected": "Should do X."}
        ]
    return RepoToAgentResult(
        repo_summary=repo_summary,
        architecture=RepoArchitectureOutput(
            languages=["Python"],
            frameworks=[],
            services=[],
            entrypoints=[],
            integrations=[],
            key_paths=["src/__init__.py"],
        ),
        important_files=important_files,
        recommended_bundle=recommended_bundle,
        recommended_additional_tools=[],
        draft_agent_spec={"name": draft_name, "description": draft_description},
        starter_eval_cases=starter_eval_cases,
        review_notes=[],
    )


def test_validate_pass() -> None:
    """Valid result with catalog bundle and full spec returns pass."""
    result = _minimal_result()
    vr = validate_repo_to_agent_result(result)
    assert vr.status == "pass"
    assert vr.errors == []
    assert vr.warnings == []


def test_validate_pass_with_valid_additional_tools() -> None:
    """Non-empty recommended_additional_tools with catalog tool IDs yields pass."""
    result = _minimal_result()
    result = RepoToAgentResult(
        **{**result.model_dump(), "recommended_additional_tools": ["http_request"]}
    )
    vr = validate_repo_to_agent_result(result)
    assert vr.status == "pass"
    assert vr.errors == []
    assert vr.warnings == []


def test_validate_fail_invalid_tool_id_not_in_catalog() -> None:
    """Validator enforcement: recommended_additional_tools with invalid ID yields fail; error references tool ID."""
    result = _minimal_result()
    result = RepoToAgentResult(
        **{**result.model_dump(), "recommended_additional_tools": ["made_up_tool"]}
    )
    vr = validate_repo_to_agent_result(result)
    assert vr.status == "fail"
    assert any("not in catalog" in e for e in vr.errors)
    assert any("made_up_tool" in e for e in vr.errors)


def test_validate_fail_empty_repo_summary() -> None:
    """Empty repo_summary yields fail."""
    result = _minimal_result(repo_summary="   ")
    vr = validate_repo_to_agent_result(result)
    assert vr.status == "fail"
    assert any("repo_summary" in e for e in vr.errors)


def test_validate_fail_empty_important_files() -> None:
    """Empty important_files yields fail."""
    result = _minimal_result(important_files=[])
    vr = validate_repo_to_agent_result(result)
    assert vr.status == "fail"
    assert any("important_files" in e for e in vr.errors)


def test_validate_fail_bundle_not_in_catalog() -> None:
    """recommended_bundle not in bundles catalog yields fail."""
    result = _minimal_result(recommended_bundle="python-library-maintenance")
    vr = validate_repo_to_agent_result(result)
    assert vr.status == "fail"
    assert any("not in the bundles catalog" in e for e in vr.errors)


def test_validate_fail_draft_spec_missing_description() -> None:
    """draft_agent_spec without non-empty description yields fail."""
    result = _minimal_result(draft_description="")
    vr = validate_repo_to_agent_result(result)
    assert vr.status == "fail"
    assert any("description" in e for e in vr.errors)


def test_validate_fail_empty_starter_eval_cases() -> None:
    """Empty starter_eval_cases yields fail."""
    result = _minimal_result(starter_eval_cases=[])
    vr = validate_repo_to_agent_result(result)
    assert vr.status == "fail"
    assert any("starter_eval_cases" in e for e in vr.errors)


def test_validate_fail_eval_case_missing_expected() -> None:
    """Eval case without 'expected' yields fail."""
    result = _minimal_result(
        starter_eval_cases=[{"name": "c1", "input": {}}]
    )
    vr = validate_repo_to_agent_result(result)
    assert vr.status == "fail"
    assert any("expected" in e for e in vr.errors)


def test_validate_pass_eval_case_input_may_be_string_or_object() -> None:
    """Eval case 'input' may be a string (user question) or an object; both are valid."""
    result = _minimal_result(
        starter_eval_cases=[
            {"name": "q1", "input": "How do I do X?", "expected": "Should explain X."},
            {"name": "q2", "input": {"goal": "Find Y"}, "expected": "Points to Y."},
        ]
    )
    vr = validate_repo_to_agent_result(result)
    assert vr.status == "pass"
    assert vr.errors == []


def test_validation_result_is_frozen() -> None:
    """ValidationResult is a frozen dataclass."""
    vr = ValidationResult(status="pass", errors=[], warnings=[])
    with pytest.raises(Exception):  # FrozenInstanceError
        vr.status = "fail"  # type: ignore[misc]


# ---- Repo-specific sanity checks (warnings only for known repos) ----


def test_repo_sanity_known_repo_generic_paths_warns() -> None:
    """Known repo (psf/requests) with generic paths only gets a repo-specific warning."""
    result = _minimal_result(important_files=["README.md", "LICENSE"])
    result = RepoToAgentResult(
        **{
            **result.model_dump(),
            "architecture": RepoArchitectureOutput(
                languages=["Python"],
                frameworks=[],
                services=[],
                entrypoints=[],
                integrations=[],
                key_paths=["README.md"],
            ),
        }
    )
    vr = validate_repo_to_agent_result(result, owner="psf", repo="requests")
    assert vr.status == "pass_with_warnings"
    assert any("psf/requests" in w for w in vr.warnings)
    assert any("repo-specific" in w or "expected more" in w for w in vr.warnings)


def test_repo_sanity_known_repo_with_enough_signals_no_warning() -> None:
    """Known repo with expected path signals in important_files/key_paths does not warn."""
    result = _minimal_result(
        important_files=["pyproject.toml", "src/requests/api.py", "src/requests/sessions.py"]
    )
    result = RepoToAgentResult(
        **{
            **result.model_dump(),
            "architecture": RepoArchitectureOutput(
                languages=["Python"],
                frameworks=[],
                services=[],
                entrypoints=[],
                integrations=[],
                key_paths=["src/requests/adapters.py"],
            ),
        }
    )
    vr = validate_repo_to_agent_result(result, owner="psf", repo="requests")
    assert vr.status == "pass"
    assert not any("psf/requests" in w for w in vr.warnings)


def test_validate_wrapped_repo_tools_valid() -> None:
    """Valid wrapped_repo_tools (risk_level, wrapper_kind, args_schema, source_path) yields pass."""
    result = _minimal_result()
    result = RepoToAgentResult(
        **{
            **result.model_dump(),
            "discovered_repo_tools": [],
            "wrapped_repo_tools": [
                WrappedRepoTool(
                    name="test",
                    tool_type="script",
                    command="npm run test",
                    source_path="package.json",
                    wrapper_kind="command",
                    args_schema={"type": "object", "properties": {}, "additionalProperties": False},
                    safe_to_auto_expose=True,
                    risk_level="low",
                    confidence=0.9,
                ).model_dump(),
            ],
        }
    )
    vr = validate_repo_to_agent_result(result)
    assert vr.status == "pass"
    assert not any("wrapped_repo_tools" in e for e in vr.errors)


def test_validate_wrapped_repo_tools_code_reference_valid() -> None:
    """Wrapped code-defined tool with wrapper_kind=code_reference is valid."""
    result = _minimal_result()
    result = RepoToAgentResult(
        **{
            **result.model_dump(),
            "discovered_repo_tools": [
                {"name": "search", "tool_type": "code_tool", "command": None, "description": "Code tool", "source_path": "tools.py", "confidence": 0.9},
            ],
            "wrapped_repo_tools": [
                WrappedRepoTool(
                    name="search",
                    tool_type="code_tool",
                    command=None,
                    description="Code tool",
                    source_path="tools.py",
                    wrapper_kind="code_reference",
                    args_schema={"type": "object", "properties": {}, "additionalProperties": True},
                    safe_to_auto_expose=False,
                    risk_level="medium",
                    confidence=0.9,
                ).model_dump(),
            ],
        }
    )
    vr = validate_repo_to_agent_result(result)
    assert vr.status == "pass"
    assert not any("wrapped_repo_tools" in e or "wrapper_kind" in e for e in vr.errors)


def test_validate_wrapped_repo_tools_high_risk_safe_fails() -> None:
    """High-risk tool marked safe_to_auto_expose=True yields fail."""
    result = _minimal_result()
    result = RepoToAgentResult(
        **{
            **result.model_dump(),
            "discovered_repo_tools": [],
            "wrapped_repo_tools": [
                WrappedRepoTool(
                    name="deploy",
                    tool_type="script",
                    command="npm run deploy",
                    source_path="package.json",
                    wrapper_kind="command",
                    args_schema={"type": "object", "properties": {}, "additionalProperties": False},
                    safe_to_auto_expose=True,
                    risk_level="high",
                    confidence=0.9,
                ).model_dump(),
            ],
        }
    )
    vr = validate_repo_to_agent_result(result)
    assert vr.status == "fail"
    assert any("safe_to_auto_expose" in e and "high" in e for e in vr.errors)


def test_validate_wrapped_repo_tools_missing_args_schema_fails() -> None:
    """Wrapped tool without args_schema yields fail. Use object.__setattr__ so Pydantic doesn't fill default."""
    result = _minimal_result()
    raw_wrapped = [
        {
            "name": "test",
            "tool_type": "script",
            "command": "npm run test",
            "source_path": "package.json",
            "wrapper_kind": "command",
            "safe_to_auto_expose": True,
            "risk_level": "low",
            "confidence": 0.9,
        },
    ]
    object.__setattr__(result, "wrapped_repo_tools", raw_wrapped)
    vr = validate_repo_to_agent_result(result)
    assert vr.status == "fail"
    assert any("args_schema" in e for e in vr.errors)


def test_repo_sanity_unknown_repo_no_warning() -> None:
    """Unknown owner/repo does not add repo-specific warnings."""
    result = _minimal_result(important_files=["README.md"])
    vr = validate_repo_to_agent_result(result, owner="unknown", repo="some-repo")
    assert vr.warnings == []


def test_repo_sanity_without_owner_repo_no_warning() -> None:
    """Validation without owner/repo does not add repo-specific warnings."""
    result = _minimal_result(important_files=["README.md"])
    vr = validate_repo_to_agent_result(result)
    assert vr.status == "pass"
    assert not any("repo-specific" in w for w in vr.warnings)
