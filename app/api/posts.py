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

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from supabase import Client

from app.api.deps import get_current_user, get_supabase
from app.api.middleware.auth import UserClaims
from app.services.public_url import build_avatar_url, publish_post_images

logger = logging.getLogger(__name__)

router = APIRouter(tags=["posts"])


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
) -> PostResponse:
    """Create a post from a completed glow-up job.

    AC: Post row created; shareable card updated.
    """
    user_id = claims["sub"]

    # Verify glow-up job exists, is owned, and is completed
    job = (
        supabase.table("glow_up_jobs")
        .select("id, user_id, status, original_image_id, generated_image_id")
        .eq("id", body.glow_up_job_id)
        .maybe_single()
        .execute()
    )
    if not job.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.data["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.data["status"] != "completed":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "JOB_NOT_COMPLETED", "message": "Job must be completed to create a post."}},
        )
    if not job.data.get("generated_image_id"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "NO_GENERATED_IMAGE", "message": "Job has no generated image."}},
        )

    # Get image storage keys from private buckets
    before_img = (
        supabase.table("images").select("storage_key, bucket")
        .eq("id", job.data["original_image_id"]).single().execute()
    )
    after_img = (
        supabase.table("images").select("storage_key, bucket")
        .eq("id", job.data["generated_image_id"]).single().execute()
    )

    # Copy images from private buckets to public bucket and get CDN URLs
    try:
        published = publish_post_images(
            supabase,
            user_id=user_id,
            before_image=before_img.data,
            after_image=after_img.data,
        )
    except Exception as exc:
        logger.error("Failed to publish post images: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to publish post images. Please try again.",
        ) from exc

    before_url = published.before_url
    after_url = published.after_url

    now_utc = datetime.now(tz=timezone.utc).isoformat()

    result = supabase.table("posts").insert({
        "user_id": user_id,
        "glow_up_job_id": body.glow_up_job_id,
        "caption": body.caption,
        "before_image_id": job.data["original_image_id"],
        "after_image_id": job.data["generated_image_id"],
        "before_image_url": before_url,
        "after_image_url": after_url,
        "created_at": now_utc,
        "updated_at": now_utc,
    }).execute()

    post_id = result.data[0]["id"]

    logger.info("Post %s created by user %s from job %s", post_id, user_id, body.glow_up_job_id)

    return PostResponse(
        post_id=post_id,
        before_image_url=before_url,
        after_image_url=after_url,
        caption=body.caption,
        created_at=now_utc,
    )


# ---------------------------------------------------------------------------
# DELETE /posts/{post_id}
# ---------------------------------------------------------------------------


@router.delete("/posts/{post_id}", status_code=status.HTTP_200_OK)
def delete_post(
    post_id: UUID,
    claims: UserClaims = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
) -> dict:
    """Soft-delete own post. AC-FR5: is_deleted = TRUE, removed from feed."""
    user_id = claims["sub"]

    post = (
        supabase.table("posts")
        .select("id, user_id, is_deleted")
        .eq("id", str(post_id))
        .maybe_single()
        .execute()
    )
    if not post.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    if post.data["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    if post.data["is_deleted"]:
        return {"status": "already_deleted"}

    now_utc = datetime.now(tz=timezone.utc).isoformat()
    supabase.table("posts").update({
        "is_deleted": True,
        "updated_at": now_utc,
    }).eq("id", str(post_id)).execute()

    logger.info("Post %s deleted by user %s", post_id, user_id)
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# POST /posts/{post_id}/comments
# ---------------------------------------------------------------------------


@router.post(
    "/posts/{post_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_comment(
    post_id: UUID,
    body: CreateCommentRequest,
    claims: UserClaims = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
) -> CommentResponse:
    """Add a comment to a post. Auth required (AC-U6)."""
    user_id = claims["sub"]

    # Verify post exists and is not deleted
    post = (
        supabase.table("posts")
        .select("id")
        .eq("id", str(post_id))
        .eq("is_deleted", False)
        .maybe_single()
        .execute()
    )
    if not post.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    now_utc = datetime.now(tz=timezone.utc).isoformat()
    result = supabase.table("comments").insert({
        "post_id": str(post_id),
        "user_id": user_id,
        "content": body.content,
        "created_at": now_utc,
    }).execute()

    comment = result.data[0]

    # Increment comment count atomically to avoid race conditions
    supabase.rpc("increment_comment_count", {"p_post_id": str(post_id)}).execute()

    logger.info("Comment %s on post %s by user %s", comment["id"], post_id, user_id)

    # Fetch author profile for display name and avatar
    author = (
        supabase.table("users")
        .select("display_name, avatar_storage_key")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    display_name: str | None = None
    avatar_url: str | None = None
    if author.data:
        display_name = author.data.get("display_name")
        avatar_url = build_avatar_url(supabase, author.data.get("avatar_storage_key"))

    return CommentResponse(
        comment_id=comment["id"],
        post_id=str(post_id),
        user_id=user_id,
        content=body.content,
        is_deleted=False,
        created_at=now_utc,
        display_name=display_name,
        avatar_url=avatar_url,
    )


# ---------------------------------------------------------------------------
# GET /posts/{post_id}/comments
# ---------------------------------------------------------------------------


@router.get("/posts/{post_id}/comments", response_model=CommentsListResponse)
def get_comments(
    post_id: UUID,
    cursor: str | None = Query(None, description="Cursor (created_at ISO timestamp)"),
    limit: int = Query(20, ge=1, le=100),
    supabase: Client = Depends(get_supabase),
) -> CommentsListResponse:
    """List comments on a post. Public read — no auth required (FR-22)."""
    fetch_limit = limit + 1

    query = (
        supabase.table("comments")
        .select("id, post_id, user_id, content, is_deleted, created_at, users(display_name, avatar_storage_key)")
        .eq("post_id", str(post_id))
        .eq("is_deleted", False)
        .order("created_at", desc=False)
        .limit(fetch_limit)
    )

    if cursor:
        query = query.gt("created_at", cursor)

    result = query.execute()
    comments = result.data or []

    has_more = len(comments) > limit
    if has_more:
        comments = comments[:limit]

    next_cursor = comments[-1]["created_at"] if has_more and comments else None

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


@router.post("/posts/{post_id}/report", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def report_post(
    post_id: UUID,
    body: ReportRequest,
    claims: UserClaims = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
) -> ReportResponse:
    """Report a post for review. Auth required."""
    user_id = claims["sub"]

    # Verify post exists
    post = (
        supabase.table("posts")
        .select("id")
        .eq("id", str(post_id))
        .eq("is_deleted", False)
        .maybe_single()
        .execute()
    )
    if not post.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    result = supabase.table("reports").insert({
        "post_id": str(post_id),
        "reporter_user_id": user_id,
        "reason": body.reason,
    }).execute()

    report = result.data[0]
    logger.info("Report %s on post %s by user %s", report["id"], post_id, user_id)

    return ReportResponse(
        report_id=report["id"],
        status="pending",
    )
