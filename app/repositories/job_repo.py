"""Job repository — all supabase queries for the polymorphic jobs table.

Follows the same pattern as other repositories: constructor takes a Client,
methods are synchronous (callers use run_sync for async handlers).

The jobs table is polymorphic: source_type + source_id point at either a
glowup_analyses row (today) or a makeup_sessions row (future Makeup feature).
Application-layer integrity only — no DB foreign key for the polymorphic ref.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from supabase import Client

logger = logging.getLogger(__name__)

# Columns needed for job status polling
JOB_STATUS_SELECT = (
    "id, user_id, status, source_type, source_id, updated_at, "
    "before_image_url, after_image_url, failure_reason, saved_at, "
    "identity_preserved, credit_reservation_id"
)

# Source type constant for Glow Up — avoids magic strings in callers.
SOURCE_TYPE_GLOWUP = "glowup_analysis"


class JobRepository:
    """Encapsulates all DB calls related to the jobs table and usage_events."""

    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    # ------------------------------------------------------------------
    # jobs — read
    # ------------------------------------------------------------------

    def get_by_id(self, job_id: str) -> dict | None:
        """Fetch a single job by ID. Returns None if not found."""
        result = (
            self._sb.table("jobs").select("*").eq("id", job_id).maybe_single().execute()
        )
        if not result or not result.data:
            return None
        return result.data

    def get_by_id_with_fields(self, job_id: str, fields: str) -> dict | None:
        """Fetch a job by ID selecting specific fields. Returns None if not found."""
        result = (
            self._sb.table("jobs")
            .select(fields)
            .eq("id", job_id)
            .maybe_single()
            .execute()
        )
        if not result or not result.data:
            return None
        return result.data

    def get_by_id_single(self, job_id: str) -> dict:
        """Fetch a single job by ID using .single() (raises if not found)."""
        result = self._sb.table("jobs").select("*").eq("id", job_id).single().execute()
        return result.data

    def get_by_idempotency_key(self, key: str, user_id: str) -> dict | None:
        """Check for an existing job by idempotency key + user. Returns None if not found."""
        result = (
            self._sb.table("jobs")
            .select("id, status")
            .eq("idempotency_key", key)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if not result or not result.data:
            return None
        return result.data

    def get_for_status_poll(self, job_id: str) -> dict | None:
        """Fetch job fields needed for GET /jobs/{job_id} status polling."""
        result = (
            self._sb.table("jobs")
            .select(JOB_STATUS_SELECT)
            .eq("id", job_id)
            .maybe_single()
            .execute()
        )
        if not result or not result.data:
            return None
        return result.data

    def get_for_cancel(self, job_id: str) -> dict | None:
        """Fetch job fields needed for cancel operation."""
        result = (
            self._sb.table("jobs")
            .select("id, user_id, status, credit_reservation_id")
            .eq("id", job_id)
            .maybe_single()
            .execute()
        )
        if not result or not result.data:
            return None
        return result.data

    def get_for_refund(self, job_id: str) -> dict | None:
        """Fetch job fields needed for refund operation."""
        result = (
            self._sb.table("jobs")
            .select("id, user_id, status, credit_reservation_id")
            .eq("id", job_id)
            .maybe_single()
            .execute()
        )
        if not result or not result.data:
            return None
        return result.data

    def get_for_save(self, job_id: str) -> dict | None:
        """Fetch job fields needed for the save operation."""
        result = (
            self._sb.table("jobs")
            .select("id, user_id, status, saved_at")
            .eq("id", job_id)
            .maybe_single()
            .execute()
        )
        if not result or not result.data:
            return None
        return result.data

    def get_jobs_for_post(self, job_id: str) -> dict | None:
        """Fetch job fields needed for post creation. Returns None if not found."""
        result = (
            self._sb.table("jobs")
            .select("id, user_id, status, before_image_url, after_image_url")
            .eq("id", job_id)
            .maybe_single()
            .execute()
        )
        if not result or not result.data:
            return None
        return result.data

    def get_completed_jobs_for_source(self, source_ids: list[str]) -> list[dict]:
        """Fetch latest completed jobs for a list of source_ids (e.g. for history)."""
        result = (
            self._sb.table("jobs")
            .select("source_id, after_image_url, created_at")
            .in_("source_id", source_ids)
            .eq("status", "completed")
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    def get_completed_jobs_for_sources(
        self, source_type: str, source_ids: list[str]
    ) -> list[dict]:
        """Fetch latest completed jobs for a list of source_ids filtered by source_type.

        Returns rows ordered desc by created_at so callers can take the first
        occurrence per source_id to get the most recent completed job.
        """
        result = (
            self._sb.table("jobs")
            .select("source_id, after_image_url, created_at")
            .eq("source_type", source_type)
            .in_("source_id", source_ids)
            .eq("status", "completed")
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    def get_stuck_jobs(self, cutoff: str) -> list[dict]:
        """Fetch jobs stuck in 'processing' or 'finalizing' state before the given UTC cutoff."""
        result = (
            self._sb.table("jobs")
            .select("id, credit_reservation_id, status")
            .in_("status", ["processing", "finalizing"])
            .lt("updated_at", cutoff)
            .execute()
        )
        return result.data or []

    # ------------------------------------------------------------------
    # jobs — write
    # ------------------------------------------------------------------

    def create(self, job_data: dict) -> dict:
        """Insert a new job row. Returns the inserted row."""
        result = self._sb.table("jobs").insert(job_data).execute()
        return result.data[0] if result.data else {}

    def update(self, job_id: str, update_data: dict) -> list[dict]:
        """Generic update for a job row by ID. Returns updated rows."""
        result = self._sb.table("jobs").update(update_data).eq("id", job_id).execute()
        return result.data or []

    def save(self, job_id: str, user_id: str) -> dict | None:
        """Set saved_at to NOW() for a job owned by user_id. Idempotent.

        Only updates if saved_at IS NULL (first-save semantics). Subsequent
        calls with the same job_id silently succeed by returning the existing
        saved_at via a second fetch.
        Returns the job row (with saved_at populated), or None if not found.
        """
        now_utc = datetime.now(tz=timezone.utc).isoformat()
        # Only set saved_at if it is still NULL — idempotent
        self._sb.table("jobs").update({"saved_at": now_utc}).eq("id", job_id).eq(
            "user_id", user_id
        ).is_("saved_at", None).execute()

        # Fetch the current row (saved_at may have been set in a previous call)
        result = (
            self._sb.table("jobs")
            .select("id, saved_at")
            .eq("id", job_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    def claim(self, job_id: str) -> list[dict]:
        """Conditionally transition job from queued → processing.

        Uses eq('status', 'queued') to guard against double-claim.
        Returns updated rows (empty if job was not in queued state).
        """
        now_utc = datetime.now(tz=timezone.utc).isoformat()
        result = (
            self._sb.table("jobs")
            .update(
                {
                    "status": "processing",
                    "updated_at": now_utc,
                }
            )
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
