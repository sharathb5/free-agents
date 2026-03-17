"""
Data models for the agent runtime.

Defines InvokeContext, InvokeRequest, MemoryPolicy, MemoryEvent, and KnowledgeItem.
Do not duplicate these definitions elsewhere.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class StoredAgent(BaseModel):
    """Storage view of a registered agent (e.g. from repo-to-agent or registry)."""

    agent_id: str
    name: str
    description: str
    bundle_id: Optional[str] = None
    tools: List[str] = Field(default_factory=list)
    eval_cases: List[Dict[str, Any]] = Field(default_factory=list)
    repo_owner: Optional[str] = None
    repo_name: Optional[str] = None
    created_at: float = 0.0


class MemoryPolicy(BaseModel):
    """Policy for session memory: last N events and/or max chars.

    Agent Runtime Part 4 adds optional tool-aware fields; presets that don't
    specify them fall back to safe defaults.
    """

    mode: str = "last_n"
    max_messages: int = Field(default=10, ge=0)
    max_chars: int = Field(default=8000, ge=0)
    # Tool-aware memory controls (optional; default excludes tool results).
    memory_include_tool_results: bool = False
    # "exclude" | "summary" | "full"; only used when memory_include_tool_results is True.
    memory_tool_result_mode: str = "summary"


class MemoryEvent(BaseModel):
    """A single event in conversation memory (stored or in context)."""

    role: str  # "user" | "assistant" | "system"
    content: str
    event_type: Optional[str] = None
    run_id: Optional[str] = None
    step_index: Optional[int] = None
    tool_name: Optional[str] = None
    idempotency_key: Optional[str] = None
    ts: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


class KnowledgeItem(BaseModel):
    """Optional knowledge item for prompt context (e.g. RAG chunk)."""

    id: Optional[str] = None
    content: str
    meta: Optional[Dict[str, Any]] = None


class InvokeContext(BaseModel):
    """Optional context for /invoke: session and/or inline memory."""

    session_id: Optional[str] = None
    memory: Optional[List[Dict[str, Any]]] = None  # list of {role, content, ...}
    knowledge: Optional[List[Dict[str, Any]]] = None


class InvokeRequest(BaseModel):
    """Parsed /invoke request body."""

    input: Dict[str, Any]
    context: Optional[InvokeContext] = None


class Run(BaseModel):
    """Runtime run record (one per invocation)."""

    id: str
    agent_id: str
    agent_version: str
    status: str  # queued|running|succeeded|failed|canceled
    created_at: str
    updated_at: str
    session_id: Optional[str] = None
    input_json: Dict[str, Any]
    output_json: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    step_count: int = 0
    usage_json: Optional[Dict[str, Any]] = None


class RunStep(BaseModel):
    """Runtime step record (one per step/action)."""

    id: str
    run_id: str
    step_index: int
    step_type: str  # llm_action|tool_call|tool_result|final|error
    model: Optional[str] = None
    action_json: Dict[str, Any]
    tool_name: Optional[str] = None
    tool_args_json: Optional[Dict[str, Any]] = None
    tool_result_json: Optional[Dict[str, Any]] = None
    created_at: str
    error: Optional[str] = None


class EvalSuite(BaseModel):
    """Eval suite: saved set of test cases for an agent (Part 6)."""

    id: str
    agent_id: str
    agent_version: Optional[str] = None
    name: str
    description: Optional[str] = None
    created_at: str
    updated_at: str
    cases_json: List[Dict[str, Any]]


class EvalRun(BaseModel):
    """Eval run: one execution of an eval suite against an agent (Part 6)."""

    id: str
    eval_suite_id: str
    agent_id: str
    agent_version: Optional[str] = None
    status: str  # queued|running|succeeded|failed
    created_at: str
    updated_at: str
    summary_json: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class EvalCaseResult(BaseModel):
    """Eval case result: outcome of one case in an eval run (Part 6)."""

    id: str
    eval_run_id: str
    case_index: int
    status: str  # passed|failed|error
    score: float
    expected_json: Optional[Dict[str, Any]] = None
    actual_json: Optional[Dict[str, Any]] = None
    matcher_type: str
    message: Optional[str] = None
    run_id: Optional[str] = None
    created_at: str
