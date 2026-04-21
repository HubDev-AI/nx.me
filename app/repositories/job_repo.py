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

from app.services.public_url import (
    GENERATED_IMAGES_BUCKET,
    PUBLIC_BUCKET,
    RAW_SELFIES_BUCKET,
)

logger = logging.getLogger(__name__)

# Columns needed for job status polling. created_at is used by the dev-only
# DEV_GLOWUP_FORCE_404_FOR_NEW_JOBS_SECONDS gate in app/api/jobs.py to
# simulate read-after-write replica lag.
# Makeup-specific columns are included so GET /jobs/{job_id} surfaces them
# for makeup jobs without a separate query path.
JOB_STATUS_SELECT = (
    "id, user_id, status, source_type, source_id, created_at, updated_at, "
    "before_image_url, after_image_url, failure_reason, saved_at, "
    "identity_preserved, credit_reservation_id, "
    "fal_request_id, fal_url, output_key, preset_slug, intensity, "
    "makeup_failure_reason, user_tier_at_enqueue"
)

# Source type constants — avoid magic strings in callers.
SOURCE_TYPE_GLOWUP = "glowup_analysis"
SOURCE_TYPE_MAKEUP = "makeup_session"

# Makeup failure reason codes (distinct from glowup's failure_reason values).
MAKEUP_FAILURE_REFUSED = "refused"
MAKEUP_FAILURE_NON_RETRYABLE = "non_retryable"
MAKEUP_FAILURE_RETRYABLE = "retryable"


class JobRepository:
    """Encapsulates all DB calls related to the jobs table."""

    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    # ------------------------------------------------------------------
    # jobs — read
    # ------------------------------------------------------------------

    def _fetch_by_id(self, job_id: str, fields: str) -> dict | None:
        """Shared shape for every ``jobs`` by-id read using ``.maybe_single()``.

        Returns ``None`` when the row does not exist (``result`` may itself be
        ``None`` when supabase-py returns no row for ``maybe_single``, so both
        null-paths must be guarded).
        """
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

    def get_by_id(self, job_id: str) -> dict | None:
        """Fetch a single job by ID. Returns None if not found."""
        return self._fetch_by_id(job_id, "*")

    def get_by_id_with_fields(self, job_id: str, fields: str) -> dict | None:
        """Fetch a job by ID selecting specific fields. Returns None if not found."""
        return self._fetch_by_id(job_id, fields)

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
        return self._fetch_by_id(job_id, JOB_STATUS_SELECT)

    def get_for_cancel(self, job_id: str) -> dict | None:
        """Fetch job fields needed for cancel operation."""
        return self._fetch_by_id(job_id, "id, user_id, status, credit_reservation_id")

    def get_for_refund(self, job_id: str) -> dict | None:
        """Fetch job fields needed for refund operation."""
        return self._fetch_by_id(
            job_id,
            "id, user_id, status, credit_reservation_id, failure_reason",
        )

    def get_for_save(self, job_id: str) -> dict | None:
        """Fetch job fields needed for the save operation."""
        return self._fetch_by_id(job_id, "id, user_id, status, saved_at")

    def get_jobs_for_post(self, job_id: str) -> dict | None:
        """Fetch job fields needed for post creation. Returns None if not found.

        The tier-3 schema (migration 0034) replaced the old
        ``original_image_id`` / ``generated_image_id`` FK columns with
        the storage-key strings ``before_image_url`` / ``after_image_url``.
        Callers resolve the matching ``images`` rows via
        ``image_repo.get_by_user_storage_key`` to reach the FK IDs
        ``posts`` still expects.
        """
        return self._fetch_by_id(
            job_id,
            "id, user_id, status, before_image_url, after_image_url",
        )

    def get_for_makeup_worker(self, job_id: str) -> dict | None:
        """Fetch fields needed by the makeup worker for processing + terminal writes."""
        return self._fetch_by_id(
            job_id,
            "id, user_id, status, source_id, idempotency_key, "
            "idempotency_key_body_hash, preset_slug, intensity, "
            "credit_reservation_id, user_tier_at_enqueue",
        )

    def get_by_fal_idempotency_key(self, fal_key: str) -> dict | None:
        """Look up a makeup job by the fal-side idempotency key."""
        result = (
            self._sb.table("jobs")
            .select("id, status, output_key, makeup_failure_reason")
            .eq("fal_idempotency_key", fal_key)
            .maybe_single()
            .execute()
        )
        if not result or not result.data:
            return None
        return result.data

    def update_makeup_job_processing(
        self,
        job_id: str,
        fal_request_id: str,
        fal_url: str,
        fal_idempotency_key: str,
        now_utc: str,
    ) -> None:
        """Record the fal request details when the worker submits the job."""
        self._sb.table("jobs").update(
            {
                "status": "processing",
                "fal_request_id": fal_request_id,
                "fal_url": fal_url,
                "fal_idempotency_key": fal_idempotency_key,
                "updated_at": now_utc,
            }
        ).eq("id", job_id).execute()

    def update_makeup_job_completed(
        self,
        job_id: str,
        output_key: str,
        now_utc: str,
    ) -> None:
        """Mark a makeup job as completed with its storage output key."""
        self._sb.table("jobs").update(
            {
                "status": "completed",
                "output_key": output_key,
                "completed_at": now_utc,
                "updated_at": now_utc,
            }
        ).eq("id", job_id).execute()

    def update_makeup_job_failed(
        self,
        job_id: str,
        makeup_failure_reason: str,
        now_utc: str,
    ) -> None:
        """Mark a makeup job as failed with a typed failure reason."""
        self._sb.table("jobs").update(
            {
                "status": "failed",
                "makeup_failure_reason": makeup_failure_reason,
                "updated_at": now_utc,
            }
        ).eq("id", job_id).execute()

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

    def get_latest_jobs_for_sources(
        self,
        source_type: str,
        source_ids: list[str],
        statuses: list[str],
    ) -> list[dict]:
        """Fetch jobs for a list of source_ids filtered by source_type + status set.

        Returns id, status, source_id, after_image_url, created_at, saved_at
        ordered desc by created_at, plus a nested ``posts`` array with each
        post's id/is_deleted/is_hidden flags. Callers take the first occurrence
        per source_id to get the most recent job in any included status. Used
        by the history endpoint to surface non-terminal (queued/processing/
        finalizing) and errored (failed/cancelled) rows on the profile grid
        alongside completed ones.

        The nested ``posts(...)`` select is a LEFT JOIN via the
        ``posts.glow_up_job_id → jobs.id`` foreign key (migration 0045).
        Callers filter the returned array for live rows client-side
        (``is_deleted = FALSE AND is_hidden = FALSE``) — the partial UNIQUE
        index from migration 0046 guarantees at most one live row matches.
        Soft-deleted / auto-hidden rows from prior publish attempts can still
        be present, so the filter step is required.
        """
        result = (
            self._sb.table("jobs")
            .select(
                "id, status, source_id, after_image_url, created_at, saved_at, "
                "posts(id, is_deleted, is_hidden)"
            )
            .eq("source_type", source_type)
            .in_("source_id", source_ids)
            .in_("status", statuses)
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

    def list_expired_unsaved_jobs(self, cutoff: str) -> list[dict]:
        """Fetch unsaved jobs older than ``cutoff`` for nightly retention purge.

        Projection matches what ``enumerate_blob_keys_for_delete`` needs to
        re-derive blob keys per job, plus ``source_type``/``source_id`` so
        callers can extend the purge to analysis rows later if desired.
        The retention worker enumerates via ``enumerate_blob_keys_for_delete``
        (same helper Unit 5's DELETE /v1/jobs path uses) so raw-selfies +
        generated-images + live post-images keys are all captured BEFORE the
        DB DELETE fans out via FK cascade and the posts join dies.

        ``cutoff`` is an ISO-8601 UTC timestamp string.
        """
        result = (
            self._sb.table("jobs")
            .select("id, source_id, source_type, before_image_url, after_image_url")
            .is_("saved_at", "null")
            .lt("created_at", cutoff)
            .execute()
        )
        return result.data or []

    def delete_by_ids(
        self, job_ids: list[str], *, cutoff_iso: str | None = None
    ) -> None:
        """Bulk-hard-delete jobs by ID list with optional retention CAS.

        The FK cascade added in migration 0045 (``posts.glow_up_job_id
        ON DELETE CASCADE``) fans out to ``posts``; pre-existing cascades
        on ``posts.id`` wipe ``reactions``, ``comments``, ``reports``.
        Callers must have already enumerated blob keys before invoking
        this — once the cascade runs the posts join is gone and the
        denormalized post-images keys cannot be recovered.

        ``cutoff_iso`` — when provided, constrains the DELETE with the
        retention purge predicate ``saved_at IS NULL AND created_at <
        cutoff_iso``. This is a compare-and-swap at commit time: any row
        that was Saved (``saved_at`` flipped to non-null) between the
        earlier enumerate and this DELETE is silently skipped rather
        than hard-deleted. Callers that enumerate a purge set MUST pass
        the same cutoff used to assemble that set; the retention worker
        is the only current site.
        """
        if not job_ids:
            return
        query = self._sb.table("jobs").delete().in_("id", job_ids)
        if cutoff_iso is not None:
            query = query.is_("saved_at", "null").lt("created_at", cutoff_iso)
        query.execute()

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
    # Hard-delete cascade (Unit 5) — callers must run enumeration BEFORE
    # ``delete_by_id`` so the FK cascade does not kill the joins used to
    # enumerate post-images storage keys. See
    # ``docs/solutions/best-practices/account-delete-hard-reset-invariant``.
    # ------------------------------------------------------------------

    def enumerate_blob_keys_for_delete(self, job_id: str) -> list[tuple[str, str]]:
        """Return every ``(bucket, storage_key)`` tuple owned by this job.

        Combines the job's own ``before_image_url`` (``raw-selfies``) and
        ``after_image_url`` (``generated-images``) with the denormalized
        ``posts.before_image_url`` + ``posts.after_image_url`` columns for
        the live public post (if any). Same enumeration contract as
        ``user_repo.list_user_storage_keys`` so the delete-glowup and
        delete-account paths stay symmetric — see the plan's
        "API surface parity" line.

        Only ``post-images`` keys from a live post (``is_deleted = FALSE
        AND is_hidden = FALSE``) are returned. Hidden / soft-deleted posts
        are left alone — their blobs are reclaimed by nightly retention.

        Returns ``[]`` when the job does not exist. Safe to call multiple
        times; idempotent because every call re-queries from source.

        Delegates to ``_job_own_blob_keys`` (``None`` signals a missing job
        so the live-post lookup is skipped, preserving the single-query
        behaviour for that branch) and ``_live_post_blob_keys``.
        """
        job_keys = self._job_own_blob_keys(job_id)
        if job_keys is None:
            # Job does not exist — preserve the empty-list contract and skip
            # the post lookup so we issue a single query for the missing-job case.
            return []
        return job_keys + self._live_post_blob_keys(job_id)

    def _job_own_blob_keys(self, job_id: str) -> list[tuple[str, str]] | None:
        """Keys for the job's own ``before_image_url`` + ``after_image_url``.

        Returns ``None`` when the job row is missing so the caller can
        distinguish "no job" from "job exists but has no image URLs yet".
        """
        row = self._fetch_by_id(job_id, "before_image_url, after_image_url")
        if row is None:
            return None
        keys: list[tuple[str, str]] = []
        before = row.get("before_image_url")
        after = row.get("after_image_url")
        if before:
            keys.append((RAW_SELFIES_BUCKET, before))
        if after:
            keys.append((GENERATED_IMAGES_BUCKET, after))
        return keys

    def _live_post_blob_keys(self, job_id: str) -> list[tuple[str, str]]:
        """Keys for the live public post row (if any) linked to this job.

        Partial unique index (migration 0046) guarantees at most one row;
        deleted/hidden posts are skipped — their blobs are reclaimed by
        nightly retention, not the per-job delete path.
        """
        result = (
            self._sb.table("posts")
            .select("before_image_url, after_image_url")
            .eq("glow_up_job_id", job_id)
            .eq("is_deleted", False)
            .eq("is_hidden", False)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return []
        row = rows[0]
        keys: list[tuple[str, str]] = []
        before = row.get("before_image_url")
        after = row.get("after_image_url")
        if before:
            keys.append((PUBLIC_BUCKET, before))
        if after:
            keys.append((PUBLIC_BUCKET, after))
        return keys

    def count_peer_jobs_for_source(
        self,
        source_id: str,
        *,
        exclude_id: str,
        exclude_statuses: set[str] | None = None,
    ) -> int:
        """Count jobs sharing a ``source_id`` (excluding this job).

        Peer definition (per plan §Key Technical Decisions):
          ``source_id = this.source_id AND id != this.id AND status NOT IN
          (exclude_statuses)``

        The endpoint passes ``exclude_statuses={"cancelled"}`` — a
        cancelled peer has already released its reservation and does not
        keep the analysis alive, so we want those treated as "gone" for
        ref-counting. ``queued|processing|finalizing|completed|failed``
        peers DO keep the analysis. Cheap: an indexed equality scan on
        ``jobs.source_id``.
        """
        exclude_statuses = exclude_statuses or set()
        query = (
            self._sb.table("jobs")
            .select("id", count="exact")
            .eq("source_id", source_id)
            .neq("id", exclude_id)
        )
        if exclude_statuses:
            query = query.not_.in_("status", list(exclude_statuses))
        result = query.execute()
        return int(result.count or 0)

    def delete_by_id(self, job_id: str) -> None:
        """Hard-delete a single job row.

        The FK cascade added in migration 0045 (``posts.glow_up_job_id
        ON DELETE CASCADE``) fans out to ``posts``; pre-existing cascades
        on ``posts.id`` wipe ``reactions``, ``comments``, ``reports``.
        The endpoint must have already enumerated and ideally wiped blobs
        before calling this — see ``enumerate_blob_keys_for_delete`` and
        the ORDER MATTERS comment in ``delete_job``.
        """
        self._sb.table("jobs").delete().eq("id", job_id).execute()

    def delete_analysis_by_id(self, analysis_id: str) -> None:
        """Hard-delete a row from ``glowup_analyses`` by id.

        There is **no** FK cascade from ``jobs.source_id`` to this table
        (the column is a plain UUID; polymorphic ref). The endpoint
        invokes this only when ``count_peer_jobs_for_source`` says no
        other job references the analysis, AND ``source_type`` is
        ``glowup_analysis``. Uploads are NOT touched here — they have
        independent lifecycle owned by ``retention.py``.
        """
        self._sb.table("glowup_analyses").delete().eq("id", analysis_id).execute()
