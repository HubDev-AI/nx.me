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

import hashlib

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel
from supabase import Client

from app.api.deps import (
    get_block_repo,
    get_client_ip,
    get_feed_repo,
    get_redis,
    get_supabase,
    require_app_feature,
)
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


_GUEST_TOKEN_RE = re.compile(r"^[0-9a-f]{64}$")

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
    authorization: Annotated[str | None, Header()] = None,
    feed_repo: FeedRepository = Depends(get_feed_repo),
    block_repo: BlockRepository = Depends(get_block_repo),
    supabase: Client = Depends(get_supabase),
) -> FeedResponse:
    """Public feed endpoint — no auth required.

    AC-FR6: Zero authenticated API calls required.
    AC-D7: Posts with non-cleared images excluded.
    AC-U10: biggest_improvements uses reaction_count only, no AI scores.

    If the caller provides a valid JWT, posts from blocked/blocking users
    are excluded from the results.
    """
    # Optional auth: if a valid JWT is present, resolve blocked user IDs
    excluded_user_ids: set[str] = set()
    if authorization and authorization.startswith("Bearer "):
        try:
            from app.api.middleware.auth import validate_jwt

            claims = validate_jwt(authorization.removeprefix("Bearer ").strip())
            user_id = claims["sub"]
            excluded_user_ids = await run_sync(
                block_repo.get_all_hidden_user_ids, user_id
            )
        except Exception:
            # Invalid/expired token on a public endpoint — proceed without filtering
            pass

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


async def validate_guest_token(redis_client: aioredis.Redis, token: str) -> bool:
    """Register a guest session token on first use and enforce per-token rate limit.

    Tokens are stored as SHA-256 hashes (first 32 hex chars) so raw tokens are
    never persisted in Redis.

    Returns True if the token is valid and within the per-token reaction limit.
    Returns False if the token has exceeded GUEST_REACTION_LIMIT reactions within
    GUEST_TOKEN_TTL_SECONDS.
    """
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    # Register token idempotently — NX means "only set if not exists"
    registration_key = f"guest_token:{token_hash}"
    await redis_client.set(
        registration_key, "1", ex=settings.GUEST_TOKEN_TTL_SECONDS, nx=True
    )

    # Rate limit counter — expire on first write to align with registration window
    count_key = f"guest_reactions:{token_hash}"
    count = await redis_client.incr(count_key)
    if count == 1:
        await redis_client.expire(count_key, settings.GUEST_TOKEN_TTL_SECONDS)

    return count <= settings.GUEST_REACTION_LIMIT


class ReactionResponse(BaseModel):
    reaction_count: int


@router.post("/posts/{post_id}/reactions", response_model=ReactionResponse)
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
        # Server-side token registry + per-token rate limit (LR-8)
        token_allowed = await validate_guest_token(redis_client, guest_token)
        if not token_allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": {
                        "code": "GUEST_RATE_LIMIT_EXCEEDED",
                        "message": "Guest reaction limit reached. Try again later.",
                    }
                },
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Provide Authorization header or X-Guest-Token",
        )

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
        "guest_session_token": guest_token,
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
    x_guest_token: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
    feed_repo: FeedRepository = Depends(get_feed_repo),
    redis_client: aioredis.Redis = Depends(get_redis),
) -> ReactionResponse:
    """Deprecated alias — use POST /posts/{post_id}/reactions instead."""
    return await react_to_post(
        post_id=post_id,
        request=request,
        x_guest_token=x_guest_token,
        authorization=authorization,
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
