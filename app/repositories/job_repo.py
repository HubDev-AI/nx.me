"""Job repository — all supabase queries for glow_up_jobs and usage_events.

Follows the same pattern as UserRepository: constructor takes a Client,
methods are synchronous (callers use run_sync for async handlers).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from supabase import Client

logger = logging.getLogger(__name__)

# Columns needed for job status polling
JOB_STATUS_SELECT = (
    "id, user_id, status, queue_lane, updated_at, "
    "original_image_id, generated_image_id, failure_reason, "
    "identity_preserved, credit_reservation_id"
)


class JobRepository:
    """Encapsulates all DB calls related to glow_up_jobs and usage_events."""

    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    # ------------------------------------------------------------------
    # glow_up_jobs — read
    # ------------------------------------------------------------------

    def get_for_analysis(self, job_id: str) -> dict | None:
        """Fetch analysis_id from a glow_up_job row (for shareable card).

        Returns a dict with analysis_id, or None if the job is not found.
        """
        result = (
            self._sb.table("glow_up_jobs")
            .select("analysis_id")
            .eq("id", job_id)
            .maybe_single()
            .execute()
        )
        if not result or not result.data:
            return None
        return result.data

    def get_by_id(self, job_id: str) -> dict | None:
        """Fetch a single job by ID. Returns None if not found."""
        result = (
            self._sb.table("glow_up_jobs")
            .select("*")
            .eq("id", job_id)
            .maybe_single()
            .execute()
        )
        return result.data or None

    def get_by_id_with_fields(self, job_id: str, fields: str) -> dict | None:
        """Fetch a job by ID selecting specific fields. Returns None if not found."""
        result = (
            self._sb.table("glow_up_jobs")
            .select(fields)
            .eq("id", job_id)
            .maybe_single()
            .execute()
        )
        return result.data or None

    def get_by_id_single(self, job_id: str) -> dict:
        """Fetch a single job by ID using .single() (raises if not found)."""
        result = (
            self._sb.table("glow_up_jobs")
            .select("*")
            .eq("id", job_id)
            .single()
            .execute()
        )
        return result.data

    def get_by_idempotency_key(self, key: str, user_id: str) -> dict | None:
        """Check for an existing job by idempotency key + user. Returns None if not found."""
        result = (
            self._sb.table("glow_up_jobs")
            .select("id, status")
            .eq("idempotency_key", key)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        return result.data or None

    def get_for_status_poll(self, job_id: str) -> dict | None:
        """Fetch job fields needed for GET /jobs/{job_id} status polling."""
        result = (
            self._sb.table("glow_up_jobs")
            .select(JOB_STATUS_SELECT)
            .eq("id", job_id)
            .maybe_single()
            .execute()
        )
        return result.data or None

    def get_for_cancel(self, job_id: str) -> dict | None:
        """Fetch job fields needed for cancel operation."""
        result = (
            self._sb.table("glow_up_jobs")
            .select("id, user_id, status, credit_reservation_id")
            .eq("id", job_id)
            .maybe_single()
            .execute()
        )
        return result.data or None

    def get_for_refund(self, job_id: str) -> dict | None:
        """Fetch job fields needed for refund operation."""
        result = (
            self._sb.table("glow_up_jobs")
            .select("id, user_id, status, credit_reservation_id")
            .eq("id", job_id)
            .maybe_single()
            .execute()
        )
        return result.data or None

    def get_jobs_for_post(self, job_id: str) -> dict | None:
        """Fetch job fields needed for post creation. Returns None if not found."""
        result = (
            self._sb.table("glow_up_jobs")
            .select("id, user_id, status, original_image_id, generated_image_id")
            .eq("id", job_id)
            .maybe_single()
            .execute()
        )
        return result.data or None

    def get_completed_jobs_for_analyses(self, analysis_ids: list[str]) -> list[dict]:
        """Fetch latest completed glow_up_jobs for a list of analysis IDs (for history)."""
        result = (
            self._sb.table("glow_up_jobs")
            .select("analysis_id, generated_image_id, created_at")
            .in_("analysis_id", analysis_ids)
            .eq("status", "completed")
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    def get_stuck_jobs(self, cutoff: str) -> list[dict]:
        """Fetch jobs stuck in 'processing' or 'finalizing' state before the given UTC cutoff."""
        result = (
            self._sb.table("glow_up_jobs")
            .select("id, credit_reservation_id, status")
            .in_("status", ["processing", "finalizing"])
            .lt("updated_at", cutoff)
            .execute()
        )
        return result.data or []

    # ------------------------------------------------------------------
    # glow_up_jobs — write
    # ------------------------------------------------------------------

    def create(self, job_data: dict) -> dict:
        """Insert a new job row. Returns the inserted row."""
        result = self._sb.table("glow_up_jobs").insert(job_data).execute()
        return result.data[0] if result.data else {}

    def update(self, job_id: str, update_data: dict) -> list[dict]:
        """Generic update for a job row by ID. Returns updated rows."""
        result = (
            self._sb.table("glow_up_jobs")
            .update(update_data)
            .eq("id", job_id)
            .execute()
        )
        return result.data or []

    def claim(self, job_id: str) -> list[dict]:
        """Conditionally transition job from queued → processing.

        Uses eq('status', 'queued') to guard against double-claim.
        Returns updated rows (empty if job was not in queued state).
        """
        now_utc = datetime.now(tz=timezone.utc).isoformat()
        result = (
            self._sb.table("glow_up_jobs")
            .update({
                "status": "processing",
                "updated_at": now_utc,
            })
            .eq("id", job_id)
            .eq("status", "queued")
            .execute()
        )
        return result.data or []

    # ------------------------------------------------------------------
    # usage_events
    # ------------------------------------------------------------------

    def insert_usage_event(self, event_data: dict) -> dict:
        """Insert a usage_events row. Returns the inserted row."""
        result = self._sb.table("usage_events").insert(event_data).execute()
        return result.data[0] if result.data else {}

    def get_usage_event_status(self, job_id: str) -> str | None:
        """Get the current status of the usage_event for a job.

        Returns the status string ('reserved', 'committed', 'released',
        'refunded') or None if no event exists.
        """
        result = (
            self._sb.table("usage_events")
            .select("status")
            .eq("job_id", job_id)
            .maybe_single()
            .execute()
        )
        if result.data:
            return result.data.get("status")
        return None

    def update_usage_event(self, job_id: str, update_data: dict) -> list[dict]:
        """Update usage_events rows for a given job_id (e.g. cancel/refund)."""
        result = (
            self._sb.table("usage_events")
            .update(update_data)
            .eq("job_id", job_id)
            .execute()
        )
        return result.data or []
