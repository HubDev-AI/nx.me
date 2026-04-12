"""Nightly retention worker — purges expired uploads and unsaved jobs.

Retention policy (all periods sourced from config — no magic numbers):
  - Unsaved jobs older than RETENTION_JOB_DAYS: purged individually.
    Leaves the associated upload + glowup_analysis intact (independent lifecycle).
  - Uploads not accessed for RETENTION_UPLOAD_DAYS: purged via CASCADE,
    which drops glowup_analyses and any remaining associated jobs automatically.

Storage cleanup: for each deleted upload, the corresponding image blob is
removed from Supabase storage (raw-selfies bucket). The uploads.image_url
column stores the storage key directly (e.g. "{user_id}/{upload_id}.jpg"),
not a full HTTPS URL — so no URL parsing is needed.

Scheduling: nightly cron at 03:00 UTC (configured in app/worker_settings.py).
"""

from __future__ import annotations

import logging

from supabase import Client

from app.config import settings

logger = logging.getLogger(__name__)


async def run_retention(ctx: dict) -> None:
    """ARQ cron task: enforce upload and job retention policies.

    Steps:
    1. Delete unsaved jobs beyond RETENTION_JOB_DAYS (independent of uploads).
    2. Collect image_url values for uploads past RETENTION_UPLOAD_DAYS.
    3. Delete those uploads (CASCADE removes glowup_analyses + orphaned jobs).
    4. Remove the corresponding storage blobs from the raw-selfies bucket.
    5. Log counts for observability.
    """
    supabase: Client = ctx["supabase"]

    # ------------------------------------------------------------------
    # Step 1: Purge unsaved jobs older than RETENTION_JOB_DAYS
    # ------------------------------------------------------------------

    purged_jobs_result = (
        supabase.table("jobs")
        .delete()
        .is_("saved_at", "null")
        .lt(
            "created_at",
            f"now() - interval '{settings.RETENTION_JOB_DAYS} days'",
        )
        .execute()
    )
    purged_jobs: list[dict] = purged_jobs_result.data or []
    purged_job_count = len(purged_jobs)

    # ------------------------------------------------------------------
    # Step 2: Fetch uploads to purge — collect storage keys first
    # ------------------------------------------------------------------

    expired_uploads_result = (
        supabase.table("uploads")
        .select("id, image_url")
        .lt(
            "last_accessed_at",
            f"now() - interval '{settings.RETENTION_UPLOAD_DAYS} days'",
        )
        .execute()
    )
    expired_uploads: list[dict] = expired_uploads_result.data or []

    if not expired_uploads:
        logger.info(
            "Retention: purged %d jobs, 0 uploads, 0 storage objects",
            purged_job_count,
        )
        return

    upload_ids = [row["id"] for row in expired_uploads]
    storage_keys = [row["image_url"] for row in expired_uploads if row.get("image_url")]

    # ------------------------------------------------------------------
    # Step 3: Delete uploads (CASCADE drops glowup_analyses + orphaned jobs)
    # ------------------------------------------------------------------

    supabase.table("uploads").delete().in_("id", upload_ids).execute()
    purged_upload_count = len(upload_ids)

    # ------------------------------------------------------------------
    # Step 4: Remove blobs from Supabase storage (raw-selfies bucket)
    # ------------------------------------------------------------------

    purged_storage_count = 0
    if storage_keys:
        try:
            supabase.storage.from_("raw-selfies").remove(storage_keys)
            purged_storage_count = len(storage_keys)
        except Exception:
            logger.error(
                "Retention: storage blob cleanup failed for %d keys — orphaned blobs may remain",
                len(storage_keys),
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Step 5: Observability log
    # ------------------------------------------------------------------

    logger.info(
        "Retention: purged %d jobs, %d uploads, %d storage objects",
        purged_job_count,
        purged_upload_count,
        purged_storage_count,
    )
