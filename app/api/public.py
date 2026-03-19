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

from app.api.deps import get_analysis_repo, get_job_repo, get_post_repo, get_user_repo
from app.db.async_helpers import run_sync
from app.repositories.analysis_repo import AnalysisRepository
from app.repositories.job_repo import JobRepository
from app.repositories.post_repo import PostRepository
from app.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["public"])


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class RecommendationItem(BaseModel):
    rank: int
    category: str
    suggestion_text: str
    rationale: str | None = None


class CardResponse(BaseModel):
    username: str
    display_name: str
    before_image_url: str
    after_image_url: str
    recommendations: list[RecommendationItem]
    reaction_count: int
    comment_count: int


# ---------------------------------------------------------------------------
# GET /public/cards/{username}
# ---------------------------------------------------------------------------


@router.get("/public/cards/{username}", response_model=CardResponse)
async def get_shareable_card(
    username: str,
    user_repo: UserRepository = Depends(get_user_repo),
    post_repo: PostRepository = Depends(get_post_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    analysis_repo: AnalysisRepository = Depends(get_analysis_repo),
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

    # Step 3 — find the analysis for the post's glow_up_job
    recommendations: list[dict] = []

    glow_up_job_id: str | None = post.get("glow_up_job_id")
    if glow_up_job_id:
        job_data = await run_sync(job_repo.get_for_analysis, glow_up_job_id)

        if job_data:
            analysis_id: str | None = job_data.get("analysis_id")
            if analysis_id:
                recommendations = await run_sync(analysis_repo.get_recommendations, analysis_id)

    logger.info(
        "Shareable card served for user %s (post %s, %d recommendations)",
        username,
        post["id"],
        len(recommendations),
    )

    # URLs are stable public CDN paths (no signing needed)
    return CardResponse(
        username=user["username"],
        display_name=user.get("display_name") or user["username"],
        before_image_url=post["before_image_url"],
        after_image_url=post["after_image_url"],
        recommendations=recommendations,
        reaction_count=post["reaction_count"],
        comment_count=post["comment_count"],
    )
