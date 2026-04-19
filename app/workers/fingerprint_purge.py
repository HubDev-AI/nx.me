"""Nightly fingerprint purge worker — TTL sweep for ``signup_grants_issued``.

Scheduled cron: daily 03:15 UTC (unused slot per orphan-DLQ-symmetry guidance).

Deletes rows from ``signup_grants_issued`` older than 12 months.  Keeping the
table bounded prevents unbounded growth while preserving enough history to
detect abuse within any reasonable re-registration window (a user who deletes
and re-registers within 12 months is still caught by the fingerprint check).

Pattern mirrors ``app/workers/retention.py``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from supabase import Client

from app.repositories.signup_grant_repo import SignupGrantRepository

logger = logging.getLogger(__name__)

# Retention window for signup fingerprint rows (12 months ≈ 365 days).
# ``timedelta`` cannot express calendar months directly; 365 days is a
# conservative approximation that keeps the math in stdlib (no dateutil dep).
_FINGERPRINT_TTL_DAYS = 365

# Cron schedule constants (registered in app/worker_settings.py).
# Daily 03:15 UTC — unused slot per orphan-DLQ-symmetry guidance.
FINGERPRINT_PURGE_CRON_HOUR = 3
FINGERPRINT_PURGE_CRON_MINUTE = 15


async def run_fingerprint_purge(ctx: dict) -> None:
    """ARQ cron task: delete ``signup_grants_issued`` rows older than 12 months.

    Uses ``SignupGrantRepository.purge_older_than`` with a cutoff of
    ``now() - 12 months`` so the table stays bounded without removing rows
    that could still be hit by a re-registration attempt within the TTL window.
    """
    supabase: Client = ctx["supabase"]

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=_FINGERPRINT_TTL_DAYS)

    logger.info(
        "fingerprint_purge: starting — deleting signup_grants_issued rows older than %s",
        cutoff.isoformat(),
    )

    try:
        repo = SignupGrantRepository(supabase)
        deleted = repo.purge_older_than(cutoff)
    except Exception:
        logger.exception("fingerprint_purge: purge_older_than failed")
        raise

    logger.info("fingerprint_purge: done — deleted=%d rows", deleted)
