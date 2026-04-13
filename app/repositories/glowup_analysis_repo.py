"""Glowup analysis repository — all supabase.table('glowup_analyses') queries.

Follows the same pattern as other repositories: constructor takes a Client,
methods are synchronous (callers use run_sync for async handlers).

One glowup_analysis per upload (enforced by DB unique index on upload_id).
"""

from __future__ import annotations

import logging

from supabase import Client

logger = logging.getLogger(__name__)

# Columns returned for most read operations.
GLOWUP_ANALYSIS_FULL_SELECT = (
    "id, upload_id, face_shape, symmetry_score, recommendations, created_at"
)


class GlowupAnalysisRepository:
    """Encapsulates all DB calls related to the glowup_analyses table."""

    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_by_id(self, analysis_id: str) -> dict | None:
        """Fetch a glowup analysis by ID. Returns None if not found."""
        result = (
            self._sb.table("glowup_analyses")
            .select(GLOWUP_ANALYSIS_FULL_SELECT)
            .eq("id", analysis_id)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    def get_by_upload_id(self, upload_id: str) -> dict | None:
        """Fetch the glowup analysis for a given upload (at most one). Returns None if not found."""
        result = (
            self._sb.table("glowup_analyses")
            .select(GLOWUP_ANALYSIS_FULL_SELECT)
            .eq("upload_id", upload_id)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    def get_for_worker(self, analysis_id: str) -> dict | None:
        """Fetch fields needed by the generation worker.

        Returns face_shape, symmetry_score, and recommendations; or None
        if the analysis does not exist.
        """
        result = (
            self._sb.table("glowup_analyses")
            .select("face_shape, symmetry_score, recommendations")
            .eq("id", analysis_id)
            .single()
            .execute()
        )
        return result.data if result else None

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def insert(self, row: dict) -> dict:
        """Insert a new glowup_analyses row. Returns the inserted row."""
        result = self._sb.table("glowup_analyses").insert(row).execute()
        return result.data[0] if result.data else {}
