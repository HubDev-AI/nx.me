"""Upload repository — all supabase.table('uploads') queries in one place.

Follows the same pattern as other repositories: constructor takes a Client,
methods are synchronous (callers use run_sync for async handlers).

Key invariant: last_accessed_at is reset to NOW() on every read to keep
the 30-day retention clock rolling (Q19 / Phase 5 retention worker).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from supabase import Client

logger = logging.getLogger(__name__)

# Columns returned for callers that need the full upload row.
UPLOAD_FULL_SELECT = (
    "id, user_id, image_url, nsfw_result, face_detected, "
    "last_accessed_at, mst_bin, created_at"
)


class UploadRepository:
    """Encapsulates all DB calls related to the uploads table."""

    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    # ------------------------------------------------------------------
    # Read (always reset last_accessed_at — Q19 retention clock)
    # ------------------------------------------------------------------

    def get_by_id(self, upload_id: str, *, touch_access: bool = True) -> dict | None:
        """Fetch an upload by ID, resetting last_accessed_at. Returns None if not found.

        ``touch_access`` (default True) controls whether this read refreshes the
        retention clock. User-initiated reads should leave it True (spec Q19 —
        retention clock resets when the user returns). Internal machinery that
        reads the row as part of a non-user-visible flow (e.g. the worker
        fetching a storage key during generation) must pass ``touch_access=False``
        so retention keeps decaying correctly for dormant users.
        """
        if touch_access:
            now_utc = datetime.now(tz=timezone.utc).isoformat()
            # Update last_accessed_at first, then fetch — guarantees the clock
            # is always reset even if the fetch itself is the only read.
            self._sb.table("uploads").update({"last_accessed_at": now_utc}).eq(
                "id", upload_id
            ).execute()

        result = (
            self._sb.table("uploads")
            .select(UPLOAD_FULL_SELECT)
            .eq("id", upload_id)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    def get_by_id_for_owner_check(
        self, upload_id: str, user_id: str, *, touch_access: bool = True
    ) -> dict | None:
        """Fetch upload by ID + user_id in one query. Resets last_accessed_at.

        Returns the row if it belongs to user_id, None otherwise.
        Avoids a separate ownership check round-trip.

        ``touch_access`` — see ``get_by_id``; default True matches user-initiated
        semantics, pass False for internal preflight checks.
        """
        if touch_access:
            now_utc = datetime.now(tz=timezone.utc).isoformat()
            self._sb.table("uploads").update({"last_accessed_at": now_utc}).eq(
                "id", upload_id
            ).eq("user_id", user_id).execute()

        result = (
            self._sb.table("uploads")
            .select(UPLOAD_FULL_SELECT)
            .eq("id", upload_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    def list_for_user(
        self,
        user_id: str,
        limit: int,
        cursor: str | None = None,
    ) -> list[dict]:
        """Fetch uploads for a user, newest-first, cursor-paginated.

        Cursor format: "{created_at}|{id}" composite string.
        Returns at most *limit* rows (caller adds 1 to detect has_more).
        Also resets last_accessed_at on returned rows to keep the retention
        clock rolling (Q19).
        """
        # Columns needed for history assembly (glowup_analyses joined in Python).
        select_cols = "id, user_id, image_url, created_at"

        query = self._sb.table("uploads").select(select_cols).eq("user_id", user_id)

        if cursor:
            parts = cursor.split("|", 1)
            if len(parts) == 2:
                cursor_ts, cursor_id = parts
                # Rows where (created_at, id) < (cursor_ts, cursor_id) DESC
                query = query.or_(
                    f"created_at.lt.{cursor_ts},"
                    f"and(created_at.eq.{cursor_ts},id.lt.{cursor_id})"
                )

        result = (
            query.order("created_at", desc=True)
            .order("id", desc=True)
            .limit(limit)
            .execute()
        )
        rows: list[dict] = result.data or []

        # Touch last_accessed_at in bulk to keep retention clock alive.
        if rows:
            ids = [r["id"] for r in rows]
            now_utc = datetime.now(tz=timezone.utc).isoformat()
            self._sb.table("uploads").update({"last_accessed_at": now_utc}).in_(
                "id", ids
            ).execute()

        return rows

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def insert(self, row: dict) -> dict:
        """Insert a new uploads row. Returns the inserted row."""
        result = self._sb.table("uploads").insert(row).execute()
        return result.data[0] if result.data else {}

    def update(self, upload_id: str, update_data: dict) -> list[dict]:
        """Generic update for an uploads row by ID. Returns updated rows."""
        result = (
            self._sb.table("uploads").update(update_data).eq("id", upload_id).execute()
        )
        return result.data or []
