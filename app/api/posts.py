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
    user_id: str
    content: str
    created_at: str


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

    # Copy BOTH images from private buckets to the public post-images bucket.
    # Images stay private until the user explicitly creates a post.
    from app.services.public_url import PUBLIC_BUCKET, get_public_url

    before_public_key = f"before/{user_id}/{before_img.data['storage_key'].split('/')[-1]}"
    after_public_key = f"after/{user_id}/{after_img.data['storage_key'].split('/')[-1]}"

    for src_img, public_key in [
        (before_img.data, before_public_key),
        (after_img.data, after_public_key),
    ]:
        try:
            raw_bytes = supabase.storage.from_(src_img.get("bucket", "raw-selfies")).download(
                src_img["storage_key"]
            )
            supabase.storage.from_(PUBLIC_BUCKET).upload(
                path=public_key,
                file=raw_bytes,
                file_options={"content-type": "image/jpeg", "upsert": "true"},
            )
        except Exception as exc:
            logger.warning("Failed to copy %s to public bucket: %s", public_key, exc)

    before_url = get_public_url(before_public_key)
    after_url = get_public_url(after_public_key)

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
        .select("id, comment_count")
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

    # Increment comment count
    supabase.table("posts").update({
        "comment_count": (post.data.get("comment_count") or 0) + 1,
        "updated_at": now_utc,
    }).eq("id", str(post_id)).execute()

    logger.info("Comment %s on post %s by user %s", comment["id"], post_id, user_id)

    return CommentResponse(
        comment_id=comment["id"],
        user_id=user_id,
        content=body.content,
        created_at=now_utc,
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
        .select("id, user_id, content, created_at")
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

    return CommentsListResponse(
        comments=[
            CommentResponse(
                comment_id=c["id"],
                user_id=c["user_id"],
                content=c["content"],
                created_at=c["created_at"],
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
