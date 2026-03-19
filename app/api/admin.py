"""Admin API — content moderation endpoints.

All endpoints require X-Admin-Key header matching ADMIN_API_KEY.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from supabase import Client

from app.api.deps import get_supabase, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ReportStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(reviewed|actioned|dismissed)$")


class BanRequest(BaseModel):
    reason: str = Field(..., max_length=500)


class PostVisibilityUpdate(BaseModel):
    is_hidden: bool


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


@router.get("/reports", dependencies=[Depends(require_admin)])
def list_reports(
    report_status: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    supabase: Client = Depends(get_supabase),
):
    """List reports with optional status filter, ordered newest-first."""
    query = (
        supabase.table("reports")
        .select("id, post_id, reporter_user_id, reason, status, created_at")
        .order("created_at", desc=True)
        .limit(limit)
    )
    if report_status:
        query = query.eq("status", report_status)
    return query.execute().data or []


@router.patch("/reports/{report_id}", dependencies=[Depends(require_admin)])
def update_report_status(
    report_id: UUID,
    body: ReportStatusUpdate,
    supabase: Client = Depends(get_supabase),
):
    """Update a report's status. If dismissed and no other active reports remain, un-hide the post."""
    result = (
        supabase.table("reports")
        .update({"status": body.status})
        .eq("id", str(report_id))
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    # If dismissed, check whether the post can be un-hidden
    if body.status == "dismissed":
        report = result.data[0]
        post_id = report["post_id"]
        # Only un-hide if no other pending/actioned reports exist for this post
        other_reports = (
            supabase.table("reports")
            .select("id")
            .eq("post_id", post_id)
            .in_("status", ["pending", "actioned"])
            .neq("id", str(report_id))
            .limit(1)
            .execute()
        )
        if not other_reports.data:
            supabase.table("posts").update({"is_hidden": False}).eq("id", post_id).execute()
            logger.info("Post %s un-hidden after report %s dismissed", post_id, report_id)

    logger.info("Report %s updated to status '%s'", report_id, body.status)
    return {"report_id": str(report_id), "status": body.status}


# ---------------------------------------------------------------------------
# User bans
# ---------------------------------------------------------------------------


@router.post("/users/{user_id}/ban", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
def ban_user(
    user_id: UUID,
    body: BanRequest,
    supabase: Client = Depends(get_supabase),
):
    """Ban a user and hide all their posts."""
    now = datetime.now(tz=timezone.utc).isoformat()
    supabase.table("users").update({
        "is_banned": True,
        "banned_at": now,
        "ban_reason": body.reason,
    }).eq("id", str(user_id)).execute()

    # Hide all posts by the banned user
    supabase.table("posts").update({
        "is_hidden": True,
    }).eq("user_id", str(user_id)).execute()

    logger.warning("User %s banned: %s", user_id, body.reason)
    return {"user_id": str(user_id), "banned": True}


@router.delete(
    "/users/{user_id}/ban",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
def unban_user(
    user_id: UUID,
    supabase: Client = Depends(get_supabase),
):
    """Unban a user and restore visibility for posts without active reports."""
    supabase.table("users").update({
        "is_banned": False,
        "banned_at": None,
        "ban_reason": None,
    }).eq("id", str(user_id)).execute()

    # Un-hide posts — posts hidden individually by reports stay hidden
    supabase.table("posts").update({
        "is_hidden": False,
    }).eq("user_id", str(user_id)).eq("is_hidden", True).execute()

    logger.info("User %s unbanned", user_id)


@router.get("/users", dependencies=[Depends(require_admin)])
def list_banned_users(
    banned: bool = Query(True),
    limit: int = Query(50, ge=1, le=100),
    supabase: Client = Depends(get_supabase),
):
    """List users filtered by ban status."""
    return (
        supabase.table("users")
        .select("id, username, is_banned, banned_at, ban_reason")
        .eq("is_banned", banned)
        .order("banned_at", desc=True)
        .limit(limit)
        .execute()
        .data or []
    )


# ---------------------------------------------------------------------------
# Post visibility
# ---------------------------------------------------------------------------


@router.patch("/posts/{post_id}", dependencies=[Depends(require_admin)])
def update_post_visibility(
    post_id: UUID,
    body: PostVisibilityUpdate,
    supabase: Client = Depends(get_supabase),
):
    """Manually show or hide a post."""
    supabase.table("posts").update({
        "is_hidden": body.is_hidden,
    }).eq("id", str(post_id)).execute()

    action = "hidden" if body.is_hidden else "un-hidden"
    logger.info("Post %s %s by admin", post_id, action)
    return {"post_id": str(post_id), "is_hidden": body.is_hidden}
