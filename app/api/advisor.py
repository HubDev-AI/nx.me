"""Advisor API — Chat, Nudges & Memory Management.

Story 7-2: All 7 advisor endpoints.

Endpoints:
  POST /v1/advisor/messages           — send message (premium, require_feature)
  GET  /v1/advisor/messages           — conversation history
  GET  /v1/advisor/nudges             — nudge feed (all tiers)
  POST /v1/advisor/nudges/{id}/read   — mark nudge as read
  POST /v1/memories                   — add goal/note
  GET  /v1/memories                   — list memories
  DELETE /v1/memories/{id}            — delete memory
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from supabase import Client

from app.advisor.models import (
    ConversationHistoryResponse,
    MemoryCreateRequest,
    MemoryListResponse,
    MemoryResponse,
    MemoryType,
    MessageRequest,
    MessageResponse,
    NudgeFeedResponse,
    NudgeResponse,
)
from app.advisor.service import AdvisorService
from app.api.deps import get_current_user, get_redis, get_supabase, require_feature
from app.api.middleware.auth import UserClaims
from app.repositories.advisor_repo import AdvisorRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["advisor"])


# ---------------------------------------------------------------------------
# Dependency: AdvisorService
# ---------------------------------------------------------------------------


def get_advisor_service(
    request: Request,
    supabase: Client = Depends(get_supabase),
    redis_client: aioredis.Redis = Depends(get_redis),
) -> AdvisorService:
    """Return an AdvisorService wired to app-level infrastructure."""
    from app.api.deps import get_llm_adapter

    llm_adapter = get_llm_adapter()
    return AdvisorService(
        advisor_repo=AdvisorRepository(supabase),
        redis_client=redis_client,
        llm_adapter=llm_adapter,
    )


# ---------------------------------------------------------------------------
# POST /v1/advisor/messages — send message (premium only)
# ---------------------------------------------------------------------------


@router.post(
    "/advisor/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_advisor_message(
    body: MessageRequest,
    _: None = Depends(require_feature("advisor_chat")),
    claims: UserClaims = Depends(get_current_user),
    svc: AdvisorService = Depends(get_advisor_service),
) -> MessageResponse:
    """Send a message to Ada (premium tier only).

    Requires: require_feature("advisor_chat") — 402 if not on premium.
    Rate-limited to ADVISOR_CHAT_RATE_LIMIT messages/hour.
    """
    user_id = UUID(claims["sub"])

    try:
        row = await svc.send_message(user_id=user_id, raw_message=body.message)
    except ValueError as exc:
        msg = str(exc)
        if "RATE_LIMIT_EXCEEDED" in msg:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Too many messages. Try again in an hour.",
                    }
                },
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "INVALID_MESSAGE", "message": msg}},
        ) from exc

    return MessageResponse(
        id=row.get("id", ""),
        role=row.get("role", "advisor"),
        content=row.get("content", ""),
        created_at=row.get("created_at", ""),
    )


# ---------------------------------------------------------------------------
# GET /v1/advisor/messages — conversation history
# ---------------------------------------------------------------------------


@router.get("/advisor/messages", response_model=ConversationHistoryResponse)
def get_advisor_messages(
    claims: UserClaims = Depends(get_current_user),
    svc: AdvisorService = Depends(get_advisor_service),
) -> ConversationHistoryResponse:
    """Return the active conversation history for the current user."""
    user_id = UUID(claims["sub"])
    result = svc.get_conversation_history(user_id)

    return ConversationHistoryResponse(
        conversation_id=result["conversation_id"],
        messages=[
            MessageResponse(
                id=m["id"],
                role=m["role"],
                content=m["content"],
                created_at=m["created_at"],
            )
            for m in result["messages"]
        ],
    )


# ---------------------------------------------------------------------------
# GET /v1/advisor/nudges — nudge feed (all tiers)
# ---------------------------------------------------------------------------


@router.get("/advisor/nudges", response_model=NudgeFeedResponse)
def get_nudges(
    claims: UserClaims = Depends(get_current_user),
    svc: AdvisorService = Depends(get_advisor_service),
) -> NudgeFeedResponse:
    """Return the nudge feed for the current user (all tiers)."""
    user_id = UUID(claims["sub"])
    nudges = svc.get_nudges(user_id)

    return NudgeFeedResponse(
        nudges=[
            NudgeResponse(
                id=n["id"],
                trigger=n["trigger"],
                content=n["content"],
                read_at=n.get("read_at"),
                created_at=n["created_at"],
            )
            for n in nudges
        ]
    )


# ---------------------------------------------------------------------------
# POST /v1/advisor/nudges/{id}/read — mark nudge as read
# ---------------------------------------------------------------------------


@router.post("/advisor/nudges/{nudge_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_nudge_read(
    nudge_id: UUID,
    claims: UserClaims = Depends(get_current_user),
    svc: AdvisorService = Depends(get_advisor_service),
) -> None:
    """Mark a nudge as read. Idempotent — safe to call multiple times."""
    user_id = UUID(claims["sub"])
    found = svc.mark_nudge_read(user_id=user_id, nudge_id=nudge_id)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nudge not found",
        )


# ---------------------------------------------------------------------------
# POST /v1/memories — add goal/note
# ---------------------------------------------------------------------------


@router.post("/memories", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
async def add_memory(
    body: MemoryCreateRequest,
    claims: UserClaims = Depends(get_current_user),
    svc: AdvisorService = Depends(get_advisor_service),
) -> MemoryResponse:
    """Add a user-authored memory (goal or note). All tiers."""
    # Users may only create goal or user_note types
    if body.type not in (MemoryType.GOAL, MemoryType.USER_NOTE):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "INVALID_MEMORY_TYPE",
                    "message": "Users may only create 'goal' or 'user_note' memories.",
                }
            },
        )

    user_id = UUID(claims["sub"])
    row = await svc.add_memory(user_id=user_id, memory_type=body.type, content=body.content)

    return MemoryResponse(
        id=row.get("id", ""),
        type=row.get("type", ""),
        content=row.get("content", {}),
        created_at=row.get("created_at", ""),
    )


# ---------------------------------------------------------------------------
# GET /v1/memories — list memories
# ---------------------------------------------------------------------------


@router.get("/memories", response_model=MemoryListResponse)
def list_memories(
    claims: UserClaims = Depends(get_current_user),
    svc: AdvisorService = Depends(get_advisor_service),
) -> MemoryListResponse:
    """List all memories for the current user. All tiers."""
    user_id = UUID(claims["sub"])
    rows = svc.list_memories(user_id)

    return MemoryListResponse(
        memories=[
            MemoryResponse(
                id=r["id"],
                type=r["type"],
                content=r.get("content", {}),
                created_at=r["created_at"],
            )
            for r in rows
        ]
    )


# ---------------------------------------------------------------------------
# DELETE /v1/memories/{id} — delete memory
# ---------------------------------------------------------------------------


@router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(
    memory_id: UUID,
    claims: UserClaims = Depends(get_current_user),
    svc: AdvisorService = Depends(get_advisor_service),
) -> None:
    """Delete a user-owned memory. All tiers."""
    user_id = UUID(claims["sub"])
    deleted = svc.delete_memory(user_id=user_id, memory_id=memory_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )
