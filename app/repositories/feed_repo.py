"""Feed repository — all feed/reaction supabase queries in one place.

Follows the same pattern as PostRepository: constructor takes a Client,
methods are synchronous (callers use run_sync for async handlers).
"""

from __future__ import annotations

import logging

from supabase import Client

logger = logging.getLogger(__name__)

_POST_COLUMNS = (
    "id, user_id, caption, before_image_url, after_image_url, "
    "reaction_count, comment_count, created_at, "
    "before_image_id, after_image_id, "
    "username, display_name, avatar_storage_key, kind"
)


class FeedRepository:
    """Encapsulates all DB calls related to the feed views and reactions."""

    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    # ------------------------------------------------------------------
    # v_feed_posts view — feed queries
    # ------------------------------------------------------------------

    def fetch_newest(
        self,
        cursor: str | None,
        limit: int,
        excluded_user_ids: set[str] | None = None,
    ) -> list[dict]:
        """Fetch posts ordered by created_at DESC.

        Uses v_feed_posts view which JOINs images to enforce AC-D7
        (both images must be 'cleared') at the database level.
        Hidden posts (auto-hidden via report threshold) are excluded.
        Posts by excluded_user_ids (blocked/blocking) are filtered out.
        """
        query = (
            self._sb.table("v_feed_posts")
            .select(_POST_COLUMNS)
            .order("created_at", desc=True)
            .limit(limit)
        )

        if cursor:
            query = query.lt("created_at", cursor)

        if excluded_user_ids:
            query = query.not_.in_("user_id", list(excluded_user_ids))

        result = query.execute()
        return result.data or []

    def fetch_trending(
        self,
        cursor: str | None,
        limit: int,
        excluded_user_ids: set[str] | None = None,
    ) -> list[dict]:
        """Fetch posts ordered by HN-style time-decay score via feed_trending RPC.

        score = reaction_count / POWER(hours_since_post + 2, 1.5)
        Computed in SQL so sorting, filtering, and pagination happen in the DB.
        """
        params: dict = {"p_limit": limit}

        if cursor:
            parts = cursor.split("|", 2)
            if len(parts) == 3:
                params["p_cursor_score"] = float(parts[0])
                params["p_cursor_created"] = parts[1]
                params["p_cursor_id"] = parts[2]

        if excluded_user_ids:
            params["p_excluded_user_ids"] = list(excluded_user_ids)

        result = self._sb.rpc("feed_trending", params).execute()
        return result.data or []

    def fetch_biggest_improvements(
        self,
        cursor: str | None,
        limit: int,
        excluded_user_ids: set[str] | None = None,
    ) -> list[dict]:
        """Fetch posts ordered by reaction_count DESC (AC-U10: no AI scores).

        Uses feed_biggest_improvements() SQL function with tuple-based
        cursor pagination — no over-fetching required.
        """
        params: dict = {"p_limit": limit}

        if cursor:
            parts = cursor.split("|", 2)
            if len(parts) == 3:
                params["p_cursor_reactions"] = int(parts[0])
                params["p_cursor_created"] = parts[1]
                params["p_cursor_id"] = parts[2]

        if excluded_user_ids:
            params["p_excluded_user_ids"] = list(excluded_user_ids)

        result = self._sb.rpc("feed_biggest_improvements", params).execute()
        return result.data or []

    # ------------------------------------------------------------------
    # posts table — reaction validation
    # ------------------------------------------------------------------

    def get_post_for_reaction(self, post_id: str) -> dict | None:
        """Fetch id and reaction_count for an active post (reaction validation)."""
        result = (
            self._sb.table("posts")
            .select("id, reaction_count")
            .eq("id", post_id)
            .eq("is_deleted", False)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    # ------------------------------------------------------------------
    # RPCs — reaction persistence
    # ------------------------------------------------------------------

    def toggle_reaction_atomic(
        self,
        p_post_id: str,
        p_user_id: str,
    ) -> dict:
        """Toggle a reaction for (post, user) and return the new state.

        Returns ``{"reaction_count": int, "has_reacted": bool}``. A second
        call from the same user removes the reaction and decrements the
        counter.
        """
        result = self._sb.rpc(
            "toggle_reaction_atomic",
            {
                "p_post_id": p_post_id,
                "p_user_id": p_user_id,
            },
        ).execute()
        rows = result.data or []
        if not rows:
            raise RuntimeError(
                f"toggle_reaction_atomic returned no rows for post {p_post_id}"
            )
        return rows[0]

    def get_reacted_post_ids(
        self,
        user_id: str,
        post_ids: list[str],
    ) -> set[str]:
        """Return the subset of ``post_ids`` the user has reacted to.

        Used by the feed endpoint to populate ``has_reacted`` per post so
        the UI can render the heart as filled on initial load.
        """
        if not post_ids:
            return set()
        result = (
            self._sb.table("reactions")
            .select("post_id")
            .eq("user_id", user_id)
            .in_("post_id", post_ids)
            .execute()
        )
        return {row["post_id"] for row in (result.data or [])}

    def reconcile_reaction_counts(self, cutoff_iso: str) -> list[dict]:
        """Bulk UPDATE reaction counts from DB truth for posts since cutoff.

        Returns list of rows with updated post IDs.
        """
        result = self._sb.rpc(
            "reconcile_reaction_counts", {"cutoff_iso": cutoff_iso}
        ).execute()
        return result.data or []
