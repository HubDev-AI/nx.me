"""Social Feed & Reactions API.

Story 5-1:
  GET /feed — paginated feed with newest, trending, biggest_improvements sort.
  No auth required — guest users can browse the feed (AC-FR6).

Story 5-2:
  POST /posts/{id}/react — react with guest token or JWT auth.
  Redis INCR (optimistic) + background DB write via ARQ.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Annotated
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel

from app.api.deps import get_feed_repo, get_redis
from app.db.async_helpers import run_sync
from app.repositories.feed_repo import FeedRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["social"])

_GUEST_TOKEN_RE = re.compile(r"^[0-9a-f]{64}$")

_DEFAULT_PAGE_SIZE = 10
_MAX_PAGE_SIZE = 50


class FeedSort(StrEnum):
    NEWEST = "newest"
    TRENDING = "trending"
    BIGGEST_IMPROVEMENTS = "biggest_improvements"


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class FeedPostResponse(BaseModel):
    post_id: str
    user_id: str
    caption: str | None
    before_image_url: str
    after_image_url: str
    reaction_count: int
    comment_count: int
    created_at: str


class FeedResponse(BaseModel):
    posts: list[FeedPostResponse]
    next_cursor: str | None
    has_more: bool


# ---------------------------------------------------------------------------
# GET /feed
# ---------------------------------------------------------------------------


@router.get("/feed", response_model=FeedResponse)
def get_feed(
    sort: FeedSort = Query(FeedSort.NEWEST, description="Sort strategy"),
    cursor: str | None = Query(None, description="Cursor for pagination (ISO timestamp or composite)"),
    limit: int = Query(_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE, description="Page size"),
    feed_repo: FeedRepository = Depends(get_feed_repo),
) -> FeedResponse:
    """Public feed endpoint — no auth required.

    AC-FR6: Zero authenticated API calls required.
    AC-D7: Posts with non-cleared images excluded.
    AC-U10: biggest_improvements uses reaction_count only, no AI scores.
    """
    # Fetch limit+1 to determine has_more
    fetch_limit = limit + 1

    if sort == FeedSort.NEWEST:
        posts = feed_repo.fetch_newest(cursor, fetch_limit)
    elif sort == FeedSort.TRENDING:
        posts = feed_repo.fetch_trending(cursor, fetch_limit)
    elif sort == FeedSort.BIGGEST_IMPROVEMENTS:
        posts = feed_repo.fetch_biggest_improvements(cursor, fetch_limit)
    else:
        posts = feed_repo.fetch_newest(cursor, fetch_limit)

    has_more = len(posts) > limit
    if has_more:
        posts = posts[:limit]

    # URLs are now stable public CDN paths (no signing needed)
    feed_posts = [
        FeedPostResponse(
            post_id=p["id"],
            user_id=p["user_id"],
            caption=p.get("caption"),
            before_image_url=p["before_image_url"],
            after_image_url=p["after_image_url"],
            reaction_count=p["reaction_count"],
            comment_count=p["comment_count"],
            created_at=p["created_at"],
        )
        for p in posts
    ]

    # Compute next cursor
    next_cursor: str | None = None
    if has_more and posts:
        last = posts[-1]
        if sort == FeedSort.NEWEST:
            next_cursor = last["created_at"]
        elif sort == FeedSort.TRENDING:
            # Composite cursor: score|created_at|id
            # trending_score is computed by the SQL function
            score = last.get("trending_score", 0.0)
            next_cursor = f"{score:.6f}|{last['created_at']}|{last['id']}"
        elif sort == FeedSort.BIGGEST_IMPROVEMENTS:
            # Composite cursor: reaction_count|created_at|id
            next_cursor = f"{last['reaction_count']}|{last['created_at']}|{last['id']}"

    return FeedResponse(
        posts=feed_posts,
        next_cursor=next_cursor,
        has_more=has_more,
    )


# ---------------------------------------------------------------------------
# POST /posts/{post_id}/react (Story 5-2)
# ---------------------------------------------------------------------------

# Rate limit: 10 reactions per IP per 5 minutes
_REACTION_RATE_LIMIT = 10
_REACTION_RATE_WINDOW_SECONDS = 300


class ReactionResponse(BaseModel):
    reaction_count: int


@router.post("/posts/{post_id}/react", response_model=ReactionResponse)
async def react_to_post(
    post_id: UUID,
    request: Request,
    x_guest_token: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
    feed_repo: FeedRepository = Depends(get_feed_repo),
    redis_client: aioredis.Redis = Depends(get_redis),
) -> ReactionResponse:
    """React to a post — guest (X-Guest-Token) or authenticated (JWT).

    AC-U9: Duplicate reactions deduplicated via UNIQUE constraint.
    AC-A12: Rate limited at 10 reactions per IP per 5 minutes.
    """
    # --- Identify reactor: guest token or JWT ---
    user_id: str | None = None
    guest_token: str | None = None

    if authorization and authorization.startswith("Bearer "):
        from app.api.middleware.auth import validate_jwt
        claims = validate_jwt(authorization.removeprefix("Bearer ").strip())
        user_id = claims["sub"]
    elif x_guest_token:
        # Validate format: must be 64-char hex (32 bytes CSPRNG)
        if not _GUEST_TOKEN_RE.fullmatch(x_guest_token):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid guest token format",
            )
        guest_token = x_guest_token
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Provide Authorization header or X-Guest-Token",
        )

    # --- Rate limit by IP (atomic INCR-first to avoid TOCTOU) ---
    if not request.client:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot determine client IP address",
        )
    client_ip = request.client.host
    rate_key = f"reaction_rate:{client_ip}"
    new_count = await redis_client.incr(rate_key)
    if new_count == 1:
        await redis_client.expire(rate_key, _REACTION_RATE_WINDOW_SECONDS)

    if new_count > _REACTION_RATE_LIMIT:
        await redis_client.decr(rate_key)
        ttl: int = await redis_client.ttl(rate_key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": {"code": "RATE_LIMIT_EXCEEDED", "message": "Too many reactions. Please slow down."}},
            headers={"Retry-After": str(max(ttl, 0))},
        )

    # --- Verify post exists ---
    post = await run_sync(feed_repo.get_post_for_reaction, str(post_id))
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    # --- Optimistic Redis INCR ---
    redis_counter_key = f"posts:{post_id}:reactions"

    # Seed from DB on cache miss using SETNX to avoid overwriting a concurrent write,
    # then always INCR — eliminates the race between SET and INCR.
    await redis_client.setnx(redis_counter_key, post["reaction_count"])
    new_count = await redis_client.incr(redis_counter_key)

    # --- Background DB write via ARQ ---
    reaction_data = {
        "post_id": str(post_id),
        "user_id": user_id,
        "guest_session_token": guest_token,
    }

    arq_pool = request.app.state.arq_pool
    await arq_pool.enqueue_job(
        "persist_reaction",
        reaction_data,
        _queue_name="default",
    )

    return ReactionResponse(reaction_count=new_count)


# ---------------------------------------------------------------------------
# ARQ worker functions for reactions (Story 5-2)
# ---------------------------------------------------------------------------


async def persist_reaction(ctx: dict, reaction_data: dict) -> None:
    """Background task: atomically insert reaction + update counter.

    On duplicate (UNIQUE constraint), RPC returns empty set — decrement Redis.
    """
    from app.db.client import get_supabase_service
    from app.repositories.feed_repo import FeedRepository

    supabase = get_supabase_service()
    feed_repo = FeedRepository(supabase)
    post_id = reaction_data["post_id"]

    try:
        result = await run_sync(
            feed_repo.persist_reaction_atomic,
            post_id,
            reaction_data.get("user_id"),
            reaction_data.get("guest_session_token"),
        )

        if not result:
            # Duplicate reaction — undo optimistic Redis INCR
            redis_client = ctx.get("redis")
            if redis_client:
                await redis_client.decr(f"posts:{post_id}:reactions")
            logger.info("Duplicate reaction for post %s — Redis counter decremented", post_id)

    except Exception:
        # Transient failure: undo Redis optimistic increment before retry
        redis_client = ctx.get("redis")
        if redis_client:
            await redis_client.decr(f"posts:{post_id}:reactions")
        raise  # Let ARQ retry


async def reconcile_reaction_counts(ctx: dict) -> None:
    """Nightly reconciliation: sync posts.reaction_count from DB truth.

    Single SQL statement via RPC — no per-post loop.
    Runs for all posts with reactions in the previous 48 hours.
    """
    from app.db.client import get_supabase_service
    from app.repositories.feed_repo import FeedRepository

    supabase = get_supabase_service()
    feed_repo = FeedRepository(supabase)
    redis_client = ctx.get("redis")

    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=2)).isoformat()

    updated_rows = await run_sync(feed_repo.reconcile_reaction_counts, cutoff)
    updated_ids = [row["id"] for row in updated_rows]

    # Invalidate Redis for reconciled posts so next read fetches fresh count
    if redis_client and updated_ids:
        keys = [f"posts:{pid}:reactions" for pid in updated_ids]
        await redis_client.delete(*keys)

    logger.info("Reconciled reaction counts for %d posts", len(updated_ids))
