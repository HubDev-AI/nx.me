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

Scheduling: nightly cron at 03:30 UTC (configured in app/worker_settings.py).
Runs 30 minutes after ``reconcile_reaction_counts`` at 03:00 UTC. If
reconcile is still running when retention fires, retention skips this tick —
it checks the shared ``RECONCILE_LOCK_KEY`` mutex before doing any work.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from supabase import Client

from app.api.social import RECONCILE_LOCK_KEY
from app.config import settings

logger = logging.getLogger(__name__)


async def purge_expired_username_reservations(supabase: Client) -> int:
    """Delete username_reservations rows whose window has elapsed.

    Availability logic already ignores expired rows, so this is pure
    table-hygiene that bounds table growth over years. Returns the
    number of rows deleted.
    """
    result = (
        supabase.table("username_reservations")
        .delete()
        .lt("reserved_until", datetime.now(tz=timezone.utc).isoformat())
        .execute()
    )
    return len(result.data or [])


async def reconcile_orphaned_users(supabase: Client) -> int:
    """Delete public.users rows whose Supabase auth.users identity is gone.

    Covers the partial-failure window in delete_account where step 3
    (auth.admin.delete_user) succeeds but step 5 (DELETE FROM users)
    raises. The orphan row has no working auth identity and cannot be
    recovered by the user — a re-login returns 401 because the auth
    row is already deleted. Without this sweeper the orphan survives
    forever.

    Runs a single RPC (an auth.users LEFT JOIN) to find every
    public.users row without a matching auth.users row, then hard-
    deletes those rows (triggering the same CASCADE chain the original
    delete would have). Returns the count.

    Safe because:
    - Supabase's auth.users row always exists for any legitimate login —
      we only create public.users after successful auth provisioning, so
      a missing auth row is unambiguously an orphan.
    - Runs in the same cron after retention cleanup; deletes cascade
      through the FKs rewritten by migrations 0044 + 0045.
    """
    # PostgREST can't express a LEFT JOIN across schemas (public.users
    # → auth.users), so we do it in two steps: list all public.users
    # ids, then subtract the set of live auth ids.
    users_result = supabase.table("users").select("id").execute()
    public_ids = {row["id"] for row in (users_result.data or [])}
    if not public_ids:
        return 0

    # auth.users is not exposed via PostgREST — use the admin list
    # endpoint. For small pre-launch scale this one-shot fetch is
    # adequate. If user counts grow into the tens of thousands, switch
    # to a server-side RPC that does the EXISTS check in a single query.
    auth_ids: set[str] = set()
    page = 1
    per_page = 1000
    while True:
        resp = supabase.auth.admin.list_users(page=page, per_page=per_page)
        rows = resp.users if hasattr(resp, "users") else resp or []
        if not rows:
            break
        for u in rows:
            auth_ids.add(str(u.id))
        if len(rows) < per_page:
            break
        page += 1

    orphans = public_ids - auth_ids
    if not orphans:
        return 0

    # Hard-delete each orphan. Cascade chain (post-0044/0045) drops
    # every owned row. Username reservations were already inserted by
    # the original delete_account call, so we don't re-insert here —
    # the reservation protects the orphan's former handle already.
    supabase.table("users").delete().in_("id", list(orphans)).execute()
    logger.warning(
        "reconcile_orphaned_users: hard-deleted %d public.users rows with no auth identity",
        len(orphans),
    )
    return len(orphans)


async def run_retention(ctx: dict) -> None:
    """ARQ cron task: enforce upload and job retention policies.

    Steps:
    1. Honour the reconcile-cron mutex — skip entirely if reconcile is
       still running (prevents racing on tables reconcile touches).
    2. Delete unsaved jobs beyond RETENTION_JOB_DAYS (independent of uploads).
    3. Collect image_url values for uploads past RETENTION_UPLOAD_DAYS.
    4. Delete those uploads (CASCADE removes glowup_analyses + orphaned jobs).
    5. Remove the corresponding storage blobs from the raw-selfies bucket.
    6. Log counts for observability.
    """
    redis_client = ctx.get("redis")

    if redis_client is not None:
        if await redis_client.get(RECONCILE_LOCK_KEY) is not None:
            logger.warning(
                "retention skipped: reconcile lock %s held", RECONCILE_LOCK_KEY
            )
            return

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

    purged_upload_count = 0
    purged_storage_count = 0

    if expired_uploads:
        upload_ids = [row["id"] for row in expired_uploads]
        storage_keys = [
            row["image_url"] for row in expired_uploads if row.get("image_url")
        ]

        # --------------------------------------------------------------
        # Step 3: Delete uploads (CASCADE drops glowup_analyses + orphans)
        # --------------------------------------------------------------

        supabase.table("uploads").delete().in_("id", upload_ids).execute()
        purged_upload_count = len(upload_ids)

        # --------------------------------------------------------------
        # Step 4: Remove blobs from Supabase storage (raw-selfies bucket)
        # --------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Step 6: Purge expired username_reservations (table hygiene)
    # ------------------------------------------------------------------

    try:
        purged_reservations = await purge_expired_username_reservations(supabase)
        logger.info(
            "Retention: purged %d expired username reservations",
            purged_reservations,
        )
    except Exception:
        logger.exception("username_reservations cleanup failed")

    # ------------------------------------------------------------------
    # Step 7: Reconcile orphaned public.users rows (auth identity gone
    # but DB row survived — the delete_account partial-failure case).
    # ------------------------------------------------------------------

    try:
        reconciled = await reconcile_orphaned_users(supabase)
        if reconciled:
            logger.warning(
                "Retention: reconciled %d orphaned users (auth identity missing)",
                reconciled,
            )
    except Exception:
        logger.exception("orphaned-users reconciliation failed")
