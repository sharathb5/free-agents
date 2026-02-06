"""
Data models for the agent runtime.

Defines InvokeContext, InvokeRequest, MemoryPolicy, MemoryEvent, and KnowledgeItem.
Do not duplicate these definitions elsewhere.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MemoryPolicy(BaseModel):
    """Policy for session memory: last N events and/or max chars."""

    mode: str = "last_n"
    max_messages: int = Field(default=10, ge=0)
    max_chars: int = Field(default=8000, ge=0)


class MemoryEvent(BaseModel):
    """A single event in conversation memory (stored or in context)."""

    role: str  # "user" | "assistant" | "system"
    content: str
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
