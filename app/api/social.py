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
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Annotated
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel
from supabase import Client

from app.api.deps import get_current_user, get_redis, get_supabase
from app.api.middleware.auth import UserClaims
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["social"])

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
    supabase: Client = Depends(get_supabase),
) -> FeedResponse:
    """Public feed endpoint — no auth required.

    AC-FR6: Zero authenticated API calls required.
    AC-D7: Posts with non-cleared images excluded.
    AC-U10: biggest_improvements uses reaction_count only, no AI scores.
    """
    # Fetch limit+1 to determine has_more
    fetch_limit = limit + 1

    if sort == FeedSort.NEWEST:
        posts = _fetch_newest(supabase, cursor, fetch_limit)
    elif sort == FeedSort.TRENDING:
        posts = _fetch_trending(supabase, cursor, fetch_limit)
    elif sort == FeedSort.BIGGEST_IMPROVEMENTS:
        posts = _fetch_biggest_improvements(supabase, cursor, fetch_limit)
    else:
        posts = _fetch_newest(supabase, cursor, fetch_limit)

    has_more = len(posts) > limit
    if has_more:
        posts = posts[:limit]

    # Generate fresh signed URLs at read time (P2-4: stored URLs expire)
    posts = _refresh_image_urls(supabase, posts)

    # Build response
    feed_posts = [
        FeedPostResponse(
            post_id=p["id"],
            user_id=p["user_id"],
            caption=p.get("caption"),
            before_image_url=p["_before_url"],
            after_image_url=p["_after_url"],
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
            score = _compute_trending_score(last)
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
# Sort strategy implementations
# ---------------------------------------------------------------------------

_POST_COLUMNS = (
    "id, user_id, caption, before_image_url, after_image_url, "
    "reaction_count, comment_count, created_at, "
    "before_image_id, after_image_id"
)


def _fetch_newest(supabase: Client, cursor: str | None, limit: int) -> list[dict]:
    """Fetch posts ordered by created_at DESC."""
    query = (
        supabase.table("posts")
        .select(_POST_COLUMNS)
        .eq("is_deleted", False)
        .order("created_at", desc=True)
        .limit(limit)
    )

    if cursor:
        query = query.lt("created_at", cursor)

    result = query.execute()
    return _filter_cleared_images(supabase, result.data or [])


def _fetch_trending(supabase: Client, cursor: str | None, limit: int) -> list[dict]:
    """Fetch posts ordered by HN-style time-decay score.

    score = reaction_count / POWER(hours_since_post + 2, 1.5)
    Computed in Python since Supabase PostgREST doesn't support computed ORDER BY.
    """
    # Fetch recent posts (last 7 days for trending, or more if cursor indicates)
    query = (
        supabase.table("posts")
        .select(_POST_COLUMNS)
        .eq("is_deleted", False)
        .order("created_at", desc=True)
        .limit(500)  # Pool for trending calculation
    )

    result = query.execute()
    posts = _filter_cleared_images(supabase, result.data or [])

    # Compute trending scores
    now = datetime.now(tz=timezone.utc)
    for post in posts:
        post["_trending_score"] = _compute_trending_score(post, now)

    # Sort by trending score descending
    posts.sort(key=lambda p: p["_trending_score"], reverse=True)

    # Apply cursor (skip past cursor position)
    if cursor:
        parts = cursor.split("|", 2)
        if len(parts) == 3:
            cursor_score = float(parts[0])
            cursor_created = parts[1]
            cursor_id = parts[2]
            # Skip posts until we're past the cursor
            found = False
            filtered = []
            for p in posts:
                if found:
                    filtered.append(p)
                elif p["id"] == cursor_id:
                    found = True
            posts = filtered

    return posts[:limit]


def _fetch_biggest_improvements(supabase: Client, cursor: str | None, limit: int) -> list[dict]:
    """Fetch posts ordered by reaction_count DESC (AC-U10: no AI scores)."""
    query = (
        supabase.table("posts")
        .select(_POST_COLUMNS)
        .eq("is_deleted", False)
        .order("reaction_count", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
    )

    if cursor:
        parts = cursor.split("|", 2)
        if len(parts) == 3:
            cursor_reactions = int(parts[0])
            cursor_created = parts[1]
            cursor_id = parts[2]
            # Posts with fewer reactions, or same reactions but older
            query = (
                supabase.table("posts")
                .select(_POST_COLUMNS)
                .eq("is_deleted", False)
                .lte("reaction_count", cursor_reactions)
                .order("reaction_count", desc=True)
                .order("created_at", desc=True)
                .limit(limit + cursor_reactions)  # Over-fetch to skip past cursor
            )
            result = query.execute()
            posts = _filter_cleared_images(supabase, result.data or [])

            # Skip past the cursor position
            found = False
            filtered = []
            for p in posts:
                if found:
                    filtered.append(p)
                elif p["id"] == cursor_id:
                    found = True
            return filtered[:limit]

    result = query.execute()
    return _filter_cleared_images(supabase, result.data or [])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_trending_score(post: dict, now: datetime | None = None) -> float:
    """HN-style time-decay: reaction_count / POWER(hours + 2, 1.5)."""
    if now is None:
        now = datetime.now(tz=timezone.utc)

    created = datetime.fromisoformat(post["created_at"])
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)

    hours = max(0, (now - created).total_seconds() / 3600)
    reactions = post.get("reaction_count", 0)
    return reactions / pow(hours + 2, 1.5)


def _refresh_image_urls(supabase: Client, posts: list[dict]) -> list[dict]:
    """Generate fresh signed URLs for post images (P2-4: stored URLs expire)."""
    if not posts:
        return posts

    image_ids: set[str] = set()
    for p in posts:
        image_ids.add(p["before_image_id"])
        image_ids.add(p["after_image_id"])

    result = (
        supabase.table("images")
        .select("id, storage_key, bucket")
        .in_("id", list(image_ids))
        .execute()
    )

    url_map: dict[str, str] = {}
    for img in (result.data or []):
        bucket = img.get("bucket", "raw-selfies")
        try:
            signed = supabase.storage.from_(bucket).create_signed_url(
                img["storage_key"], settings.SIGNED_URL_EXPIRY_SECONDS
            )["signedURL"]
            url_map[img["id"]] = signed
        except Exception:
            url_map[img["id"]] = ""

    for p in posts:
        p["_before_url"] = url_map.get(p["before_image_id"], p.get("before_image_url", ""))
        p["_after_url"] = url_map.get(p["after_image_id"], p.get("after_image_url", ""))

    return posts


def _filter_cleared_images(supabase: Client, posts: list[dict]) -> list[dict]:
    """Exclude posts where before or after image is not 'cleared' (AC-D7)."""
    if not posts:
        return posts

    # Collect all image IDs
    image_ids: set[str] = set()
    for p in posts:
        image_ids.add(p["before_image_id"])
        image_ids.add(p["after_image_id"])

    if not image_ids:
        return posts

    # Batch-fetch image statuses
    result = (
        supabase.table("images")
        .select("id, status")
        .in_("id", list(image_ids))
        .execute()
    )

    cleared_ids: set[str] = set()
    for img in (result.data or []):
        if img["status"] == "cleared":
            cleared_ids.add(img["id"])

    # Filter: both images must be cleared
    return [
        p for p in posts
        if p["before_image_id"] in cleared_ids and p["after_image_id"] in cleared_ids
    ]


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
    supabase: Client = Depends(get_supabase),
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
        guest_token = x_guest_token
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Provide Authorization header or X-Guest-Token",
        )

    # --- Rate limit by IP ---
    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"reaction_rate:{client_ip}"
    current_rate = int(await redis_client.get(rate_key) or 0)

    if current_rate >= _REACTION_RATE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": {"code": "RATE_LIMIT_EXCEEDED", "message": "Too many reactions. Please slow down."}},
        )

    # --- Verify post exists ---
    post = (
        supabase.table("posts")
        .select("id, reaction_count")
        .eq("id", str(post_id))
        .eq("is_deleted", False)
        .maybe_single()
        .execute()
    )
    if not post.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    # --- Optimistic Redis INCR ---
    redis_counter_key = f"posts:{post_id}:reactions"

    # Load from DB on cache miss
    cached = await redis_client.get(redis_counter_key)
    if cached is None:
        await redis_client.set(redis_counter_key, post.data["reaction_count"], ex=60)

    new_count = await redis_client.incr(redis_counter_key)

    # --- Increment rate limiter ---
    pipe = redis_client.pipeline()
    pipe.incr(rate_key)
    pipe.expire(rate_key, _REACTION_RATE_WINDOW_SECONDS)
    await pipe.execute()

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
    """Background task: insert reaction row and update post counter.

    On duplicate (UNIQUE constraint), decrements Redis counter.
    Retries up to 3 times on transient failures.
    """
    from app.db.client import get_supabase_service

    supabase = get_supabase_service()
    post_id = reaction_data["post_id"]

    try:
        supabase.table("reactions").insert({
            "post_id": post_id,
            "user_id": reaction_data.get("user_id"),
            "guest_session_token": reaction_data.get("guest_session_token"),
        }).execute()

        # Update canonical counter: read current count from reactions table
        count_result = (
            supabase.table("reactions")
            .select("id", count="exact")
            .eq("post_id", post_id)
            .execute()
        )
        actual_count = count_result.count or 0
        supabase.table("posts").update({
            "reaction_count": actual_count,
        }).eq("id", post_id).execute()

    except Exception as exc:
        if "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
            # Dedup: decrement the optimistic Redis INCR
            redis_client = ctx.get("redis")
            if redis_client:
                await redis_client.decr(f"posts:{post_id}:reactions")
            logger.info("Duplicate reaction for post %s — Redis counter decremented", post_id)
            return
        raise  # Let ARQ retry


async def reconcile_reaction_counts(ctx: dict) -> None:
    """Nightly reconciliation: sync posts.reaction_count and Redis from DB truth.

    Runs for all posts with reactions in the previous 48 hours.
    """
    from app.db.client import get_supabase_service

    supabase = get_supabase_service()
    redis_client = ctx.get("redis")

    # Find posts with recent reaction activity (48h)
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=2)).isoformat()
    recent_reactions = (
        supabase.table("reactions")
        .select("post_id")
        .gte("created_at", cutoff)
        .execute()
    )

    post_ids: set[str] = {r["post_id"] for r in (recent_reactions.data or [])}

    for pid in post_ids:
        # Count actual reactions from DB
        count_result = (
            supabase.table("reactions")
            .select("id", count="exact")
            .eq("post_id", pid)
            .execute()
        )
        actual_count = count_result.count or 0

        # Update posts.reaction_count
        supabase.table("posts").update({
            "reaction_count": actual_count,
        }).eq("id", pid).execute()

        # Update Redis
        if redis_client:
            await redis_client.set(f"posts:{pid}:reactions", actual_count, ex=60)

    logger.info("Reconciled reaction counts for %d posts", len(post_ids))
