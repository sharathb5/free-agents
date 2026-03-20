"""
Deterministic tool ingestion pipeline.

Extracts tool candidates from repositories into a staging table and promotes
high-confidence candidates into platform tools. No LLM usage; no repo code execution.
"""

from .models import ToolCandidate
from .pipeline import dedupe_candidates, promote_candidates, run_tool_ingestion_for_repo

__all__ = [
    "ToolCandidate",
    "dedupe_candidates",
    "promote_candidates",
    "run_tool_ingestion_for_repo",
]

