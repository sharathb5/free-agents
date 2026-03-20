from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


CAPABILITY_CATEGORIES = (
    "search_retrieval",
    "http_api_access",
    "file_filesystem",
    "code_execution",
    "structured_data",
    "communication",
)


def normalize_tool_name(name: str) -> str:
    """
    Deterministic normalization used for dedupe/debug/UI.

    - lower-case
    - collapse non-alnum into '_'
    - strip leading/trailing '_'
    """
    s = (name or "").strip().lower()
    out: List[str] = []
    prev_us = False
    for ch in s:
        if ch.isalnum():
            out.append(ch)
            prev_us = False
        else:
            if not prev_us:
                out.append("_")
                prev_us = True
    normalized = "".join(out).strip("_")
    return normalized or "tool"


def default_args_schema(*, allow_additional: bool = False) -> Dict[str, Any]:
    """
    Default schema aligned with repo_to_agent WrappedRepoTool.args_schema.
    """
    return {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": bool(allow_additional),
    }


class ToolCandidate(BaseModel):
    name: str
    normalized_name: str = ""
    description: Optional[str] = ""
    source_repo: str
    source_path: str
    tool_type: str
    args_schema: Dict[str, Any] = Field(default_factory=default_args_schema)
    execution_kind: str
    risk_level: str = "medium"  # low|medium|high
    tags: List[str] = Field(default_factory=list)
    capability_category: str = Field(default="code_execution")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    promotion_reason: Optional[str] = None
    raw_snippet: str = ""

    def with_computed_fields(self) -> "ToolCandidate":
        """
        Return a copy with deterministic derived fields filled in.
        """
        normalized = normalize_tool_name(self.name)
        category = self.capability_category
        if category not in CAPABILITY_CATEGORIES:
            category = "code_execution"
        return self.model_copy(
            update={
                "normalized_name": normalized,
                "capability_category": category,
            }
        )

