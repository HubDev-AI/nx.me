"""Posts, Comments & Reports API.

Story 5-3:
  POST /posts           — create post from completed glow-up job
  DELETE /posts/{id}     — soft-delete own post
  POST /posts/{id}/comments  — add comment (auth required)
  GET /posts/{id}/comments   — list comments (public)
  POST /posts/{id}/report    — report a post (auth required)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from supabase import Client

from app.api.deps import get_current_user, get_image_repo, get_job_repo, get_post_repo, get_redis, get_supabase
from app.api.middleware.auth import UserClaims
from app.config import settings
from app.repositories.image_repo import ImageRepository
from app.repositories.job_repo import JobRepository
from app.repositories.post_repo import PostRepository
from app.services.public_url import build_avatar_url, publish_post_images

logger = logging.getLogger(__name__)

router = APIRouter(tags=["posts"])

_COMMENT_RATE_LIMIT = 10
_COMMENT_RATE_WINDOW = 60


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class CreatePostRequest(BaseModel):
    glow_up_job_id: str
    caption: str | None = Field(None, max_length=500)


class PostResponse(BaseModel):
    post_id: str
    before_image_url: str
    after_image_url: str
    caption: str | None
    created_at: str


class CreateCommentRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)


class CommentResponse(BaseModel):
    comment_id: str
    post_id: str
    user_id: str
    content: str
    is_deleted: bool
    created_at: str
    display_name: str | None
    avatar_url: str | None


class CommentsListResponse(BaseModel):
    comments: list[CommentResponse]
    next_cursor: str | None
    has_more: bool


class ReportRequest(BaseModel):
    reason: str | None = Field(None, max_length=500)


class ReportResponse(BaseModel):
    report_id: str
    status: str


# ---------------------------------------------------------------------------
# POST /posts
# ---------------------------------------------------------------------------


@router.post("/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
def create_post(
    body: CreatePostRequest,
    claims: UserClaims = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
    post_repo: PostRepository = Depends(get_post_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    image_repo: ImageRepository = Depends(get_image_repo),
) -> Response:
    """Create a post from a completed glow-up job.

    AC: Post row created; shareable card updated.
    """
    user_id = claims["sub"]

    # Verify glow-up job exists, is owned, and is completed
    job_data = job_repo.get_jobs_for_post(body.glow_up_job_id)
    if not job_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job_data["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job_data["status"] != "completed":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "JOB_NOT_COMPLETED", "message": "Job must be completed to create a post."}},
        )
    if not job_data.get("generated_image_id"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "NO_GENERATED_IMAGE", "message": "Job has no generated image."}},
        )

    # Get image storage keys from private buckets
    before_img_data = image_repo.get_by_id_with_fields(job_data["original_image_id"], "storage_key, bucket")
    after_img_data = image_repo.get_by_id_with_fields(job_data["generated_image_id"], "storage_key, bucket")

    # Copy images from private buckets to public bucket and get CDN URLs
    try:
        published = publish_post_images(
            supabase,
            user_id=user_id,
            before_image=before_img_data,
            after_image=after_img_data,
        )
    except Exception as exc:
        logger.error("Failed to publish post images: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to publish post images. Please try again.",
        ) from exc

    before_url = published.before_url
    after_url = published.after_url

    # Re-verify job status right before insert to minimise TOCTOU window (M-5).
    # The job could have been re-queued or failed between the first check and
    # the image publish above.
    fresh_job = job_repo.get_jobs_for_post(body.glow_up_job_id)
    if not fresh_job or fresh_job["status"] != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "JOB_STATUS_CHANGED", "message": "Job status changed during post creation."}},
        )

    now_utc = datetime.now(tz=timezone.utc).isoformat()

    post = post_repo.insert_post({
        "user_id": user_id,
        "glow_up_job_id": body.glow_up_job_id,
        "caption": body.caption,
        "before_image_id": job_data["original_image_id"],
        "after_image_id": job_data["generated_image_id"],
        "before_image_url": before_url,
        "after_image_url": after_url,
        "created_at": now_utc,
        "updated_at": now_utc,
    })

    post_id = post["id"]

    logger.info("Post %s created by user %s from job %s", post_id, user_id, body.glow_up_job_id)

    from fastapi.responses import JSONResponse

    payload = PostResponse(
        post_id=post_id,
        before_image_url=before_url,
        after_image_url=after_url,
        caption=body.caption,
        created_at=now_utc,
    )
    return JSONResponse(
        content=payload.model_dump(),
        status_code=status.HTTP_201_CREATED,
        headers={"Location": f"/v1/posts/{post_id}"},
    )


# ---------------------------------------------------------------------------
# DELETE /posts/{post_id}
# ---------------------------------------------------------------------------


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(
    post_id: UUID,
    claims: UserClaims = Depends(get_current_user),
    post_repo: PostRepository = Depends(get_post_repo),
) -> Response:
    """Soft-delete own post. AC-FR5: is_deleted = TRUE, removed from feed."""
    user_id = claims["sub"]

    post = post_repo.get_post_with_ownership(str(post_id))
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    if post["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    if post["is_deleted"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "ALREADY_DELETED", "message": "Post is already deleted"}},
        )

    now_utc = datetime.now(tz=timezone.utc).isoformat()
    post_repo.soft_delete_post(str(post_id), now_utc)

    logger.info("Post %s deleted by user %s", post_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# POST /posts/{post_id}/comments
# ---------------------------------------------------------------------------


@router.post(
    "/posts/{post_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_comment(
    post_id: UUID,
    body: CreateCommentRequest,
    claims: UserClaims = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
    post_repo: PostRepository = Depends(get_post_repo),
    redis_client: aioredis.Redis = Depends(get_redis),
) -> Response:
    """Add a comment to a post. Auth required (AC-U6)."""
    user_id = claims["sub"]

    # Rate limit comments per user
    rate_key = f"comment_rate:{user_id}"
    count = await redis_client.incr(rate_key)
    if count == 1:
        await redis_client.expire(rate_key, _COMMENT_RATE_WINDOW)
    if count > _COMMENT_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many comments. Please slow down.")

    # Verify post exists and is not deleted
    post = post_repo.get_active_post(str(post_id))
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    # Atomic: insert comment + increment count in single transaction
    comment = post_repo.insert_comment_atomic(
        p_post_id=str(post_id),
        p_user_id=user_id,
        p_content=body.content,
    )

    comment_id = comment["id"]
    comment_created_at = comment.get("created_at", "")
    logger.info("Comment %s on post %s by user %s", comment_id, post_id, user_id)

    # Fetch author profile for display name and avatar
    author = post_repo.get_commenter_profile(user_id)
    display_name: str | None = None
    avatar_url: str | None = None
    if author:
        display_name = author.get("display_name")
        avatar_url = build_avatar_url(supabase, author.get("avatar_storage_key"))

    from fastapi.responses import JSONResponse

    payload = CommentResponse(
        comment_id=comment_id,
        post_id=str(post_id),
        user_id=user_id,
        content=body.content,
        is_deleted=False,
        created_at=comment_created_at,
        display_name=display_name,
        avatar_url=avatar_url,
    )
    return JSONResponse(
        content=payload.model_dump(),
        status_code=status.HTTP_201_CREATED,
        headers={"Location": f"/v1/posts/{post_id}/comments/{comment_id}"},
    )


# ---------------------------------------------------------------------------
# GET /posts/{post_id}/comments
# ---------------------------------------------------------------------------


@router.get("/posts/{post_id}/comments", response_model=CommentsListResponse)
def get_comments(
    post_id: UUID,
    cursor: str | None = Query(None, description="Cursor ({created_at}|{id} composite)"),
    limit: int = Query(20, ge=1, le=100),
    sort: str = Query("oldest", pattern="^(newest|oldest)$", description="Sort order: oldest or newest"),
    supabase: Client = Depends(get_supabase),
    post_repo: PostRepository = Depends(get_post_repo),
) -> CommentsListResponse:
    """List comments on a post. Public read — no auth required (FR-22)."""
    fetch_limit = limit + 1

    comments = post_repo.get_comments_page(
        post_id=str(post_id),
        fetch_limit=fetch_limit,
        cursor=cursor,
        sort=sort,
    )

    has_more = len(comments) > limit
    if has_more:
        comments = comments[:limit]

    next_cursor = (
        f"{comments[-1]['created_at']}|{comments[-1]['id']}"
        if has_more and comments
        else None
    )

    # Build signed avatar URLs — batch unique storage keys to minimise signed URL calls
    unique_keys: dict[str, str | None] = {}
    for c in comments:
        author = c.get("users") or {}
        key = author.get("avatar_storage_key")
        if key and key not in unique_keys:
            unique_keys[key] = build_avatar_url(supabase, key)

    return CommentsListResponse(
        comments=[
            CommentResponse(
                comment_id=c["id"],
                post_id=c["post_id"],
                user_id=c["user_id"],
                content=c["content"],
                is_deleted=c["is_deleted"],
                created_at=c["created_at"],
                display_name=(c.get("users") or {}).get("display_name"),
                avatar_url=unique_keys.get((c.get("users") or {}).get("avatar_storage_key") or ""),
            )
            for c in comments
        ],
        next_cursor=next_cursor,
        has_more=has_more,
    )


# ---------------------------------------------------------------------------
# POST /posts/{post_id}/report
# ---------------------------------------------------------------------------


@router.post(
    "/posts/{post_id}/report",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def report_post(
    post_id: UUID,
    body: ReportRequest,
    claims: UserClaims = Depends(get_current_user),
    post_repo: PostRepository = Depends(get_post_repo),
    redis_client: aioredis.Redis = Depends(get_redis),
) -> ReportResponse:
    """Report a post for review. Auth required."""
    user_id = claims["sub"]

    # Rate limit reports per user
    rate_key = f"report_rate:{user_id}"
    count = await redis_client.incr(rate_key)
    if count == 1:
        await redis_client.expire(rate_key, settings.REPORT_RATE_WINDOW_SECONDS)
    if count > settings.REPORT_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many reports. Please slow down.")

    # Verify post exists
    post = post_repo.get_active_post(str(post_id))
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    report = post_repo.insert_report(
        post_id=str(post_id),
        reporter_user_id=user_id,
        reason=body.reason,
    )

    # Auto-hide: count unique reporters, hide if threshold reached
    report_count = post_repo.count_unique_reporters(str(post_id))
    if report_count >= settings.REPORT_AUTO_HIDE_THRESHOLD:
        post_repo.hide_post(str(post_id))
        logger.warning("Post %s auto-hidden: %d unique reports", post_id, report_count)

    logger.info("Report %s on post %s by user %s", report["id"], post_id, user_id)

    return ReportResponse(
        report_id=report["id"],
        status="pending",
    )
