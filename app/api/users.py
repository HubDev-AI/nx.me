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

from app.api.deps import (
    get_client_ip,
    get_current_user,
    get_glowup_analysis_repo,
    get_image_repo,
    get_job_repo,
    get_redis,
    get_upload_repo,
    get_user_or_guest,
    get_user_repo,
)
from app.api.public import RecommendationItem
from app.api.middleware.auth import UserClaims
from app.config import settings
from app.db.async_helpers import run_sync
from app.repositories.glowup_analysis_repo import GlowupAnalysisRepository
from app.repositories.image_repo import ImageRepository
from app.repositories.job_repo import SOURCE_TYPE_GLOWUP, JobRepository
from app.repositories.upload_repo import UploadRepository
from app.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["users"])

_DEFAULT_HISTORY_PAGE_SIZE = 20
_MAX_HISTORY_PAGE_SIZE = 100

_USERNAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")
_USERNAME_MIN_LENGTH = 3
_USERNAME_MAX_LENGTH = 30
_USERNAME_CHANGE_COOLDOWN_HOURS = 24
_USERNAME_CHECK_RATE_LIMIT = 30  # max requests per window
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


class MeResponse(BaseModel):
    """Identity payload for the current session — JWT user or guest token."""

    username: str
    display_name: str
    avatar_url: str | None


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
    username: str = Query(
        min_length=_USERNAME_MIN_LENGTH, max_length=_USERNAME_MAX_LENGTH
    ),
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
# GET /users/me  — identity for the current session (JWT user or guest token)
# ---------------------------------------------------------------------------
# Declared BEFORE /users/{username}/profile so path matching prefers the
# static "me" segment over the path-param branch.


@router.get("/users/me", response_model=MeResponse)
async def get_me(
    claims: UserClaims = Depends(get_user_or_guest),
    user_repo: UserRepository = Depends(get_user_repo),
    image_repo: ImageRepository = Depends(get_image_repo),
) -> MeResponse:
    """Return the current session's identity (username, display_name, avatar).

    Accepts either a JWT (real user) or X-Guest-Token (guest, when
    FEATURE_AUTH_REQUIRED=false). Mobile uses this to learn its own username
    after guest provisioning so screens like profile.tsx can call
    /users/{username}/profile.
    """
    user = await run_sync(user_repo.get_profile_by_id, claims["sub"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    avatar_storage_key = user.get("avatar_storage_key")
    avatar_url = (
        await run_sync(
            image_repo.build_avatar_signed_url,
            avatar_storage_key,
            settings.SIGNED_URL_EXPIRY_SECONDS,
        )
        if avatar_storage_key
        else None
    )
    return MeResponse(
        username=user["username"],
        display_name=user["display_name"],
        avatar_url=avatar_url,
    )


# ---------------------------------------------------------------------------
# GET /users/{username}/profile  (public)
# ---------------------------------------------------------------------------


@router.get(
    "/users/{username}/profile",
    response_model=ProfileResponse,
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
        await run_sync(
            image_repo.build_avatar_signed_url,
            avatar_storage_key,
            settings.SIGNED_URL_EXPIRY_SECONDS,
        )
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
    cursor: str | None = Query(
        None, description="Cursor ({created_at}|{id} composite)"
    ),
    limit: int = Query(
        _DEFAULT_HISTORY_PAGE_SIZE,
        ge=1,
        le=_MAX_HISTORY_PAGE_SIZE,
        description="Page size",
    ),
    claims: UserClaims = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_user_repo),
    upload_repo: UploadRepository = Depends(get_upload_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    glowup_analysis_repo: GlowupAnalysisRepository = Depends(get_glowup_analysis_repo),
) -> HistoryResponse:
    """Return the authenticated user's glow-up history in reverse chronological order.

    Owner only — returns 404 if the token does not belong to the requested user.
    Cursor-paginated using created_at timestamp.

    History = uploads that have a glowup_analyses row and at least one completed job.
    The before_image_url comes directly from uploads.image_url; the after_image_url
    comes from jobs.after_image_url of the most recent completed job.
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

    uploads = await run_sync(upload_repo.list_for_user, user_id, fetch_limit, cursor)

    has_more = len(uploads) > limit
    if has_more:
        uploads = uploads[:limit]

    next_cursor: str | None = (
        f"{uploads[-1]['created_at']}|{uploads[-1]['id']}"
        if has_more and uploads
        else None
    )

    # -- Batch-fetch related data instead of N+1 per-upload queries ----------

    upload_ids = [row["id"] for row in uploads]

    # 1. Fetch glowup_analyses for these uploads (one per upload, unique index).
    #    Build upload_id → analysis mapping for later assembly.
    analysis_by_upload: dict[str, dict] = {}
    if upload_ids:
        for analysis in await run_sync(
            lambda: (
                glowup_analysis_repo._sb.table("glowup_analyses")
                .select("id, upload_id, face_shape, symmetry_score, recommendations")
                .in_("upload_id", upload_ids)
                .execute()
                .data
                or []
            )
        ):
            analysis_by_upload[analysis["upload_id"]] = analysis

    # 2. Fetch latest completed job per glowup_analysis in one query.
    #    PostgREST doesn't support DISTINCT ON, so pick latest per source_id in Python.
    analysis_ids = [a["id"] for a in analysis_by_upload.values()]
    jobs_by_analysis: dict[str, str] = {}  # analysis_id -> after_image_url
    if analysis_ids:
        for job in await run_sync(
            job_repo.get_completed_jobs_for_sources, SOURCE_TYPE_GLOWUP, analysis_ids
        ):
            sid = job["source_id"]
            # First seen per source_id is the latest (ordered desc by created_at)
            if sid not in jobs_by_analysis and job.get("after_image_url"):
                jobs_by_analysis[sid] = job["after_image_url"]

    # 3. Assemble entries — no image signing needed; uploads.image_url and
    #    jobs.after_image_url are stable CDN paths stored directly.
    entries: list[HistoryEntry] = []
    for row in uploads:
        upload_id = row["id"]
        analysis = analysis_by_upload.get(upload_id)

        analysis_id: str | None = analysis["id"] if analysis else None
        face_shape: str | None = analysis.get("face_shape") if analysis else None
        symmetry_score: float | None = (
            analysis.get("symmetry_score") if analysis else None
        )
        raw_recs: list[dict] = (
            (analysis.get("recommendations") or []) if analysis else []
        )

        after_url: str | None = (
            jobs_by_analysis.get(analysis_id) if analysis_id else None
        )

        entries.append(
            HistoryEntry(
                analysis_id=analysis_id or upload_id,
                face_shape=face_shape,
                symmetry_score=symmetry_score,
                recommendations=[
                    RecommendationItem(
                        rank=r["rank"],
                        category=r["category"],
                        suggestion=r["suggestion_text"],
                        rationale=r.get("rationale"),
                    )
                    for r in raw_recs
                ],
                before_image_url=row.get("image_url"),
                after_image_url=after_url,
                created_at=row["created_at"],
            )
        )

    logger.info(
        "History fetched for user %s: %d entries (has_more=%s)",
        user_id,
        len(entries),
        has_more,
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
        avatar_pattern = (
            rf"^avatars/{re.escape(user_id)}/[a-zA-Z0-9_\-]+\.(jpg|jpeg|png|webp)$"
        )
        if not re.match(avatar_pattern, body.avatar_storage_key):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid avatar storage key",
            )
        updates["avatar_storage_key"] = body.avatar_storage_key

    if updates:
        updates["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
        await run_sync(user_repo.update_profile, user_id, updates)
        logger.info(
            "Profile updated for user %s: fields=%s", user_id, list(updates.keys())
        )

    # --- Username change (with cooldown) ---
    if body.new_username is not None and body.new_username != user["username"]:
        # Enforce cooldown
        username_changed_at_str = user.get("username_changed_at")
        if username_changed_at_str:
            last_change = datetime.fromisoformat(username_changed_at_str)
            if last_change.tzinfo is None:
                last_change = last_change.replace(tzinfo=timezone.utc)
            cooldown_end = last_change + timedelta(
                hours=_USERNAME_CHANGE_COOLDOWN_HOURS
            )
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
        await run_sync(
            image_repo.build_avatar_signed_url,
            refreshed_avatar_key,
            settings.SIGNED_URL_EXPIRY_SECONDS,
        )
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
