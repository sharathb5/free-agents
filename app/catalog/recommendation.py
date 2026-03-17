# TODO: later replace with LLM classifier.
"""
Agent idea -> bundle recommendation (Part 5 MVP). Keyword-based heuristic.
"""

from __future__ import annotations

from typing import Any, Dict, List

# Precedence order: first match wins when multiple keywords match.
_KEYWORD_RULES: List[tuple[List[str], str, str, float]] = [
    (
        ["repo to agent", "generate agent from repo", "turn repo into agent"],
        "repo_to_agent",
        "Agent idea suggests turning a repository into an agent.",
        0.9,
    ),
    (["github", "repo", "codebase"], "github_reader", "Agent idea mentions GitHub or codebase access.", 0.85),
    (["research", "sources", "article", "web"], "research_basic", "Agent idea suggests web research or articles.", 0.85),
    (["write", "email", "draft"], "no_tools_writer", "Agent idea suggests writing or drafting without tools.", 0.8),
    (["analyze csv", "data"], "data_analysis", "Agent idea suggests data analysis.", 0.75),
]


def recommend_bundle(agent_idea: str) -> Dict[str, Any]:
    """
    Recommend a bundle and optional additional tools from an agent idea string.

    Returns:
        bundle_id: str
        confidence: float 0.0-1.0
        rationale: str
        suggested_additional_tools: list of tool_ids from catalog (may be empty)
    """
    if not agent_idea or not isinstance(agent_idea, str):
        return {
            "bundle_id": "no_tools_writer",
            "confidence": 0.2,
            "rationale": "No agent idea provided; defaulting to writer with no tools.",
            "suggested_additional_tools": [],
        }
    lower = agent_idea.strip().lower()
    for keywords, bundle_id, rationale, confidence in _KEYWORD_RULES:
        for kw in keywords:
            if kw in lower:
                return {
                    "bundle_id": bundle_id,
                    "confidence": confidence,
                    "rationale": rationale,
                    "suggested_additional_tools": [],
                }
    return {
        "bundle_id": "no_tools_writer",
        "confidence": 0.3,
        "rationale": "No matching bundle; defaulting to writer with no tools.",
        "suggested_additional_tools": [],
    }
