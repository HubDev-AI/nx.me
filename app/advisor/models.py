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
    # One row per user (partial unique index, see migration 0040). Carries
    # the current stable style facts (face shape, symmetry, current top
    # recommendations) — upserted on every successful analysis. Chat
    # user_data and nudge generation read from this row in preference to
    # re-deriving from the most recent ``analysis_insight``.
    STYLE_PROFILE = "style_profile"


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
    # Field named `content` to mirror MessageResponse.content and the mobile
    # AdvisorMessage type — request and response shapes were asymmetric and
    # mobile already shipped sending {content}.
    content: str


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
    body: str
    next_step_label: str
    next_step_seed: str
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


class NudgeNextStepResponse(BaseModel):
    seed_text: str


# ---------------------------------------------------------------------------
# Chat seeds API models (Plan 2026-04-20-001 Unit 5)
# ---------------------------------------------------------------------------


class ChatSeed(BaseModel):
    label: str
    text: str


class ChatSeedsResponse(BaseModel):
    seeds: list[ChatSeed]
