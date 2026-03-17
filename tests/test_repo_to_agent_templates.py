from __future__ import annotations

from typing import Any, Dict, List

from app.repo_to_agent.models import (
    AgentDraftOutput,
    AgentReviewOutput,
    RepoArchitectureOutput,
    RepoScoutOutput,
)
from app.repo_to_agent.templates import (
    AGENT_DESIGNER_TEMPLATE,
    AGENT_REVIEWER_TEMPLATE,
    REPO_ARCHITECT_TEMPLATE,
    REPO_SCOUT_TEMPLATE,
    AgentTemplate,
)


def _collect_templates() -> List[AgentTemplate]:
    return [
        REPO_SCOUT_TEMPLATE,
        REPO_ARCHITECT_TEMPLATE,
        AGENT_DESIGNER_TEMPLATE,
        AGENT_REVIEWER_TEMPLATE,
    ]


def test_all_templates_exist_and_ids_unique() -> None:
    templates = _collect_templates()
    assert len(templates) == 4

    ids = {t.id for t in templates}
    assert len(ids) == 4, "Template ids must be unique"
    assert ids == {"repo_scout", "repo_architect", "agent_designer", "agent_reviewer"}


def test_allowed_tools_per_template() -> None:
    assert REPO_SCOUT_TEMPLATE.allowed_tools == ["github_repo_read"]
    assert REPO_ARCHITECT_TEMPLATE.allowed_tools == ["github_repo_read"]
    assert AGENT_DESIGNER_TEMPLATE.allowed_tools == []
    assert AGENT_REVIEWER_TEMPLATE.allowed_tools == []


def test_output_schema_matches_models() -> None:
    def normalize(schema: Dict[str, Any]) -> Dict[str, Any]:
        # Pydantic may add extra metadata keys; we compare key structural parts.
        return {
            "title": schema.get("title"),
            "type": schema.get("type"),
            "properties": schema.get("properties"),
            "required": schema.get("required"),
        }

    assert normalize(REPO_SCOUT_TEMPLATE.output_schema) == normalize(
        RepoScoutOutput.model_json_schema()
    )
    assert normalize(REPO_ARCHITECT_TEMPLATE.output_schema) == normalize(
        RepoArchitectureOutput.model_json_schema()
    )
    assert normalize(AGENT_DESIGNER_TEMPLATE.output_schema) == normalize(
        AgentDraftOutput.model_json_schema()
    )
    assert normalize(AGENT_REVIEWER_TEMPLATE.output_schema) == normalize(
        AgentReviewOutput.model_json_schema()
    )

