"""Advisor data models — Pydantic schemas and domain types."""
from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Memory types
# ---------------------------------------------------------------------------


class MemoryType(StrEnum):
    GOAL = "goal"
    USER_NOTE = "user_note"
    ACCEPTED_SUGGESTION = "accepted_suggestion"
    DISMISSED_SUGGESTION = "dismissed_suggestion"
    ANALYSIS_INSIGHT = "analysis_insight"


# ---------------------------------------------------------------------------
# LLM response
# ---------------------------------------------------------------------------


class LLMResponse(BaseModel):
    content: str
    input_tokens: int = 0
    output_tokens: int = 0


# ---------------------------------------------------------------------------
# Memory API models
# ---------------------------------------------------------------------------


class MemoryCreateRequest(BaseModel):
    type: MemoryType
    content: dict[str, Any]


class MemoryResponse(BaseModel):
    id: str
    type: str
    content: dict[str, Any]
    created_at: str


class MemoryListResponse(BaseModel):
    memories: list[MemoryResponse]


# ---------------------------------------------------------------------------
# Message API models
# ---------------------------------------------------------------------------


class MessageRequest(BaseModel):
    message: str


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


class ConversationHistoryResponse(BaseModel):
    conversation_id: str
    messages: list[MessageResponse]


# ---------------------------------------------------------------------------
# Nudge API models
# ---------------------------------------------------------------------------


class NudgeResponse(BaseModel):
    id: str
    trigger: str
    content: str
    read_at: str | None
    created_at: str


class NudgeFeedResponse(BaseModel):
    nudges: list[NudgeResponse]
    next_cursor: str | None = None
    has_more: bool = False


class ConversationHistoryPageResponse(BaseModel):
    conversation_id: str
    messages: list[MessageResponse]
    next_cursor: str | None = None
    has_more: bool = False


class MemoryListPageResponse(BaseModel):
    memories: list[MemoryResponse]
    next_cursor: str | None = None
    has_more: bool = False
