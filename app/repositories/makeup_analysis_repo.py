"""MakeupAnalysisRepository — persistence for per-user analyzer output.

Stores Monk Skin Tone bin, undertone, region anchors, preset ranking, and
consent metadata. Biometric fields (mst_bin, undertone, region_anchors) are
purged at 90 days by a scheduled sweeper via ``delete_older_than``; consent
fields are retained per privacy policy.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from supabase import Client


class MakeupAnalysisRepository:
    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    def insert(self, analysis_data: dict) -> dict:
        """Insert a new makeup_analyses row and return it."""
        result = self._sb.table("makeup_analyses").insert(analysis_data).execute()
        return result.data[0]

    def get_latest_for_user(self, user_id: str) -> dict | None:
        """Return the most recent analysis for a user, or None."""
        result = (
            self._sb.table("makeup_analyses")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
        )
        if not result or not result.data:
            return None
        return result.data

    def nullify_biometric_fields(self, user_id: str) -> None:
        """Wipe biometric columns for a user (right-to-erasure / purge path).

        Sets mst_bin, undertone, region_anchors to NULL for all rows belonging
        to the user. Consent and ranking metadata are retained.
        """
        self._sb.table("makeup_analyses").update(
            {"mst_bin": None, "undertone": None, "region_anchors": None}
        ).eq("user_id", user_id).execute()

    def delete_older_than(self, days: int) -> None:
        """Hard-delete analysis rows older than *days* days (purge sweeper).

        Uses a cutoff timestamp computed in Python so the sweeper job can
        control timezone and precision consistently.
        """
        cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).isoformat()
        self._sb.table("makeup_analyses").delete().lt("created_at", cutoff).execute()
