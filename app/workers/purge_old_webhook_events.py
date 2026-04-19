"""Nightly worker — purge ``processed_webhook_events`` rows older than 30 days.

Scheduled cron: daily 03:45 UTC.

Stripe webhook idempotency keys are kept in ``processed_webhook_events`` to
deduplicate replays. Rows older than ``_WEBHOOK_EVENT_RETENTION_DAYS`` are no
longer useful for deduplication and constitute unnecessary PII retention.

Pattern mirrors ``app/workers/fingerprint_purge.py``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from supabase import Client

logger = logging.getLogger(__name__)

# Retention window — events older than this are safe to purge.
_WEBHOOK_EVENT_RETENTION_DAYS = 30

# Cron schedule constants (registered in app/worker_settings.py).
# Daily 03:45 UTC.
WEBHOOK_EVENT_PURGE_CRON_HOUR = 3
WEBHOOK_EVENT_PURGE_CRON_MINUTE = 45


async def purge_old_webhook_events(ctx: dict) -> None:
    """ARQ cron task: delete ``processed_webhook_events`` rows older than 30 days.

    Uses a single DELETE with a timestamp cutoff so the query is index-driven
    (``inserted_at`` index from migration 0001). Returns cleanly on any error
    so a transient DB issue does not crash the worker.
    """
    supabase: Client = ctx["supabase"]

    cutoff = datetime.now(tz=timezone.utc) - timedelta(
        days=_WEBHOOK_EVENT_RETENTION_DAYS
    )

    logger.info(
        "purge_old_webhook_events: starting — deleting processed_webhook_events older than %s",
        cutoff.isoformat(),
    )

    try:
        result = (
            supabase.table("processed_webhook_events")
            .delete()
            .lt("inserted_at", cutoff.isoformat())
            .execute()
        )
        deleted = len(result.data) if result.data else 0
    except Exception:
        logger.exception("purge_old_webhook_events: DELETE failed")
        return

    logger.info("purge_old_webhook_events: done — deleted=%d rows", deleted)
