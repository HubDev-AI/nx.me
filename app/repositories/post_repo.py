"""Post repository — all posts/comments/reports supabase queries in one place.

Follows the same pattern as UserRepository: constructor takes a Client,
methods are synchronous (callers use run_sync for async handlers).
"""
from __future__ import annotations

import logging

from supabase import Client

logger = logging.getLogger(__name__)


class PostRepository:
    """Encapsulates all DB calls related to posts, comments, and reports tables."""

    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    # ------------------------------------------------------------------
    # posts table — reads
    # ------------------------------------------------------------------

    def get_latest_for_user(self, user_id: str) -> dict | None:
        """Fetch the latest non-deleted post for a user (for shareable card).

        Returns id, before_image_url, after_image_url, reaction_count,
        comment_count, and glow_up_job_id; or None if the user has no posts.
        """
        result = (
            self._sb.table("posts")
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
        data = result.data or []
        return data[0] if data else None

    def get_post_with_ownership(self, post_id: str) -> dict | None:
        """Fetch post id, user_id, is_deleted fields for ownership checks."""
        result = (
            self._sb.table("posts")
            .select("id, user_id, is_deleted")
            .eq("id", post_id)
            .maybe_single()
            .execute()
        )
        return result.data or None

    def get_active_post(self, post_id: str) -> dict | None:
        """Fetch post id only, filtering out deleted posts."""
        result = (
            self._sb.table("posts")
            .select("id")
            .eq("id", post_id)
            .eq("is_deleted", False)
            .maybe_single()
            .execute()
        )
        return result.data or None

    # ------------------------------------------------------------------
    # posts table — writes
    # ------------------------------------------------------------------

    def insert_post(self, post_row: dict) -> dict:
        """Insert a new post row and return the created row."""
        result = self._sb.table("posts").insert(post_row).execute()
        return result.data[0]

    def soft_delete_post(self, post_id: str, now_utc: str) -> None:
        """Soft-delete a post by setting is_deleted=True."""
        self._sb.table("posts").update({
            "is_deleted": True,
            "updated_at": now_utc,
        }).eq("id", post_id).execute()

    # ------------------------------------------------------------------
    # comments table
    # ------------------------------------------------------------------

    def get_comments_page(
        self,
        post_id: str,
        fetch_limit: int,
        cursor: str | None = None,
        sort: str = "oldest",
    ) -> list[dict]:
        """Fetch a page of non-deleted comments with joined user profile.

        Cursor format: ``{created_at}|{id}`` (composite) to avoid skipping records
        that share the same timestamp.

        ``sort`` must be ``"oldest"`` (ascending, default) or ``"newest"`` (descending).
        """
        desc = sort == "newest"
        query = (
            self._sb.table("comments")
            .select("id, post_id, user_id, content, is_deleted, created_at, users(display_name, avatar_storage_key)")
            .eq("post_id", post_id)
            .eq("is_deleted", False)
            .order("created_at", desc=desc)
            .order("id", desc=desc)
            .limit(fetch_limit)
        )
        if cursor:
            cursor_created_at, cursor_id = cursor.split("|", 1)
            if desc:
                # Newest-first: rows before the cursor
                query = query.or_(
                    f"created_at.lt.{cursor_created_at},"
                    f"and(created_at.eq.{cursor_created_at},id.lt.{cursor_id})"
                )
            else:
                # Oldest-first: rows after the cursor
                query = query.or_(
                    f"created_at.gt.{cursor_created_at},"
                    f"and(created_at.eq.{cursor_created_at},id.gt.{cursor_id})"
                )
        result = query.execute()
        return result.data or []

    def insert_comment_atomic(self, p_post_id: str, p_user_id: str, p_content: str) -> dict:
        """Atomically insert a comment and increment the post comment count.

        Calls the insert_comment_atomic RPC and returns the created comment row.
        """
        result = self._sb.rpc("insert_comment_atomic", {
            "p_post_id": p_post_id,
            "p_user_id": p_user_id,
            "p_content": p_content,
        }).execute()
        return result.data[0]

    # ------------------------------------------------------------------
    # reports table
    # ------------------------------------------------------------------

    def insert_report(self, post_id: str, reporter_user_id: str, reason: str | None) -> dict:
        """Insert a report row and return the created row."""
        result = self._sb.table("reports").insert({
            "post_id": post_id,
            "reporter_user_id": reporter_user_id,
            "reason": reason,
        }).execute()
        return result.data[0]

    def count_unique_reporters(self, post_id: str) -> int:
        """Count distinct reporters for a post."""
        result = (
            self._sb.table("reports")
            .select("reporter_user_id")
            .eq("post_id", post_id)
            .execute()
        )
        unique_reporters = {r["reporter_user_id"] for r in (result.data or [])}
        return len(unique_reporters)

    def hide_post(self, post_id: str) -> None:
        """Set is_hidden=true on a post (auto-hide on report threshold)."""
        self._sb.table("posts").update({"is_hidden": True}).eq("id", post_id).execute()

    def unhide_post(self, post_id: str) -> None:
        """Set is_hidden=false on a post (admin un-hide)."""
        self._sb.table("posts").update({"is_hidden": False}).eq("id", post_id).execute()

    # ------------------------------------------------------------------
    # users table — comment author profile (used in posts context)
    # ------------------------------------------------------------------

    def get_commenter_profile(self, user_id: str) -> dict | None:
        """Fetch display_name and avatar_storage_key for a comment author."""
        result = (
            self._sb.table("users")
            .select("display_name, avatar_storage_key")
            .eq("id", user_id)
            .maybe_single()
            .execute()
        )
        return result.data or None
