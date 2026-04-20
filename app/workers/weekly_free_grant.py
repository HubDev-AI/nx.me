"""Weekly free-credit grant worker — delivers milli-credits to Free users.

Scheduled cron: Monday 02:30 UTC (unused slot per orphan-DLQ-symmetry guidance).

Each Monday the worker iterates every non-Pro user and calls
``credit_apply_weekly_free_grant`` with the current ISO-week string.  The RPC
is idempotent via a partial UNIQUE index on ``reference_id WHERE
type='weekly_free_grant'`` — running the worker twice in the same week for
the same user is a silent no-op (ON CONFLICT DO NOTHING).

Users with an *active* subscription are skipped: they receive their monthly
allotment via the credits-only billing path and must not also receive the
free weekly grant (would double-credit paid users).

Pattern mirrors ``app/workers/retention.py::run_retention``.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from supabase import Client

from app.config import settings

logger = logging.getLogger(__name__)

# ISO-week page size — keeps each Supabase query bounded.
_PAGE_SIZE = 500

# Cron schedule constant (registered in app/worker_settings.py).
# Monday 02:30 UTC — unused slot per orphan-DLQ-symmetry guidance.
WEEKLY_FREE_GRANT_CRON_HOUR = 2
WEEKLY_FREE_GRANT_CRON_MINUTE = 30
WEEKLY_FREE_GRANT_CRON_WEEKDAY = "mon"


def _current_iso_week() -> str:
    """Return the current ISO-8601 week string, e.g. ``'2026-W16'``."""
    return datetime.now(tz=timezone.utc).strftime("%G-W%V")


def _run_grant_sync(supabase: Client, iso_week: str, weekly_grant_milli: int) -> None:
    """Sync implementation of the grant loop — runs in a thread pool via
    ``asyncio.to_thread`` so the event loop is never blocked by supabase-py's
    synchronous HTTP calls.

    Error handling:
    - Subscription fetch failure -> re-raise so ARQ retries the whole job.
    - Page fetch failure -> re-raise so ARQ retries the whole job.
    - Per-user RPC failure -> log + continue (one bad user must not abort the
      entire week's grant run).

    TODO(perf-001): batch via set-returning RPC at scale to eliminate the
    N+1 pattern (one RPC per user). Acceptable at pre-launch volume.
    """
    # Fetch user IDs with active subscriptions so we can skip them.
    # The subscriptions table is small pre-launch; one-shot fetch is adequate.
    # Paired with a count probe: if .data comes back empty but `count` > 0
    # (PostgREST returned 200+empty-data under connection reset or stale
    # replica), abort rather than silently granting every Pro user.
    try:
        sub_result = (
            supabase.table("subscriptions")
            .select("user_id", count="exact")
            .eq("status", "active")
            .execute()
        )
        pro_user_ids: set[str] = {row["user_id"] for row in (sub_result.data or [])}
        # Sanity check: PostgREST can return 200 + empty data under replica
        # staleness or connection reset after headers. If `count` reports any
        # active subscriptions but `data` came back empty, abort instead of
        # silently granting every Pro user a free weekly credit.
        expected_count_raw = getattr(sub_result, "count", None)
        expected_count = expected_count_raw if isinstance(expected_count_raw, int) else 0
        if expected_count > 0 and not pro_user_ids:
            logger.error(
                "weekly_free_grant: subscriptions count=%d but data empty — aborting",
                expected_count,
            )
            raise RuntimeError(
                "pro_user_ids sanity check failed — active subscriptions present but"
                " empty data payload from Supabase"
            )
    except Exception:
        logger.exception(
            "weekly_free_grant: failed to fetch active subscriptions -- aborting"
        )
        raise

    granted = 0
    skipped_pro = 0
    errors = 0
    offset = 0

    while True:
        try:
            page_result = (
                supabase.table("users")
                .select("id")
                .eq("is_banned", False)
                .range(offset, offset + _PAGE_SIZE - 1)
                .execute()
            )
        except Exception:
            logger.exception(
                "weekly_free_grant: failed to fetch users page at offset=%d -- aborting",
                offset,
            )
            raise

        rows = page_result.data or []
        if not rows:
            break

        for row in rows:
            user_id: str = row["id"]

            if user_id in pro_user_ids:
                skipped_pro += 1
                continue

            try:
                supabase.rpc(
                    "credit_apply_weekly_free_grant",
                    {
                        "p_user_id": user_id,
                        "p_iso_week": iso_week,
                        "p_weekly_grant_milli": weekly_grant_milli,
                    },
                ).execute()
                granted += 1
            except Exception:
                logger.exception(
                    "weekly_free_grant: RPC failed for user=%s iso_week=%s",
                    user_id,
                    iso_week,
                )
                errors += 1

        if len(rows) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    logger.info(
        "weekly_free_grant: done iso_week=%s granted=%d skipped_pro=%d errors=%d",
        iso_week,
        granted,
        skipped_pro,
        errors,
    )


async def run_weekly_free_grant(ctx: dict) -> None:
    """ARQ cron task: grant weekly free credits to eligible Free users.

    Offloads the sync supabase-py calls to a thread pool via
    ``asyncio.to_thread`` so the ARQ event loop is not blocked.
    """
    supabase: Client = ctx["supabase"]
    iso_week = _current_iso_week()
    weekly_grant_milli = settings.WEEKLY_FREE_GRANT_MILLI

    logger.info(
        "weekly_free_grant: starting for iso_week=%s grant_milli=%d",
        iso_week,
        weekly_grant_milli,
    )

    await asyncio.to_thread(_run_grant_sync, supabase, iso_week, weekly_grant_milli)
