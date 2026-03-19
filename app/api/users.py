"""User Profile & History API.

Story 6-3:
  GET  /users/{username}/profile  — public, no auth required
  GET  /users/{username}/history  — private, owner only
  PATCH /users/{username}         — update display_name and/or avatar, owner only
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import get_analysis_repo, get_current_user, get_image_repo, get_job_repo, get_user_repo
from app.api.public import RecommendationItem
from app.api.middleware.auth import UserClaims
from app.config import settings
from app.db.async_helpers import run_sync
from app.repositories.analysis_repo import AnalysisRepository
from app.repositories.image_repo import ImageRepository
from app.repositories.job_repo import JobRepository
from app.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["users"])

_DEFAULT_HISTORY_PAGE_SIZE = 20
_MAX_HISTORY_PAGE_SIZE = 100


# ---------------------------------------------------------------------------
# Response / Request models
# ---------------------------------------------------------------------------


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


class UpdateProfileResponse(BaseModel):
    username: str
    display_name: str
    avatar_url: str | None


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
# GET /users/{username}/profile  (public)
# ---------------------------------------------------------------------------


@router.get("/users/{username}/profile", response_model=ProfileResponse)
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
                recommendations=row.get("recommendations") or [],
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
    """Update the authenticated user's display_name and/or avatar.

    Owner only — returns 403 if the token does not belong to the requested user.
    Username cannot be changed via this endpoint; any username field in the body
    is silently ignored per AC.
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

    # Re-fetch to return the current state
    refreshed = await run_sync(_lookup_user, user_repo, username)
    refreshed_avatar_key = refreshed.get("avatar_storage_key")
    avatar_url = (
        await run_sync(image_repo.build_avatar_signed_url, refreshed_avatar_key, settings.SIGNED_URL_EXPIRY_SECONDS)
        if refreshed_avatar_key
        else None
    )

    return UpdateProfileResponse(
        username=refreshed["username"],
        display_name=refreshed["display_name"],
        avatar_url=avatar_url,
    )
