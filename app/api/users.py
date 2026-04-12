"""User Profile & History API.

Story 6-3:
  GET  /users/{username}/profile  — public, no auth required
  GET  /users/{username}/history  — private, owner only
  PATCH /users/{username}         — update display_name, avatar, and/or username, owner only
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

import redis.asyncio as aioredis
from pydantic import BaseModel, Field

from app.api.deps import get_analysis_repo, get_client_ip, get_current_user, get_image_repo, get_job_repo, get_redis, get_user_repo
from app.api.public import RecommendationItem
from app.api.middleware.auth import UserClaims
from app.config import settings
from app.db.async_helpers import run_sync
from app.repositories.analysis_repo import AnalysisRepository
from app.repositories.image_repo import ImageRepository
from app.repositories.job_repo import JobRepository
from app.repositories.user_repo import UserRepository
from app.api.deps import require_app_feature

logger = logging.getLogger(__name__)

router = APIRouter(tags=["users"])

_DEFAULT_HISTORY_PAGE_SIZE = 20
_MAX_HISTORY_PAGE_SIZE = 100

_USERNAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")
_USERNAME_MIN_LENGTH = 3
_USERNAME_MAX_LENGTH = 30
_USERNAME_CHANGE_COOLDOWN_HOURS = 24
_USERNAME_CHECK_RATE_LIMIT = 30          # max requests per window
_USERNAME_CHECK_RATE_WINDOW_SECONDS = 60  # 1 minute


# ---------------------------------------------------------------------------
# Response / Request models
# ---------------------------------------------------------------------------


class UsernameAvailabilityResponse(BaseModel):
    available: bool
    reason: str | None = None


class ProfileResponse(BaseModel):
    username: str
    display_name: str
    avatar_url: str | None
    post_count: int
    total_reactions: int
    member_since: str


class HistoryEntry(BaseModel):
    analysis_id: str
    face_shape: str | None
    symmetry_score: float | None
    recommendations: list[RecommendationItem]
    before_image_url: str | None
    after_image_url: str | None
    created_at: str


class HistoryResponse(BaseModel):
    entries: list[HistoryEntry]
    next_cursor: str | None
    has_more: bool


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None
    avatar_storage_key: str | None = None
    new_username: str | None = Field(
        default=None,
        min_length=_USERNAME_MIN_LENGTH,
        max_length=_USERNAME_MAX_LENGTH,
        pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$",
    )


class UpdateProfileResponse(BaseModel):
    username: str
    display_name: str
    avatar_url: str | None
    username_change_cooldown_remaining_seconds: int | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lookup_user(user_repo: UserRepository, username: str) -> dict:
    """Fetch a non-deleted user by username. Raises 404 if missing."""
    data = user_repo.get_by_username(username)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return data


# ---------------------------------------------------------------------------
# GET /users/check-username  (public, no auth)
# ---------------------------------------------------------------------------


@router.get("/users/check-username", response_model=UsernameAvailabilityResponse)
async def check_username(
    request: Request,
    username: str = Query(min_length=_USERNAME_MIN_LENGTH, max_length=_USERNAME_MAX_LENGTH),
    user_repo: UserRepository = Depends(get_user_repo),
    r: aioredis.Redis = Depends(get_redis),
) -> UsernameAvailabilityResponse:
    """Check if a username is available (case-insensitive).

    No auth required. Per-IP rate limited to prevent username enumeration.
    """
    # Per-IP rate limit to prevent enumeration
    client_ip = get_client_ip(request) or "unknown"
    rate_key = f"username_check:{client_ip}"
    current = await r.incr(rate_key)
    if current == 1:
        await r.expire(rate_key, _USERNAME_CHECK_RATE_WINDOW_SECONDS)
    if current > _USERNAME_CHECK_RATE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please slow down.",
        )

    if not _USERNAME_PATTERN.match(username):
        return UsernameAvailabilityResponse(available=False, reason="invalid")

    result = await run_sync(user_repo.check_username_available_ci, username)
    return UsernameAvailabilityResponse(**result)


# ---------------------------------------------------------------------------
# GET /users/{username}/profile  (public)
# ---------------------------------------------------------------------------


@router.get(
    "/users/{username}/profile",
    response_model=ProfileResponse,
    dependencies=[Depends(require_app_feature("social_enabled"))],
)
async def get_user_profile(
    username: str,
    user_repo: UserRepository = Depends(get_user_repo),
    image_repo: ImageRepository = Depends(get_image_repo),
) -> ProfileResponse:
    """Return public profile stats for the given username.

    No auth required. Returns 404 for deleted or non-existent users.
    """
    # M-2: Wrap sync Supabase calls to avoid blocking the event loop
    user = await run_sync(_lookup_user, user_repo, username)
    user_id: str = user["id"]

    # Aggregate post_count and total_reactions via DB function (single query)
    stats = await run_sync(user_repo.get_user_post_stats, user_id)
    post_count = stats.get("post_count", 0)
    total_reactions = stats.get("total_reactions", 0)

    avatar_storage_key = user.get("avatar_storage_key")
    avatar_url = (
        await run_sync(image_repo.build_avatar_signed_url, avatar_storage_key, settings.SIGNED_URL_EXPIRY_SECONDS)
        if avatar_storage_key
        else None
    )

    logger.debug("Profile viewed for user %s", user_id)

    return ProfileResponse(
        username=user["username"],
        display_name=user["display_name"],
        avatar_url=avatar_url,
        post_count=post_count,
        total_reactions=total_reactions,
        member_since=user["created_at"],
    )


# ---------------------------------------------------------------------------
# GET /users/{username}/history  (owner only)
# ---------------------------------------------------------------------------


@router.get("/users/{username}/history", response_model=HistoryResponse)
async def get_user_history(
    username: str,
    cursor: str | None = Query(None, description="Cursor ({created_at}|{id} composite)"),
    limit: int = Query(
        _DEFAULT_HISTORY_PAGE_SIZE,
        ge=1,
        le=_MAX_HISTORY_PAGE_SIZE,
        description="Page size",
    ),
    claims: UserClaims = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_user_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    image_repo: ImageRepository = Depends(get_image_repo),
    analysis_repo: AnalysisRepository = Depends(get_analysis_repo),
) -> HistoryResponse:
    """Return the authenticated user's analysis history in reverse chronological order.

    Owner only — returns 403 if the token does not belong to the requested user.
    Cursor-paginated using created_at timestamp.
    """
    # M-2: Wrap sync Supabase calls to avoid blocking the event loop
    user = await run_sync(_lookup_user, user_repo, username)
    user_id: str = user["id"]

    if claims["sub"] != user_id:
        # Return 404 (not 403) to prevent user enumeration (L-1)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )

    fetch_limit = limit + 1

    analyses = await run_sync(analysis_repo.list_for_user, user_id, fetch_limit, cursor)

    has_more = len(analyses) > limit
    if has_more:
        analyses = analyses[:limit]

    next_cursor: str | None = (
        f"{analyses[-1]['created_at']}|{analyses[-1]['id']}"
        if has_more and analyses
        else None
    )

    # -- Batch-fetch related data instead of N+1 per-analysis queries ----------

    analysis_ids = [row["id"] for row in analyses]

    # 1. Collect original_image_ids from analyses and fetch all in one query
    original_image_ids = [
        row["original_image_id"] for row in analyses if row.get("original_image_id")
    ]
    before_images_by_id: dict[str, dict] = {}
    if original_image_ids:
        for img in await run_sync(image_repo.get_by_ids, original_image_ids):
            if img.get("storage_key"):
                before_images_by_id[img["id"]] = img

    # 2. Fetch latest completed glow_up_job per analysis in one query.
    #    PostgREST doesn't support DISTINCT ON, so fetch all completed jobs
    #    for these analyses and pick the latest per analysis_id in Python.
    jobs_by_analysis: dict[str, str] = {}  # analysis_id -> generated_image_id
    if analysis_ids:
        for job in await run_sync(job_repo.get_completed_jobs_for_analyses, analysis_ids):
            aid = job["analysis_id"]
            # First seen per analysis_id is the latest (ordered desc)
            if aid not in jobs_by_analysis and job.get("generated_image_id"):
                jobs_by_analysis[aid] = job["generated_image_id"]

    # 3. Fetch all generated images in one query
    generated_image_ids = list(jobs_by_analysis.values())
    after_images_by_id: dict[str, dict] = {}
    if generated_image_ids:
        for img in await run_sync(image_repo.get_by_ids, generated_image_ids):
            if img.get("storage_key"):
                after_images_by_id[img["id"]] = img

    # 4. Batch-sign all URLs, grouped by bucket to minimise overhead
    def _sign_url(bucket: str, storage_key: str) -> str | None:
        try:
            return image_repo.create_signed_url(bucket, storage_key, settings.SIGNED_URL_EXPIRY_SECONDS)
        except Exception:
            logger.warning("Failed to sign URL: bucket=%s key=%s", bucket, storage_key, exc_info=True)
            return None

    signed_before: dict[str, str | None] = {}
    for img_id, img in before_images_by_id.items():
        bucket = img.get("bucket") or "raw-selfies"
        signed_before[img_id] = _sign_url(bucket, img["storage_key"])

    signed_after: dict[str, str | None] = {}
    for img_id, img in after_images_by_id.items():
        bucket = img.get("bucket") or "generated-images"
        signed_after[img_id] = _sign_url(bucket, img["storage_key"])

    # 5. Assemble entries using the pre-fetched lookups
    entries: list[HistoryEntry] = []
    for row in analyses:
        before_url: str | None = None
        after_url: str | None = None

        orig_id = row.get("original_image_id")
        if orig_id and orig_id in signed_before:
            before_url = signed_before[orig_id]

        gen_id = jobs_by_analysis.get(row["id"])
        if gen_id and gen_id in signed_after:
            after_url = signed_after[gen_id]

        entries.append(
            HistoryEntry(
                analysis_id=row["id"],
                face_shape=row.get("face_shape"),
                symmetry_score=row.get("symmetry_score"),
                recommendations=[
                    RecommendationItem(
                        rank=r["rank"],
                        category=r["category"],
                        suggestion=r["suggestion_text"],
                        rationale=r.get("rationale"),
                    )
                    for r in (row.get("recommendations") or [])
                ],
                before_image_url=before_url,
                after_image_url=after_url,
                created_at=row["created_at"],
            )
        )

    logger.info(
        "History fetched for user %s: %d entries (has_more=%s)", user_id, len(entries), has_more
    )

    return HistoryResponse(
        entries=entries,
        next_cursor=next_cursor,
        has_more=has_more,
    )


# ---------------------------------------------------------------------------
# PATCH /users/{username}  (owner only)
# ---------------------------------------------------------------------------


@router.patch("/users/{username}", response_model=UpdateProfileResponse)
async def update_user_profile(
    username: str,
    body: UpdateProfileRequest,
    claims: UserClaims = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_user_repo),
    image_repo: ImageRepository = Depends(get_image_repo),
) -> UpdateProfileResponse:
    """Update the authenticated user's profile (display_name, avatar, username).

    Owner only — returns 404 if the token does not belong to the requested user.
    Username changes are subject to a 24-hour cooldown enforced via username_changed_at.
    """
    # M-2: Wrap sync Supabase calls to avoid blocking the event loop
    user = await run_sync(_lookup_user, user_repo, username)
    user_id: str = user["id"]

    if claims["sub"] != user_id:
        # Return 404 (not 403) to prevent user enumeration (L-1)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )

    updates: dict = {}
    if body.display_name is not None:
        updates["display_name"] = body.display_name
    if body.avatar_storage_key is not None:
        avatar_pattern = rf"^avatars/{re.escape(user_id)}/[a-zA-Z0-9_\-]+\.(jpg|jpeg|png|webp)$"
        if not re.match(avatar_pattern, body.avatar_storage_key):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid avatar storage key",
            )
        updates["avatar_storage_key"] = body.avatar_storage_key

    if updates:
        updates["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
        await run_sync(user_repo.update_profile, user_id, updates)
        logger.info("Profile updated for user %s: fields=%s", user_id, list(updates.keys()))

    # --- Username change (with cooldown) ---
    if body.new_username is not None and body.new_username != user["username"]:
        # Enforce cooldown
        username_changed_at_str = user.get("username_changed_at")
        if username_changed_at_str:
            last_change = datetime.fromisoformat(username_changed_at_str)
            if last_change.tzinfo is None:
                last_change = last_change.replace(tzinfo=timezone.utc)
            cooldown_end = last_change + timedelta(hours=_USERNAME_CHANGE_COOLDOWN_HOURS)
            now = datetime.now(tz=timezone.utc)
            if now < cooldown_end:
                remaining = int((cooldown_end - now).total_seconds())
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Username can only be changed once every 24 hours.",
                    headers={"Retry-After": str(remaining)},
                )

        # Check availability (case-insensitive)
        availability = await run_sync(
            user_repo.check_username_available_ci,
            body.new_username,
            user_id,
        )
        if not availability["available"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Username is {availability.get('reason', 'unavailable')}.",
            )

        # Apply username change atomically
        try:
            await run_sync(user_repo.update_username, user_id, body.new_username)
        except Exception as exc:
            if "unique" in str(exc).lower():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Username is taken.",
                ) from exc
            raise

    # Re-fetch by ID (not username) — the old username from the URL path
    # may no longer exist after a rename.
    refreshed = await run_sync(user_repo.get_profile_by_id, user_id)
    if not refreshed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    refreshed_avatar_key = refreshed.get("avatar_storage_key")
    avatar_url = (
        await run_sync(image_repo.build_avatar_signed_url, refreshed_avatar_key, settings.SIGNED_URL_EXPIRY_SECONDS)
        if refreshed_avatar_key
        else None
    )

    # Compute cooldown remaining for response
    cooldown_remaining: int | None = None
    changed_at_str = refreshed.get("username_changed_at") if refreshed else None
    if changed_at_str:
        last = datetime.fromisoformat(changed_at_str)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        end = last + timedelta(hours=_USERNAME_CHANGE_COOLDOWN_HOURS)
        remaining_secs = int((end - datetime.now(tz=timezone.utc)).total_seconds())
        if remaining_secs > 0:
            cooldown_remaining = remaining_secs

    return UpdateProfileResponse(
        username=refreshed["username"],
        display_name=refreshed["display_name"],
        avatar_url=avatar_url,
        username_change_cooldown_remaining_seconds=cooldown_remaining,
    )
