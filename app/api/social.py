"""Social Feed & Reactions API.

Story 5-1:
  GET /feed — paginated feed (JWT required).

Story 5-2:
  POST /posts/{id}/react — react as an authenticated user (JWT required).
  Redis INCR (optimistic) + background DB write via ARQ.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from supabase import Client

from app.api.deps import (
    get_block_repo,
    get_client_ip,
    get_current_user,
    get_feed_repo,
    get_redis,
    get_supabase,
    require_app_feature,
)
from app.api.middleware.auth import UserClaims
from app.config import settings
from app.db.async_helpers import run_sync
from app.repositories.block_repo import BlockRepository
from app.repositories.feed_repo import FeedRepository
from app.services.public_url import build_avatar_url

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["social"],
    dependencies=[Depends(require_app_feature("social_enabled"))],
)


# Lua script: atomic INCR + conditional EXPIRE + limit check (L-2).
# Returns the new count if within limit, or 0 if the limit is exceeded.
_RATE_LIMIT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
end
if current > tonumber(ARGV[2]) then
    redis.call('DECR', KEYS[1])
    return 0
end
return 1
"""

# H-4: Atomic seed-and-increment Lua script for reaction counters.
# If the key does not exist, seed it from the DB value (ARGV[1]) and then
# increment by 1. If the key already exists, just increment.
# This eliminates the race window between SETNX and INCR.
_REACTION_SEED_AND_INCR_SCRIPT = """
local exists = redis.call('EXISTS', KEYS[1])
if exists == 0 then
    redis.call('SET', KEYS[1], tonumber(ARGV[1]))
end
return redis.call('INCR', KEYS[1])
"""

_DEFAULT_PAGE_SIZE = 10
_MAX_PAGE_SIZE = 50

# Redis mutex key shared with the retention cron. Acquired by
# ``reconcile_reaction_counts`` at 03:00 UTC; ``run_retention`` checks for it
# at 03:30 UTC and skips if held. Extracted to a module-level constant so both
# crons reference the exact same key without relying on string duplication.
RECONCILE_LOCK_KEY = "cron:reconcile_reactions:lock"


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
    username: str | None
    display_name: str | None
    avatar_url: str | None
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
async def get_feed(
    sort: FeedSort = Query(FeedSort.NEWEST, description="Sort strategy"),
    cursor: str | None = Query(
        None, description="Cursor for pagination (ISO timestamp or composite)"
    ),
    limit: int = Query(
        _DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE, description="Page size"
    ),
    claims: UserClaims = Depends(get_current_user),
    feed_repo: FeedRepository = Depends(get_feed_repo),
    block_repo: BlockRepository = Depends(get_block_repo),
    supabase: Client = Depends(get_supabase),
) -> FeedResponse:
    """Feed endpoint — JWT required.

    AC-D7: Posts with non-cleared images excluded.
    AC-U10: biggest_improvements uses reaction_count only, no AI scores.

    Posts from blocked/blocking users are excluded from the results.
    """
    excluded_user_ids: set[str] = await run_sync(
        block_repo.get_all_hidden_user_ids, claims["sub"]
    )

    # Fetch limit+1 to determine has_more
    fetch_limit = limit + 1

    # M-2: Wrap sync Supabase calls to avoid blocking the event loop
    if sort == FeedSort.NEWEST:
        posts = await run_sync(
            feed_repo.fetch_newest, cursor, fetch_limit, excluded_user_ids
        )
    elif sort == FeedSort.TRENDING:
        posts = await run_sync(
            feed_repo.fetch_trending, cursor, fetch_limit, excluded_user_ids
        )
    elif sort == FeedSort.BIGGEST_IMPROVEMENTS:
        posts = await run_sync(
            feed_repo.fetch_biggest_improvements, cursor, fetch_limit, excluded_user_ids
        )
    else:
        posts = await run_sync(
            feed_repo.fetch_newest, cursor, fetch_limit, excluded_user_ids
        )

    has_more = len(posts) > limit
    if has_more:
        posts = posts[:limit]

    # Build signed avatar URLs — batch unique storage keys to minimise calls
    unique_avatar_keys: dict[str, str | None] = {}
    for p in posts:
        key = p.get("avatar_storage_key")
        if key and key not in unique_avatar_keys:
            unique_avatar_keys[key] = build_avatar_url(supabase, key)

    # URLs are now stable public CDN paths (no signing needed)
    feed_posts = [
        FeedPostResponse(
            post_id=p["id"],
            user_id=p["user_id"],
            username=p.get("username"),
            display_name=p.get("display_name"),
            avatar_url=unique_avatar_keys.get(p.get("avatar_storage_key") or ""),
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
# POST /posts/{post_id}/reactions (Story 5-2) — canonical noun-based route
# POST /posts/{post_id}/react — deprecated alias (backward compat)
# ---------------------------------------------------------------------------

# Rate limit: 10 reactions per IP per 5 minutes
_REACTION_RATE_LIMIT = 10
_REACTION_RATE_WINDOW_SECONDS = 300


class ReactionResponse(BaseModel):
    reaction_count: int


@router.post("/posts/{post_id}/reactions", response_model=ReactionResponse)
async def react_to_post(
    post_id: UUID,
    request: Request,
    claims: UserClaims = Depends(get_current_user),
    feed_repo: FeedRepository = Depends(get_feed_repo),
    redis_client: aioredis.Redis = Depends(get_redis),
) -> ReactionResponse:
    """React to a post — JWT required.

    AC-U9: Duplicate reactions deduplicated via UNIQUE constraint.
    AC-A12: Rate limited at 10 reactions per IP per 5 minutes.
    """
    user_id = claims["sub"]

    # --- Rate limit by IP (atomic Lua script to avoid TOCTOU — L-2) ---
    client_ip = get_client_ip(request)
    rate_key = f"reaction_rate:{client_ip}"
    allowed = await redis_client.eval(
        _RATE_LIMIT_SCRIPT,
        1,
        rate_key,
        str(_REACTION_RATE_WINDOW_SECONDS),
        str(_REACTION_RATE_LIMIT),
    )
    if not allowed:
        ttl: int = await redis_client.ttl(rate_key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": {
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": "Too many reactions. Please slow down.",
                }
            },
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

    # H-4: Atomic seed-and-increment via Lua script. If the key does not exist,
    # seeds from the DB count and increments in one atomic operation, eliminating
    # the race window between SETNX and INCR.
    new_count = await redis_client.eval(
        _REACTION_SEED_AND_INCR_SCRIPT,
        1,
        redis_counter_key,
        str(post["reaction_count"]),
    )

    # --- Background DB write via ARQ ---
    reaction_data = {
        "post_id": str(post_id),
        "user_id": user_id,
    }

    arq_pool = request.app.state.arq_pool
    await arq_pool.enqueue_job(
        "persist_reaction",
        reaction_data,
        _queue_name="default",
    )

    return ReactionResponse(reaction_count=new_count)


@router.post(
    "/posts/{post_id}/react",
    response_model=ReactionResponse,
    deprecated=True,
    include_in_schema=True,
)
async def react_to_post_deprecated(
    post_id: UUID,
    request: Request,
    claims: UserClaims = Depends(get_current_user),
    feed_repo: FeedRepository = Depends(get_feed_repo),
    redis_client: aioredis.Redis = Depends(get_redis),
) -> ReactionResponse:
    """Deprecated alias — use POST /posts/{post_id}/reactions instead."""
    return await react_to_post(
        post_id=post_id,
        request=request,
        claims=claims,
        feed_repo=feed_repo,
        redis_client=redis_client,
    )


# ---------------------------------------------------------------------------
# ARQ worker functions for reactions (Story 5-2)
# ---------------------------------------------------------------------------


async def persist_reaction(ctx: dict, reaction_data: dict) -> None:
    """Background task: atomically insert reaction + update counter.

    On duplicate (UNIQUE constraint), RPC returns empty set — decrement Redis.
    """
    # Validate payload BEFORE loading the Supabase client so a malformed
    # job fails loudly without paying the cost of a DB connection and so
    # the error isn't masked by an env-loading exception.
    post_id = reaction_data.get("post_id")
    if not post_id:
        logger.error(
            "persist_reaction received payload without post_id: %r", reaction_data
        )
        raise ValueError("persist_reaction: post_id is required")

    user_id = reaction_data.get("user_id")
    if not user_id:
        # Defensive — reaction endpoint always sets user_id from claims["sub"].
        # A missing user_id would hit the reactions.user_id NOT NULL constraint
        # at the DB and each ARQ retry would over-decrement the Redis counter.
        # Fail loudly here so ARQ drops the job instead.
        logger.error(
            "persist_reaction received payload without user_id: %r", reaction_data
        )
        raise ValueError("persist_reaction: user_id is required")

    from app.db.client import get_supabase_service
    from app.repositories.feed_repo import FeedRepository

    supabase = get_supabase_service()
    feed_repo = FeedRepository(supabase)

    try:
        result = await run_sync(
            feed_repo.persist_reaction_atomic,
            post_id,
            reaction_data.get("user_id"),
        )

        if not result:
            # Duplicate reaction — undo optimistic Redis INCR
            redis_client = ctx.get("redis")
            if redis_client:
                await redis_client.decr(f"posts:{post_id}:reactions")
            logger.info(
                "Duplicate reaction for post %s — Redis counter decremented", post_id
            )

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

    Acquires a Redis mutex (``RECONCILE_LOCK_KEY``) at the top so the
    retention cron scheduled 30 min later skips if reconcile is still
    running. The lock is released in ``finally`` — including on failure —
    so a crashed run does not block subsequent retention passes forever
    (the lock TTL also bounds the worst case at
    ``RECONCILE_LOCK_TTL_SECONDS``).
    """
    if not settings.FEATURE_SOCIAL_ENABLED:
        logger.debug("Social disabled — skipping reaction count reconciliation")
        return

    from app.db.client import get_supabase_service
    from app.repositories.feed_repo import FeedRepository

    redis_client = ctx.get("redis")

    # Acquire the cross-cron mutex before doing any work. If another process
    # already holds it, silently skip — the next scheduled tick will retry.
    if redis_client is not None:
        acquired = await redis_client.set(
            RECONCILE_LOCK_KEY,
            "1",
            nx=True,
            ex=settings.RECONCILE_LOCK_TTL_SECONDS,
        )
        if not acquired:
            logger.warning(
                "reconcile_reaction_counts skipped: lock %s already held",
                RECONCILE_LOCK_KEY,
            )
            return

    try:
        supabase = get_supabase_service()
        feed_repo = FeedRepository(supabase)

        cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=2)).isoformat()

        updated_rows = await run_sync(feed_repo.reconcile_reaction_counts, cutoff)
        updated_ids = [row["id"] for row in updated_rows]

        # Invalidate Redis for reconciled posts so next read fetches fresh count
        if redis_client and updated_ids:
            keys = [f"posts:{pid}:reactions" for pid in updated_ids]
            await redis_client.delete(*keys)

        logger.info("Reconciled reaction counts for %d posts", len(updated_ids))
    finally:
        if redis_client is not None:
            await redis_client.delete(RECONCILE_LOCK_KEY)
