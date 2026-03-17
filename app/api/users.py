"""User Profile & History API.

Story 6-3:
  GET  /users/{username}/profile  — public, no auth required
  GET  /users/{username}/history  — private, owner only
  PATCH /users/{username}         — update display_name, owner only
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from supabase import Client

from app.api.deps import get_current_user, get_supabase
from app.api.middleware.auth import UserClaims
from app.config import settings

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
    avatar_url: Optional[str]
    post_count: int
    total_reactions: int
    member_since: str


class HistoryEntry(BaseModel):
    analysis_id: str
    face_shape: Optional[str]
    symmetry_score: Optional[float]
    recommendations: list[dict]
    before_image_url: Optional[str]
    after_image_url: Optional[str]
    created_at: str


class HistoryResponse(BaseModel):
    entries: list[HistoryEntry]
    next_cursor: Optional[str]
    has_more: bool


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = None


class UpdateProfileResponse(BaseModel):
    username: str
    display_name: str
    avatar_url: Optional[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lookup_user(supabase: Client, username: str) -> dict:
    """Fetch a non-deleted user by username. Raises 404 if missing."""
    result = (
        supabase.table("users")
        .select("id, username, display_name, avatar_storage_key, created_at")
        .eq("username", username)
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return result.data


def _build_avatar_url(supabase: Client, avatar_storage_key: str | None) -> str | None:
    """Generate a signed URL for an avatar if the storage key is present."""
    if not avatar_storage_key:
        return None
    try:
        return supabase.storage.from_("avatars").create_signed_url(
            avatar_storage_key, settings.SIGNED_URL_EXPIRY_SECONDS
        )["signedURL"]
    except Exception:
        logger.warning("Failed to generate signed URL for avatar key: %s", avatar_storage_key)
        return None


# ---------------------------------------------------------------------------
# GET /users/{username}/profile  (public)
# ---------------------------------------------------------------------------


@router.get("/users/{username}/profile", response_model=ProfileResponse)
def get_user_profile(
    username: str,
    supabase: Client = Depends(get_supabase),
) -> ProfileResponse:
    """Return public profile stats for the given username.

    No auth required. Returns 404 for deleted or non-existent users.
    """
    user = _lookup_user(supabase, username)
    user_id: str = user["id"]

    # Count non-deleted posts and sum reaction_count
    posts_result = (
        supabase.table("posts")
        .select("reaction_count")
        .eq("user_id", user_id)
        .eq("is_deleted", False)
        .execute()
    )
    posts = posts_result.data or []
    post_count = len(posts)
    total_reactions = sum(p.get("reaction_count", 0) for p in posts)

    avatar_url = _build_avatar_url(supabase, user.get("avatar_storage_key"))

    logger.info("Profile viewed for user %s", user_id)

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
def get_user_history(
    username: str,
    cursor: str | None = Query(None, description="Cursor (created_at ISO timestamp)"),
    limit: int = Query(
        _DEFAULT_HISTORY_PAGE_SIZE,
        ge=1,
        le=_MAX_HISTORY_PAGE_SIZE,
        description="Page size",
    ),
    claims: UserClaims = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
) -> HistoryResponse:
    """Return the authenticated user's analysis history in reverse chronological order.

    Owner only — returns 403 if the token does not belong to the requested user.
    Cursor-paginated using created_at timestamp.
    """
    user = _lookup_user(supabase, username)
    user_id: str = user["id"]

    if claims["sub"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this user's history",
        )

    fetch_limit = limit + 1

    query = (
        supabase.table("analyses")
        .select("id, original_image_id, face_shape, symmetry_score, recommendations, status, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(fetch_limit)
    )

    if cursor:
        query = query.lt("created_at", cursor)

    result = query.execute()
    analyses = result.data or []

    has_more = len(analyses) > limit
    if has_more:
        analyses = analyses[:limit]

    next_cursor: str | None = analyses[-1]["created_at"] if has_more and analyses else None

    # Build entries — attempt to fetch before/after image URLs per analysis
    entries: list[HistoryEntry] = []
    for row in analyses:
        before_image_url: str | None = None
        after_image_url: str | None = None

        # Fetch original image (before) from the analysis
        original_image_id: str | None = row.get("original_image_id")
        if original_image_id:
            img_result = (
                supabase.table("images")
                .select("storage_key, bucket")
                .eq("id", original_image_id)
                .maybe_single()
                .execute()
            )
            if img_result.data and img_result.data.get("storage_key"):
                img = img_result.data
                bucket = img.get("bucket") or "raw-selfies"
                try:
                    before_image_url = supabase.storage.from_(bucket).create_signed_url(
                        img["storage_key"], settings.SIGNED_URL_EXPIRY_SECONDS
                    )["signedURL"]
                except Exception:
                    logger.warning(
                        "Failed to sign before-image URL for analysis %s", row["id"]
                    )

        # Fetch after image from a completed glow_up_job linked to this analysis
        job_result = (
            supabase.table("glow_up_jobs")
            .select("generated_image_id")
            .eq("analysis_id", row["id"])
            .eq("status", "completed")
            .order("created_at", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
        )
        generated_image_id: str | None = (
            job_result.data.get("generated_image_id") if job_result.data else None
        )
        if generated_image_id:
            gen_img_result = (
                supabase.table("images")
                .select("storage_key, bucket")
                .eq("id", generated_image_id)
                .maybe_single()
                .execute()
            )
            if gen_img_result.data and gen_img_result.data.get("storage_key"):
                gen_img = gen_img_result.data
                gen_bucket = gen_img.get("bucket") or "generated-images"
                try:
                    after_image_url = supabase.storage.from_(gen_bucket).create_signed_url(
                        gen_img["storage_key"], settings.SIGNED_URL_EXPIRY_SECONDS
                    )["signedURL"]
                except Exception:
                    logger.warning(
                        "Failed to sign after-image URL for analysis %s", row["id"]
                    )

        entries.append(
            HistoryEntry(
                analysis_id=row["id"],
                face_shape=row.get("face_shape"),
                symmetry_score=row.get("symmetry_score"),
                recommendations=row.get("recommendations") or [],
                before_image_url=before_image_url,
                after_image_url=after_image_url,
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
def update_user_profile(
    username: str,
    body: UpdateProfileRequest,
    claims: UserClaims = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
) -> UpdateProfileResponse:
    """Update the authenticated user's display_name.

    Owner only — returns 403 if the token does not belong to the requested user.
    Username cannot be changed via this endpoint; any username field in the body
    is silently ignored per AC.
    """
    user = _lookup_user(supabase, username)
    user_id: str = user["id"]

    if claims["sub"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this user's profile",
        )

    updates: dict = {}
    if body.display_name is not None:
        updates["display_name"] = body.display_name

    if updates:
        from datetime import datetime, timezone

        updates["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
        supabase.table("users").update(updates).eq("id", user_id).execute()
        logger.info("Profile updated for user %s: fields=%s", user_id, list(updates.keys()))

    # Re-fetch to return the current state
    refreshed = _lookup_user(supabase, username)
    avatar_url = _build_avatar_url(supabase, refreshed.get("avatar_storage_key"))

    return UpdateProfileResponse(
        username=refreshed["username"],
        display_name=refreshed["display_name"],
        avatar_url=avatar_url,
    )
