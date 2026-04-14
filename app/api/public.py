"""Public (no-auth) API — Story 6-1: Shareable Card.

GET /api/public/cards
  Returns a cursor-paginated list of users with at least one public card.
  Sole consumer: card-web sitemap.

GET /api/public/cards/{username}
  Returns the latest published post for the given username.

GET /api/public/cards/{username}/{share_hash}
  Returns a specific post identified by its share hash.

  HTTP 200 — card data
  HTTP 404 — user exists but has no published posts / hash not found
  HTTP 410 — account deleted or post hard-deleted
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import (
    get_glowup_analysis_repo,
    get_job_repo,
    get_post_repo,
    get_user_repo,
)
from app.db.async_helpers import run_sync
from app.repositories.glowup_analysis_repo import GlowupAnalysisRepository
from app.repositories.job_repo import SOURCE_TYPE_GLOWUP, JobRepository
from app.repositories.post_repo import PostRepository
from app.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["public"])

# Keyset pagination bounds for GET /public/cards — the sitemap fetches in
# 1000-user pages.
PUBLIC_CARDS_MIN_PER_PAGE = 1
PUBLIC_CARDS_MAX_PER_PAGE = 1000
PUBLIC_CARDS_DEFAULT_PER_PAGE = 1000

# Cursor encoding: urlsafe base64 of JSON ``{"u": <iso8601>, "n": <username>}``.
_CURSOR_KEY_UPDATED_AT = "u"
_CURSOR_KEY_USERNAME = "n"
# Real cursors are ~80 chars; cap raw input at 1 KiB to block pathological
# base64 payloads before we allocate for decode/json.loads.
_CURSOR_MAX_RAW_LEN = 1024


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class RecommendationItem(BaseModel):
    rank: int
    category: str
    suggestion: str
    rationale: str | None = None


class CardResponse(BaseModel):
    username: str
    display_name: str
    share_hash: str
    before_image_url: str
    after_image_url: str
    recommendations: list[RecommendationItem]
    reaction_count: int
    comment_count: int


class PublicCardListItem(BaseModel):
    username: str
    updated_at: datetime


class PublicCardListResponse(BaseModel):
    items: list[PublicCardListItem]
    next_cursor: str | None


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------


def _encode_cursor(updated_at: datetime, username: str) -> str:
    """Encode a ``(updated_at, username)`` pair as an urlsafe-base64 JSON blob."""
    payload = json.dumps(
        {
            _CURSOR_KEY_UPDATED_AT: updated_at.isoformat(),
            _CURSOR_KEY_USERNAME: username,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _decode_cursor(raw: str) -> tuple[datetime, str]:
    """Decode an urlsafe-base64 JSON cursor into ``(updated_at, username)``.

    Raises ``HTTPException(400)`` when the cursor is structurally invalid —
    malformed base64, malformed JSON, missing keys, or an unparseable timestamp.
    Real cursors are ~80 chars; a 1 KiB ceiling blocks pathological payloads.
    """
    if len(raw) > _CURSOR_MAX_RAW_LEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed cursor",
        )
    try:
        padding = "=" * (-len(raw) % 4)
        decoded = base64.urlsafe_b64decode(raw + padding)
        payload = json.loads(decoded)
        updated_at_raw = payload[_CURSOR_KEY_UPDATED_AT]
        username = payload[_CURSOR_KEY_USERNAME]
        if not isinstance(updated_at_raw, str) or not isinstance(username, str):
            raise ValueError("cursor fields must be strings")
        updated_at = datetime.fromisoformat(updated_at_raw)
    except (
        binascii.Error,
        ValueError,
        KeyError,
        json.JSONDecodeError,
        TypeError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed cursor",
        ) from exc
    # Normalise to UTC so comparisons against Supabase-returned timestamptz
    # (which are always offset-aware) never raise TypeError. A cursor payload
    # without a timezone suffix gets UTC attached — not rejected — because
    # `_encode_cursor` always emits offset-aware ISO strings, so naive values
    # only appear from hand-crafted or mis-encoded inputs.
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return updated_at, username


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _fetch_recommendations(
    glow_up_job_id: str,
    job_repo: JobRepository,
    glowup_analysis_repo: GlowupAnalysisRepository,
) -> list[dict]:
    """Resolve recommendations for a post via the tier-3 schema.

    Flow: jobs.id → jobs.source_id (when source_type='glowup_analysis') →
    glowup_analyses.recommendations JSONB.
    """
    job_data = await run_sync(job_repo.get_by_id, glow_up_job_id)
    if not job_data:
        return []
    if job_data.get("source_type") != SOURCE_TYPE_GLOWUP:
        return []
    source_id: str | None = job_data.get("source_id")
    if not source_id:
        return []
    analysis = await run_sync(glowup_analysis_repo.get_by_id, source_id)
    if not analysis:
        return []
    return analysis.get("recommendations") or []


# ---------------------------------------------------------------------------
# GET /public/cards — paginated listing (card-web sitemap)
# ---------------------------------------------------------------------------


@router.get("/public/cards", response_model=PublicCardListResponse)
async def list_public_cards(
    cursor: str | None = None,
    per_page: int = Query(
        PUBLIC_CARDS_DEFAULT_PER_PAGE,
        ge=PUBLIC_CARDS_MIN_PER_PAGE,
        le=PUBLIC_CARDS_MAX_PER_PAGE,
    ),
    post_repo: PostRepository = Depends(get_post_repo),
) -> PublicCardListResponse:
    """List users with at least one public card, sorted by recency.

    Cursor-paginated keyset over ``(max(post.updated_at), username)``. The
    endpoint is unauthenticated — its sole consumer is the card-web sitemap.
    """
    decoded_cursor = _decode_cursor(cursor) if cursor else None

    rows = await run_sync(
        post_repo.list_public_user_cursor,
        decoded_cursor,
        per_page,
    )

    # The repo returns up to per_page+1 rows. The extra row signals a next page.
    next_cursor: str | None = None
    if len(rows) > per_page:
        last = rows[per_page - 1]
        next_cursor = _encode_cursor(last["updated_at"], last["username"])
        rows = rows[:per_page]

    items = [
        PublicCardListItem(username=row["username"], updated_at=row["updated_at"])
        for row in rows
    ]
    return PublicCardListResponse(items=items, next_cursor=next_cursor)


# ---------------------------------------------------------------------------
# GET /public/cards/{username}
# ---------------------------------------------------------------------------


@router.get("/public/cards/{username}", response_model=CardResponse)
async def get_shareable_card(
    username: str,
    user_repo: UserRepository = Depends(get_user_repo),
    post_repo: PostRepository = Depends(get_post_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    glowup_analysis_repo: GlowupAnalysisRepository = Depends(get_glowup_analysis_repo),
) -> CardResponse:
    """Return the shareable card for a user's latest published post.

    No authentication required — fully public endpoint.

    Raises:
        HTTP 410: account has been deleted.
        HTTP 404: user has no published posts.
    """
    # Step 1 — look up user by username
    # M-2: Wrap sync Supabase calls to avoid blocking the event loop
    user = await run_sync(user_repo.get_by_username_for_card, username)

    if not user:
        # Username not found — treat as Gone so callers don't leak enumeration
        # info while still being semantically correct for deleted accounts.
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Account not found or has been deleted",
        )

    if user.get("deleted_at") is not None:
        logger.info("Shareable card requested for deleted account: %s", username)
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Account not found or has been deleted",
        )

    user_id: str = user["id"]

    # Step 2 — latest non-deleted post for this user
    post = await run_sync(post_repo.get_latest_for_user, user_id)

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No published posts found for this user",
        )

    # Step 3 — resolve recommendations via tier-3 schema
    recommendations: list[dict] = []
    glow_up_job_id: str | None = post.get("glow_up_job_id")
    if glow_up_job_id:
        recommendations = await _fetch_recommendations(
            glow_up_job_id, job_repo, glowup_analysis_repo
        )

    logger.info(
        "Shareable card served for user %s (post %s, %d recommendations)",
        username,
        post["id"],
        len(recommendations),
    )

    # URLs are stable public CDN paths (no signing needed)
    return _build_card_response(user, post, recommendations)


@router.get("/public/cards/{username}/{share_hash}", response_model=CardResponse)
async def get_shareable_card_by_hash(
    username: str,
    share_hash: str,
    user_repo: UserRepository = Depends(get_user_repo),
    post_repo: PostRepository = Depends(get_post_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    glowup_analysis_repo: GlowupAnalysisRepository = Depends(get_glowup_analysis_repo),
) -> CardResponse:
    """Return a specific shareable card identified by its share hash.

    URL format: /{username}/glow-up/{share_hash}
    """
    user = await run_sync(user_repo.get_by_username_for_card, username)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Account not found or has been deleted",
        )

    if user.get("deleted_at") is not None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Account not found or has been deleted",
        )

    user_id: str = user["id"]

    post = await run_sync(post_repo.get_by_share_hash, user_id, share_hash)

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Glow-up not found",
        )

    recommendations: list[dict] = []
    glow_up_job_id: str | None = post.get("glow_up_job_id")
    if glow_up_job_id:
        recommendations = await _fetch_recommendations(
            glow_up_job_id, job_repo, glowup_analysis_repo
        )

    logger.info(
        "Shareable card served for %s/%s (post %s)",
        username,
        share_hash,
        post["id"],
    )

    return _build_card_response(user, post, recommendations)


def _build_card_response(
    user: dict,
    post: dict,
    recommendations: list[dict],
) -> CardResponse:
    return CardResponse(
        username=user["username"],
        display_name=user.get("display_name") or user["username"],
        share_hash=post["share_hash"],
        before_image_url=post["before_image_url"],
        after_image_url=post["after_image_url"],
        recommendations=[
            RecommendationItem(
                rank=r["rank"],
                category=r["category"],
                suggestion=r["suggestion_text"],
                rationale=r.get("rationale"),
            )
            for r in recommendations
        ],
        reaction_count=post["reaction_count"],
        comment_count=post["comment_count"],
    )
