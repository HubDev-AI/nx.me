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
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from supabase import Client

from app.advisor.models import (
    ConversationHistoryPageResponse,
    MemoryCreateRequest,
    MemoryListPageResponse,
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
) -> Response:
    """Send a message to Ada (premium tier only).

    Requires: require_feature("advisor_chat") — 402 if not on premium.
    Rate-limited to ADVISOR_CHAT_RATE_LIMIT messages/hour.
    Returns 201 with Location header pointing to the conversation history.
    """
    from fastapi.responses import JSONResponse

    user_id = UUID(claims["sub"])

    try:
        row = await svc.send_message(user_id=user_id, raw_message=body.message)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "INVALID_MESSAGE", "message": str(exc)}},
        ) from exc

    message_id = row.get("id", "")
    payload = MessageResponse(
        id=message_id,
        role=row.get("role", "advisor"),
        content=row.get("content", ""),
        created_at=row.get("created_at", ""),
    )
    return JSONResponse(
        content=payload.model_dump(),
        status_code=status.HTTP_201_CREATED,
        headers={"Location": f"/v1/advisor/messages"},
    )


# ---------------------------------------------------------------------------
# GET /v1/advisor/messages — conversation history
# ---------------------------------------------------------------------------


@router.get("/advisor/messages", response_model=ConversationHistoryPageResponse)
def get_advisor_messages(
    cursor: str | None = Query(None, description="Cursor ({created_at}|{id} composite)"),
    limit: int = Query(50, ge=1, le=100),
    claims: UserClaims = Depends(get_current_user),
    svc: AdvisorService = Depends(get_advisor_service),
) -> ConversationHistoryPageResponse:
    """Return the active conversation history for the current user (paginated)."""
    user_id = UUID(claims["sub"])
    result = svc.get_conversation_history_page(user_id, limit=limit, cursor=cursor)

    return ConversationHistoryPageResponse(
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
        next_cursor=result.get("next_cursor"),
        has_more=result.get("has_more", False),
    )


# ---------------------------------------------------------------------------
# GET /v1/advisor/nudges — nudge feed (all tiers)
# ---------------------------------------------------------------------------


@router.get("/advisor/nudges", response_model=NudgeFeedResponse)
def get_nudges(
    cursor: str | None = Query(None, description="Cursor ({created_at}|{id} composite)"),
    limit: int = Query(50, ge=1, le=100),
    unread: bool = Query(False, description="When true, return only unread nudges (read_at IS NULL)"),
    claims: UserClaims = Depends(get_current_user),
    svc: AdvisorService = Depends(get_advisor_service),
) -> NudgeFeedResponse:
    """Return the nudge feed for the current user (all tiers, paginated)."""
    user_id = UUID(claims["sub"])
    result = svc.get_nudges_page(user_id, limit=limit, cursor=cursor, unread_only=unread)

    return NudgeFeedResponse(
        nudges=[
            NudgeResponse(
                id=n["id"],
                trigger=n["trigger"],
                content=n["content"],
                read_at=n.get("read_at"),
                created_at=n["created_at"],
            )
            for n in result["nudges"]
        ],
        next_cursor=result.get("next_cursor"),
        has_more=result.get("has_more", False),
    )


# ---------------------------------------------------------------------------
# PATCH /v1/advisor/nudges/{id} — update nudge (canonical noun-based route)
# POST /v1/advisor/nudges/{id}/read — deprecated alias (backward compat)
# ---------------------------------------------------------------------------


class NudgeUpdateRequest(BaseModel):
    read: bool = Field(..., description="Set to true to mark the nudge as read")


@router.patch(
    "/advisor/nudges/{nudge_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def update_nudge(
    nudge_id: UUID,
    body: NudgeUpdateRequest,
    claims: UserClaims = Depends(get_current_user),
    svc: AdvisorService = Depends(get_advisor_service),
) -> None:
    """Update a nudge. Currently supports marking as read (idempotent)."""
    user_id = UUID(claims["sub"])
    found = svc.mark_nudge_read(user_id=user_id, nudge_id=nudge_id)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nudge not found",
        )


@router.post(
    "/advisor/nudges/{nudge_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    deprecated=True,
)
def mark_nudge_read(
    nudge_id: UUID,
    claims: UserClaims = Depends(get_current_user),
    svc: AdvisorService = Depends(get_advisor_service),
) -> None:
    """Deprecated alias — use PATCH /advisor/nudges/{nudge_id} instead."""
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
) -> Response:
    """Add a user-authored memory (goal or note). All tiers.

    Returns 201 with Location header pointing to the memory list.
    """
    from fastapi.responses import JSONResponse

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

    memory_id = row.get("id", "")
    payload = MemoryResponse(
        id=memory_id,
        type=row.get("type", ""),
        content=row.get("content", {}),
        created_at=row.get("created_at", ""),
    )
    return JSONResponse(
        content=payload.model_dump(),
        status_code=status.HTTP_201_CREATED,
        headers={"Location": f"/v1/memories/{memory_id}"},
    )


# ---------------------------------------------------------------------------
# GET /v1/memories — list memories
# ---------------------------------------------------------------------------


@router.get("/memories", response_model=MemoryListPageResponse)
def list_memories(
    cursor: str | None = Query(None, description="Cursor ({created_at}|{id} composite)"),
    limit: int = Query(50, ge=1, le=100),
    claims: UserClaims = Depends(get_current_user),
    svc: AdvisorService = Depends(get_advisor_service),
) -> MemoryListPageResponse:
    """List memories for the current user (paginated). All tiers."""
    user_id = UUID(claims["sub"])
    result = svc.list_memories_page(user_id, limit=limit, cursor=cursor)

    return MemoryListPageResponse(
        memories=[
            MemoryResponse(
                id=r["id"],
                type=r["type"],
                content=r.get("content", {}),
                created_at=r["created_at"],
            )
            for r in result["memories"]
        ],
        next_cursor=result.get("next_cursor"),
        has_more=result.get("has_more", False),
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
