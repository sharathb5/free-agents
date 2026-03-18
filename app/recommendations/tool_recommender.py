from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RecommendationInput(BaseModel):
    """Input for tool recommendations for an agent."""

    name: str = ""
    description: str = ""
    primitive: str = ""
    prompt: str = ""
    repo_url: Optional[str] = None
    repo_context: Dict[str, Any] = Field(default_factory=dict)
    extracted_tool_ids: List[str] = Field(default_factory=list)


class CatalogTool(BaseModel):
    """Lightweight view of a tool row from the catalog."""

    tool_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    execution_kind: Optional[str] = None
    confidence: Optional[float] = None
    source_repo: Optional[str] = None
    source_path: Optional[str] = None
    promotion_reason: Optional[str] = None


class CatalogBundle(BaseModel):
    """Lightweight view of a bundle row from the catalog."""

    bundle_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    tools: List[str] = Field(default_factory=list)


class ScoreDetails(BaseModel):
    """Debug scoring information for one entity."""

    score: float = 0.0
    signals: List[str] = Field(default_factory=list)


class RecommendationDebug(BaseModel):
    """Optional debug info for recommendations."""

    intents: Dict[str, bool] = Field(default_factory=dict)
    bundle_scores: Dict[str, ScoreDetails] = Field(default_factory=dict)
    tool_scores: Dict[str, ScoreDetails] = Field(default_factory=dict)


class RecommendationResult(BaseModel):
    """Final recommendation result."""

    bundle_id: Optional[str]
    additional_tool_ids: List[str] = Field(default_factory=list)
    rationale: List[str] = Field(default_factory=list)
    debug: Optional[RecommendationDebug] = None


# --- Config and heuristics (intentionally simple and deterministic) ---

MAX_ADDITIONAL_TOOLS = 8

INTENT_KEYWORDS: Dict[str, List[str]] = {
    "filesystem": [
        "file",
        "filesystem",
        "files",
        "grep",
        "search",
        "code navigation",
        "navigate code",
        "repo understanding",
        "repository understanding",
        "shell",
        "terminal",
    ],
    "github": [
        "github",
        "pull request",
        "pull-request",
        "issues",
        "release",
        "changelog",
        "tag",
        "docs generation",
        "generate docs",
        "licenses",
        "license",
        "discussions",
        "workflow",
        "actions",
        "ci",
        "script",
        "scripts",
    ],
    "summarization": [
        "summarize",
        "summary",
        "summaries",
        "condense",
        "shorten",
        "tl;dr",
        "report",
        "rewrite",
        "paraphrase",
    ],
}

BUNDLE_INTENT_HINTS: Dict[str, List[str]] = {
    "filesystem": ["file", "filesystem", "code", "search"],
    "github": ["github", "repo", "repository"],
}

BUNDLE_PRIORITY: List[str] = [
    # more specific bundles first in case of ties
    "filesystem_search",
    "github_automation",
    "github_reader",
    "research_basic",
    "data_analysis",
    "repo_to_agent",
    "no_tools_writer",
]


def _normalize_text(value: str) -> str:
    return value.strip().lower()

def _tokens(value: str) -> List[str]:
    return [t for t in re.split(r"[^a-z0-9]+", (value or "").lower()) if t]


def _infer_intents(agent: RecommendationInput) -> Dict[str, bool]:
    haystack = " ".join(
        [
            agent.name or "",
            agent.description or "",
            agent.prompt or "",
        ]
    ).lower()

    intents: Dict[str, bool] = {}
    for intent, keywords in INTENT_KEYWORDS.items():
        intents[intent] = any(kw in haystack for kw in keywords)

    if (agent.primitive or "").strip().lower() == "transform" and not intents.get("filesystem", False):
        if intents.get("summarization", False):
            intents["summarizer_transform"] = True
    else:
        intents["summarizer_transform"] = False
    return intents


def _score_bundle(bundle: CatalogBundle, intents: Dict[str, bool], agent: RecommendationInput, extracted_ids: List[str]) -> ScoreDetails:
    score = 0.0
    signals: List[str] = []

    category = (bundle.category or "").lower()
    title_desc = f"{bundle.title or ''} {bundle.description or ''}".lower()

    if intents.get("filesystem", False):
        if "file" in category or any(h in title_desc for h in BUNDLE_INTENT_HINTS["filesystem"]):
            score += 3.0
            signals.append("filesystem_intent_bundle_match")

    if intents.get("github", False):
        if "github" in category or any(h in title_desc for h in BUNDLE_INTENT_HINTS["github"]):
            score += 3.0
            signals.append("github_intent_bundle_match")

    if intents.get("summarizer_transform", False):
        if bundle.bundle_id == "no_tools_writer":
            score += 2.0
            signals.append("summarizer_transform_prefers_no_tools_bundle")

    for tid in extracted_ids:
        if tid in bundle.tools:
            score += 0.5
            signals.append(f"extracted_tool_in_bundle:{tid}")

    return ScoreDetails(score=score, signals=signals)


def _score_tool(tool: CatalogTool, intents: Dict[str, bool], extracted_ids: List[str]) -> ScoreDetails:
    score = 0.0
    signals: List[str] = []

    category = (tool.category or "").lower()
    description = (tool.description or "").lower()
    tid = tool.tool_id
    category_tokens = set(_tokens(category))

    if intents.get("filesystem", False):
        # Use token matching to avoid accidental substring hits (e.g. "reSEARCH" in "research").
        if ("file" in category_tokens) or ("filesystem" in category_tokens) or ("search" in category_tokens):
            score += 2.0
            signals.append("filesystem_intent_tool_category")
        if any(kw in description for kw in ["file", "filesystem", "grep", "search", "code"]):
            score += 1.0
            signals.append("filesystem_intent_tool_description")

    if intents.get("github", False):
        if "github" in category:
            score += 2.0
            signals.append("github_intent_tool_category")
        if any(kw in description for kw in ["github", "release", "tag", "docs", "discussions", "license"]):
            score += 1.0
            signals.append("github_intent_tool_description")

    if intents.get("summarizer_transform", False):
        if "search" in category or "file" in category:
            score += 0.5
            signals.append("summarizer_maybe_needs_read_search")

    if tid in extracted_ids:
        score += 3.0
        signals.append("extracted_tool_match")

    return ScoreDetails(score=score, signals=signals)


def recommend_tools_for_agent(
    agent_input: RecommendationInput,
    available_tools: List[CatalogTool],
    available_bundles: List[CatalogBundle],
) -> RecommendationResult:
    """Deterministic heuristic recommendation over catalog bundles and tools."""

    primitive_norm = _normalize_text(agent_input.primitive)
    agent = agent_input.model_copy(update={"primitive": primitive_norm})
    extracted_ids = sorted({tid for tid in agent.extracted_tool_ids if isinstance(tid, str) and tid.strip()})

    intents = _infer_intents(agent)

    bundle_scores: Dict[str, ScoreDetails] = {}
    for b in available_bundles:
        details = _score_bundle(b, intents, agent, extracted_ids)
        bundle_scores[b.bundle_id] = details

    tool_scores: Dict[str, ScoreDetails] = {}
    for t in available_tools:
        details = _score_tool(t, intents, extracted_ids)
        tool_scores[t.tool_id] = details

    chosen_bundle_id: Optional[str] = None
    best_score = 0.0
    for bundle_id in BUNDLE_PRIORITY:
        if bundle_id in bundle_scores:
            details = bundle_scores[bundle_id]
            if details.score > best_score:
                best_score = details.score
                chosen_bundle_id = bundle_id

    if chosen_bundle_id is None:
        for b in available_bundles:
            details = bundle_scores[b.bundle_id]
            if details.score > best_score:
                best_score = details.score
                chosen_bundle_id = b.bundle_id

    BUNDLE_THRESHOLD = 1.0
    if chosen_bundle_id is not None and bundle_scores[chosen_bundle_id].score < BUNDLE_THRESHOLD:
        chosen_bundle_id = None

    sorted_tools = sorted(
        available_tools,
        key=lambda t: (-tool_scores.get(t.tool_id, ScoreDetails()).score, t.tool_id),
    )
    additional_tool_ids: List[str] = []
    TOOL_THRESHOLD = 1.0
    chosen_bundle_tools: List[str] = []
    if chosen_bundle_id is not None:
        for b in available_bundles:
            if b.bundle_id == chosen_bundle_id:
                chosen_bundle_tools = b.tools
                break

    for t in sorted_tools:
        if len(additional_tool_ids) >= MAX_ADDITIONAL_TOOLS:
            break
        if t.tool_id in chosen_bundle_tools:
            continue
        details = tool_scores.get(t.tool_id)
        if details is None or details.score < TOOL_THRESHOLD:
            continue
        additional_tool_ids.append(t.tool_id)

    rationale: List[str] = []
    if intents.get("filesystem", False):
        rationale.append("Detected filesystem/search intent from agent description or prompt.")
    if intents.get("github", False):
        rationale.append("Detected GitHub/repo automation intent from agent description or prompt.")
    if intents.get("summarizer_transform", False):
        rationale.append("Detected transform summarization intent; avoiding heavy tool bundles by default.")

    if chosen_bundle_id is not None:
        rationale.append(f"Selected bundle '{chosen_bundle_id}' based on highest score and inferred intents.")
    else:
        rationale.append("No bundle exceeded minimum score; not recommending a bundle.")

    if additional_tool_ids:
        rationale.append(
            f"Selected additional tools based on category/description alignment and extracted tools: {', '.join(additional_tool_ids)}."
        )
    else:
        rationale.append("No additional tools strongly matched the agent intent.")

    if not any(intents.values()):
        rationale.append("Overall match strength is low; recommendations are conservative.")

    debug = RecommendationDebug(
        intents=intents,
        bundle_scores=bundle_scores,
        tool_scores=tool_scores,
    )

    return RecommendationResult(
        bundle_id=chosen_bundle_id,
        additional_tool_ids=additional_tool_ids,
        rationale=rationale,
        debug=debug,
    )

