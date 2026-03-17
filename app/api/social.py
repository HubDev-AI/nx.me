"""Social Feed API — public feed with sort strategies and cursor pagination.

Story 5-1:
  GET /feed — paginated feed with newest, trending, biggest_improvements sort.
  No auth required — guest users can browse the feed (AC-FR6).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import StrEnum

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from supabase import Client

from app.api.deps import get_supabase

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

    # Build response
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
