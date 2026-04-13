"""Block API — user-to-user blocking."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel

from app.api.deps import get_block_repo, get_current_user, require_app_feature
from app.api.middleware.auth import UserClaims
from app.repositories.block_repo import BlockRepository

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["blocks"],
    dependencies=[Depends(require_app_feature("social_enabled"))],
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class BlockedUserResponse(BaseModel):
    id: str
    blocked_id: str
    display_name: str | None = None
    username: str | None = None
    created_at: str


class BlockedListResponse(BaseModel):
    users: list[BlockedUserResponse]
    next_cursor: str | None = None
    has_more: bool = False


# ---------------------------------------------------------------------------
# POST /users/{user_id}/block
# ---------------------------------------------------------------------------


@router.post(
    "/users/{user_id}/block",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def block_user(
    user_id: UUID,
    claims: UserClaims = Depends(get_current_user),
    block_repo: BlockRepository = Depends(get_block_repo),
) -> Response:
    """Block a user. Idempotent."""
    blocker_id = claims["sub"]
    if str(user_id) == blocker_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot block yourself",
        )
    block_repo.block(blocker_id, str(user_id))
    logger.info("User %s blocked %s", blocker_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# DELETE /users/{user_id}/block
# ---------------------------------------------------------------------------


@router.delete(
    "/users/{user_id}/block",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def unblock_user(
    user_id: UUID,
    claims: UserClaims = Depends(get_current_user),
    block_repo: BlockRepository = Depends(get_block_repo),
) -> Response:
    """Unblock a user."""
    blocker_id = claims["sub"]
    found = block_repo.unblock(blocker_id, str(user_id))
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Block relationship not found",
        )
    logger.info("User %s unblocked %s", blocker_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# GET /users/blocked
# ---------------------------------------------------------------------------


@router.get("/users/blocked", response_model=BlockedListResponse)
def list_blocked_users(
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    claims: UserClaims = Depends(get_current_user),
    block_repo: BlockRepository = Depends(get_block_repo),
) -> BlockedListResponse:
    """List users blocked by the current user (paginated)."""
    user_id = claims["sub"]
    try:
        rows = block_repo.list_blocked(user_id, limit=limit, cursor=cursor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]

    next_cursor = (
        f"{rows[-1]['created_at']}|{rows[-1]['id']}" if has_more and rows else None
    )

    return BlockedListResponse(
        users=[
            BlockedUserResponse(
                id=r["id"],
                blocked_id=r["blocked_id"],
                display_name=(r.get("blocked_user") or {}).get("display_name"),
                username=(r.get("blocked_user") or {}).get("username"),
                created_at=r["created_at"],
            )
            for r in rows
        ],
        next_cursor=next_cursor,
        has_more=has_more,
    )
