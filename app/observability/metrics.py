"""Makeup-feature operational metrics.

Emitters are fire-and-forget stubs. Wire to your metrics backend
(Prometheus, Datadog, etc.) by replacing the logger calls with SDK calls.

Metrics defined here (§8 of plan):
  makeup_generate_latency          — histogram, seconds
  makeup_failed_non_retryable_rate — counter
  makeup_fair_use_hit_rate         — counter
  makeup_retention_cohort_tag      — gauge/tag (cohort bucket for retention analysis)
  makeup_paywall_conversion_rate   — counter (paywall-tap → Pro-subscribe within 24h)
"""

from __future__ import annotations

import logging
import time
from typing import Literal

logger = logging.getLogger(__name__)


def emit_makeup_generate_latency(job_id: str, elapsed_seconds: float) -> None:
    """Histogram: end-to-end makeup generation latency (upload → job complete)."""
    logger.info(
        "metric makeup_generate_latency job_id=%s elapsed=%.3f",
        job_id,
        elapsed_seconds,
    )


def emit_makeup_generate_failed_non_retryable(job_id: str, reason: str) -> None:
    """Counter: makeup job reached a non-retryable failure state."""
    logger.info(
        "metric makeup_failed_non_retryable job_id=%s reason=%s",
        job_id,
        reason,
    )


def emit_makeup_fair_use_hit(user_id: str) -> None:
    """Counter: user hit the MAKEUP_FAIR_USE_DAILY_CAP."""
    logger.info("metric makeup_fair_use_hit user_id=%s", user_id)


def emit_makeup_retention_cohort_tag(user_id: str, cohort_pct: int) -> None:
    """Tag: records which rollout cohort the user is in for retention analysis."""
    logger.info(
        "metric makeup_retention_cohort_tag user_id=%s cohort_pct=%d",
        user_id,
        cohort_pct,
    )


def emit_makeup_paywall_conversion(
    user_id: str,
    action: Literal["tap", "subscribe"],
) -> None:
    """Counter: paywall funnel events.

    Tap → subscribe within 24h confirms the illustrated-teaser hypothesis.
    Compared against glowup paywall baseline to measure incremental lift.
    """
    logger.info(
        "metric makeup_paywall_conversion user_id=%s action=%s ts=%.3f",
        user_id,
        action,
        time.time(),
    )
