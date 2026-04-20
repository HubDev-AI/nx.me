"""Post repository — all posts/comments/reports supabase queries in one place.

Follows the same pattern as UserRepository: constructor takes a Client,
methods are synchronous (callers use run_sync for async handlers).
"""

from __future__ import annotations

import logging
from datetime import datetime

from supabase import Client

logger = logging.getLogger(__name__)

# Upper bound on rows fetched when aggregating latest-post-per-user for the
# public-cards listing. Sized to handle ~10k users with avg 10 posts each.
# The endpoint's sole consumer is the card-web sitemap (low frequency, ISR
# cached for 24h). TODO: replace this Python-side aggregation with a Postgres
# RPC (SELECT username, MAX(updated_at) ... GROUP BY user_id) once the user
# base approaches this cap.
_SITEMAP_USER_CURSOR_MAX_ROWS = 100_000


def _parse_iso_datetime(value: str | datetime) -> datetime:
    """Coerce a Supabase timestamp value to ``datetime``.

    supabase-py returns JSON strings for ``timestamptz`` columns; tests
    occasionally pass native ``datetime`` instances. Handles both.
    """
    if isinstance(value, datetime):
        return value
    # Postgres emits "+00:00"; datetime.fromisoformat accepts that in 3.11+.
    # Trailing "Z" is tolerated for safety.
    normalised = value.replace("Z", "+00:00") if value.endswith("Z") else value
    return datetime.fromisoformat(normalised)


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
                "reaction_count, comment_count, glow_up_job_id, share_hash"
            )
            .eq("user_id", user_id)
            .eq("is_deleted", False)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        data = result.data or []
        return data[0] if data else None

    def get_by_share_hash(self, user_id: str, share_hash: str) -> dict | None:
        """Fetch a non-deleted post by share_hash for the given user."""
        result = (
            self._sb.table("posts")
            .select(
                "id, before_image_url, after_image_url, "
                "reaction_count, comment_count, glow_up_job_id, share_hash"
            )
            .eq("user_id", user_id)
            .eq("share_hash", share_hash)
            .eq("is_deleted", False)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    def list_public_user_cursor(
        self,
        cursor: tuple[datetime, str] | None,
        limit: int,
    ) -> list[dict]:
        """Return the next page of users with at least one non-deleted post.

        Each result has shape ``{"username": str, "updated_at": datetime}`` where
        ``updated_at`` is the max(posts.updated_at) across that user's
        non-deleted posts. Results are sorted ``(updated_at DESC, username ASC)``
        for stable keyset pagination — ``username`` is the tie-breaker.

        The cursor is a strict upper bound: the returned rows satisfy
        ``(updated_at, username) < cursor`` in lexicographic order.

        The returned list length is at most ``limit + 1`` — the caller uses the
        extra row (if present) to derive ``next_cursor`` without a second query.

        Implementation note: the supabase-py client does not expose SQL
        ``GROUP BY``, so aggregation happens in Python. The upstream query
        uses a PostgREST inner-join against users so rows whose owner has
        been hard-deleted drop out naturally (the row is gone). An
        upper-bound fetch cap guards against runaway memory — the sole
        caller is the card-web sitemap (a single low-frequency reader).

        Known boundary quirk: because the pre-filter is ``lte(updated_at)``
        (not a tuple filter, which PostgREST does not express), a user whose
        newest post lands between page fetches can reappear on a later page
        with a stale ``updated_at``. Acceptable for the sitemap caller —
        Google dedupes URLs and uses the fresher ``lastmod`` — but **do not**
        reuse this method for a general listing without replacing it with a
        DB-side aggregation.
        """
        cursor_updated_at, cursor_username = (
            cursor if cursor is not None else (None, None)
        )

        query = (
            self._sb.table("posts")
            .select("user_id, updated_at, users!inner(username)")
            .eq("is_deleted", False)
            .order("updated_at", desc=True)
        )

        # Cursor pre-filter: rows strictly before the cursor's updated_at are
        # definitely in scope. Rows equal to the cursor's updated_at need the
        # tuple tie-break applied in Python (after aggregation).
        if cursor_updated_at is not None:
            query = query.lte("updated_at", cursor_updated_at.isoformat())

        query = query.limit(_SITEMAP_USER_CURSOR_MAX_ROWS)
        rows = query.execute().data or []

        # Fold posts → latest per user (username, max updated_at).
        latest: dict[str, tuple[str, datetime]] = {}
        for row in rows:
            user_id = row.get("user_id")
            updated_at_raw = row.get("updated_at")
            user_obj = row.get("users") or {}
            username = user_obj.get("username")
            if not user_id or not updated_at_raw or not username:
                continue
            # supabase returns ISO-8601 strings; normalise to datetime for comparison.
            updated_at = _parse_iso_datetime(updated_at_raw)
            current = latest.get(user_id)
            if current is None or updated_at > current[1]:
                latest[user_id] = (username, updated_at)

        # Sort: updated_at DESC, username ASC.
        sorted_items = sorted(
            latest.values(),
            key=lambda item: (-item[1].timestamp(), item[0]),
        )

        # Apply strict cursor filter after aggregation. The comparator must
        # match the sort order (updated_at DESC, username ASC) — a naive
        # lexicographic tuple `<` would drop users whose updated_at matches
        # the cursor but whose username is alphabetically after it.
        if cursor is not None:
            sorted_items = [
                item
                for item in sorted_items
                if item[1] < cursor_updated_at
                or (item[1] == cursor_updated_at and item[0] > cursor_username)
            ]

        # Return limit + 1 so the caller can compute next_cursor.
        page = sorted_items[: limit + 1]
        return [
            {"username": username, "updated_at": updated_at}
            for username, updated_at in page
        ]

    def get_post_with_ownership(self, post_id: str) -> dict | None:
        """Fetch post id, user_id, is_deleted fields for ownership checks."""
        result = (
            self._sb.table("posts")
            .select("id, user_id, is_deleted")
            .eq("id", post_id)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    def get_by_glow_up_job_id(self, glow_up_job_id: str) -> dict | None:
        """Fetch the live post for a glow-up job, or None.

        "Live" matches the partial unique index predicate from migration
        0046: ``is_deleted = FALSE AND is_hidden = FALSE``. Under that
        index there is at most one matching row; the partial constraint
        guarantees uniqueness, so ``limit(1)`` is defensive rather than
        load-bearing.

        Used by ``create_post`` to resolve the 23505 idempotency path:
        when an insert races another caller and fires unique_violation,
        the existing live post is returned to the caller as 200.
        """
        result = (
            self._sb.table("posts")
            .select(
                "id, user_id, glow_up_job_id, caption, "
                "before_image_url, after_image_url, created_at, share_hash"
            )
            .eq("glow_up_job_id", glow_up_job_id)
            .eq("is_deleted", False)
            .eq("is_hidden", False)
            .limit(1)
            .execute()
        )
        data = result.data or []
        return data[0] if data else None

    def get_active_by_glow_up_job_id(self, glow_up_job_id: str) -> dict | None:
        """Fetch ``{id, share_hash}`` for the live post of a glow-up job, or None.

        Same filter predicate as ``get_by_glow_up_job_id`` (partial unique
        index from migration 0046: ``is_deleted = FALSE AND is_hidden =
        FALSE``), but with a narrower projection for the hot-path status
        poll. Used by ``GET /jobs/{job_id}`` to populate
        ``JobStatusResponse.post_id`` / ``share_hash`` when a completed
        glow-up has a visible public post.

        Kept separate from ``get_by_glow_up_job_id`` on purpose — that
        method's wider projection feeds the ``PostResponse`` idempotency
        body in ``create_post``; this one runs on every status poll and
        should move as few columns as possible.
        """
        result = (
            self._sb.table("posts")
            .select("id, share_hash")
            .eq("glow_up_job_id", glow_up_job_id)
            .eq("is_deleted", False)
            .eq("is_hidden", False)
            .limit(1)
            .execute()
        )
        data = result.data or []
        return data[0] if data else None

    def get_active_post(self, post_id: str) -> dict | None:
        """Fetch post id + owner, filtering out deleted posts.

        Callers (comments, reports) need ``user_id`` to run author/block
        checks, so include it alongside ``id`` in the narrow projection.
        """
        result = (
            self._sb.table("posts")
            .select("id, user_id")
            .eq("id", post_id)
            .eq("is_deleted", False)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    # ------------------------------------------------------------------
    # posts table — writes
    # ------------------------------------------------------------------

    def insert_post(self, post_row: dict) -> dict:
        """Insert a new post row and return the created row."""
        result = self._sb.table("posts").insert(post_row).execute()
        return result.data[0]

    def soft_delete_post(self, post_id: str, now_utc: str) -> None:
        """Soft-delete a post by setting is_deleted=True."""
        self._sb.table("posts").update(
            {
                "is_deleted": True,
                "updated_at": now_utc,
            }
        ).eq("id", post_id).execute()

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
            .select(
                "id, post_id, user_id, content, is_deleted, created_at, users(display_name, avatar_storage_key)"
            )
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

    def insert_comment_atomic(
        self, p_post_id: str, p_user_id: str, p_content: str
    ) -> dict:
        """Atomically insert a comment and increment the post comment count.

        Calls the insert_comment_atomic RPC and returns the created comment row.
        """
        result = self._sb.rpc(
            "insert_comment_atomic",
            {
                "p_post_id": p_post_id,
                "p_user_id": p_user_id,
                "p_content": p_content,
            },
        ).execute()
        return result.data[0]

    # ------------------------------------------------------------------
    # reports table
    # ------------------------------------------------------------------

    def insert_report(
        self, post_id: str, reporter_user_id: str, reason: str | None
    ) -> dict:
        """Insert a report row and return the created row."""
        result = (
            self._sb.table("reports")
            .insert(
                {
                    "post_id": post_id,
                    "reporter_user_id": reporter_user_id,
                    "reason": reason,
                }
            )
            .execute()
        )
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
        return result.data if result else None
