"""Nightly makeup biometric purge worker — 90-day TTL sweep.

Scheduled cron: daily 04:30 UTC.

Nullifies mst_bin, undertone, region_anchors on makeup_analyses rows older
than 90 days. Consent and ranking metadata are retained. CAS predicate
(mst_bin IS NOT NULL) makes the sweep idempotent — already-nullified rows
are skipped.

Pattern mirrors app/workers/fingerprint_purge.py.
"""

from __future__ import annotations

import logging

from supabase import Client

from app.db.async_helpers import run_sync
from app.repositories.makeup_analysis_repo import MakeupAnalysisRepository

logger = logging.getLogger(__name__)

_BIOMETRIC_TTL_DAYS = 90

MAKEUP_PURGE_CRON_HOUR = 4
MAKEUP_PURGE_CRON_MINUTE = 30


async def run_makeup_purge(ctx: dict) -> None:
    """ARQ cron task: null biometric fields on makeup_analyses rows older than 90 days."""
    supabase: Client = ctx["supabase"]
    repo = MakeupAnalysisRepository(supabase)

    logger.info("makeup_purge: starting — TTL=%d days", _BIOMETRIC_TTL_DAYS)
    try:
        nullified = await run_sync(
            repo.nullify_biometric_fields_older_than, _BIOMETRIC_TTL_DAYS
        )
    except Exception:
        logger.exception("makeup_purge: nullify_biometric_fields_older_than failed")
        raise

    logger.info("makeup_purge: done — nullified=%d rows", nullified)
