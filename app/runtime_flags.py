"""Runtime kill-switches backed by the ``app_kill_switches`` table.

Hot-toggle for background jobs (cron workers) so operators can pause a job
via SQL without a redeploy. Unlike feature flags in ``app/features/`` — which
are env-driven, deployment-wide, and gate UI/routers — kill-switches gate
individual jobs and can be flipped live.

Design:
- Single generic table; one row per job keyed by ``key``.
- Missing row ⇒ treat as ENABLED (fail-open). A forgotten seed must not
  silently disable a production job; the absence of an explicit "off" signal
  means "on".
- Read fresh at every fire-time — no caching — so operator flips take effect
  on the next cron tick.
- Read errors ⇒ ENABLED (fail-open). A transient DB blip must not skip a
  grant; ARQ retry on downstream failure is the right recovery path.
"""

from __future__ import annotations

import asyncio
import logging

from supabase import Client

logger = logging.getLogger(__name__)

# Kill-switch keys — keep in sync with the seed rows in
# ``app/migrations/0057_app_kill_switches.sql``.
KILL_SWITCH_WEEKLY_FREE_GRANT = "weekly_free_grant"


def _is_enabled_sync(supabase: Client, key: str) -> bool:
    """Sync lookup — runs in a thread pool from the async wrapper."""
    try:
        result = (
            supabase.table("app_kill_switches")
            .select("enabled")
            .eq("key", key)
            .limit(1)
            .execute()
        )
    except Exception:
        logger.exception(
            "kill_switch: lookup failed for key=%s — fail-open (treating as enabled)",
            key,
        )
        return True

    rows = result.data or []
    if not rows:
        logger.warning(
            "kill_switch: no row for key=%s — fail-open (treating as enabled)",
            key,
        )
        return True

    return bool(rows[0]["enabled"])


async def is_kill_switch_enabled(supabase: Client, key: str) -> bool:
    """Return True when the job identified by ``key`` is allowed to run.

    ``supabase`` is the sync client from the ARQ worker context. The actual
    HTTP call is offloaded to a thread so the event loop is not blocked.
    """
    return await asyncio.to_thread(_is_enabled_sync, supabase, key)
