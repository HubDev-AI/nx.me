"""Public (no-auth) API — Story 6-1: Shareable Card.

GET /api/public/cards/{username}
  Returns the latest published post for the given username, with
  recommendations from the associated analysis.

  HTTP 200 — card data
  HTTP 404 — user exists but has no published posts
  HTTP 410 — account deleted or post hard-deleted
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from supabase import Client

from app.api.deps import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(tags=["public"])


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class CardResponse(BaseModel):
    username: str
    display_name: str
    before_image_url: str
    after_image_url: str
    recommendations: list[dict]
    reaction_count: int
    comment_count: int


# ---------------------------------------------------------------------------
# GET /public/cards/{username}
# ---------------------------------------------------------------------------


@router.get("/public/cards/{username}", response_model=CardResponse)
def get_shareable_card(
    username: str,
    supabase: Client = Depends(get_supabase),
) -> CardResponse:
    """Return the shareable card for a user's latest published post.

    No authentication required — fully public endpoint.

    Raises:
        HTTP 410: account has been deleted.
        HTTP 404: user has no published posts.
    """
    # Step 1 — look up user by username
    user_result = (
        supabase.table("users")
        .select("id, username, display_name, deleted_at")
        .eq("username", username)
        .maybe_single()
        .execute()
    )

    if not user_result.data:
        # Username not found — treat as Gone so callers don't leak enumeration
        # info while still being semantically correct for deleted accounts.
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Account not found or has been deleted",
        )

    user = user_result.data

    if user.get("deleted_at") is not None:
        logger.info("Shareable card requested for deleted account: %s", username)
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Account not found or has been deleted",
        )

    user_id: str = user["id"]

    # Step 2 — latest non-deleted post for this user
    post_result = (
        supabase.table("posts")
        .select(
            "id, before_image_url, after_image_url, "
            "reaction_count, comment_count, glow_up_job_id"
        )
        .eq("user_id", user_id)
        .eq("is_deleted", False)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    posts = post_result.data or []
    if not posts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No published posts found for this user",
        )

    post = posts[0]

    # Step 3 — find the analysis for the post's glow_up_job
    recommendations: list[dict] = []

    glow_up_job_id: str | None = post.get("glow_up_job_id")
    if glow_up_job_id:
        job_result = (
            supabase.table("glow_up_jobs")
            .select("analysis_id")
            .eq("id", glow_up_job_id)
            .maybe_single()
            .execute()
        )

        if job_result.data:
            analysis_id: str | None = job_result.data.get("analysis_id")
            if analysis_id:
                analysis_result = (
                    supabase.table("analyses")
                    .select("recommendations")
                    .eq("id", analysis_id)
                    .maybe_single()
                    .execute()
                )
                if analysis_result.data:
                    recommendations = analysis_result.data.get("recommendations") or []

    logger.info(
        "Shareable card served for user %s (post %s, %d recommendations)",
        username,
        post["id"],
        len(recommendations),
    )

    return CardResponse(
        username=user["username"],
        display_name=user.get("display_name") or user["username"],
        before_image_url=post["before_image_url"],
        after_image_url=post["after_image_url"],
        recommendations=recommendations,
        reaction_count=post["reaction_count"],
        comment_count=post["comment_count"],
    )
