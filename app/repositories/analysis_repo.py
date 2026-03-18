"""Analysis repository — all supabase.table('analyses') queries in one place.

Follows the same pattern as UserRepository: constructor takes a Client,
methods are synchronous (callers use run_sync for async handlers).
"""
from __future__ import annotations

import logging

from supabase import Client

logger = logging.getLogger(__name__)


class AnalysisRepository:
    """Encapsulates all DB calls related to the analyses table."""

    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_for_generation(self, analysis_id: str) -> dict | None:
        """Fetch analysis fields needed for generation validation.

        Returns id, user_id, status, and original_image_id; or None if
        the analysis does not exist.
        """
        result = (
            self._sb.table("analyses")
            .select("id, user_id, status, original_image_id")
            .eq("id", analysis_id)
            .maybe_single()
            .execute()
        )
        return result.data or None

    def get_for_worker(self, analysis_id: str) -> dict | None:
        """Fetch analysis fields needed by the generation worker.

        Returns face_shape, symmetry_score, and recommendations; or None
        if the analysis does not exist.
        """
        result = (
            self._sb.table("analyses")
            .select("face_shape, symmetry_score, recommendations")
            .eq("id", analysis_id)
            .single()
            .execute()
        )
        return result.data or None

    def get_by_id(self, analysis_id: str) -> dict | None:
        """Fetch an analysis by ID, or None if not found."""
        result = (
            self._sb.table("analyses")
            .select("*")
            .eq("id", analysis_id)
            .maybe_single()
            .execute()
        )
        return result.data or None

    def list_for_user(
        self,
        user_id: str,
        limit: int,
        cursor: str | None = None,
    ) -> list[dict]:
        """Return analyses for a user in reverse chronological order.

        Args:
            user_id: Owner's user ID.
            limit: Maximum number of rows to fetch.
            cursor: Optional composite cursor ``{created_at}|{id}``; only rows
                before the cursor position are returned (exclusive).  Plain
                ``created_at`` strings are still accepted for back-compat.
        """
        query = (
            self._sb.table("analyses")
            .select("id, original_image_id, face_shape, symmetry_score, recommendations, status, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .order("id", desc=True)
            .limit(limit)
        )
        if cursor:
            if "|" in cursor:
                cursor_created_at, cursor_id = cursor.split("|", 1)
                # Rows before cursor (DESC): same created_at and id < cursor_id, OR created_at < cursor_created_at
                query = query.or_(
                    f"created_at.lt.{cursor_created_at},"
                    f"and(created_at.eq.{cursor_created_at},id.lt.{cursor_id})"
                )
            else:
                # Legacy plain timestamp cursor
                query = query.lt("created_at", cursor)
        result = query.execute()
        return result.data or []

    def get_recommendations(self, analysis_id: str) -> list[dict]:
        """Fetch the recommendations JSON array for a single analysis.

        Returns an empty list if the analysis is not found.
        """
        result = (
            self._sb.table("analyses")
            .select("recommendations")
            .eq("id", analysis_id)
            .maybe_single()
            .execute()
        )
        if not result.data:
            return []
        return result.data.get("recommendations") or []

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def insert(self, row: dict) -> None:
        """Insert a new analyses row."""
        self._sb.table("analyses").insert(row).execute()
