"""Nudge scheduler — thin orchestrator for advisor-initiated nudges.

Wires together policy, templates, eligibility scans, and queue dispatch.
The public interface (ARQ job names) is unchanged:

Jobs:
  generate_nudge            — generate + save a single nudge via Haiku
  schedule_post_analysis_nudge — lightweight wrapper called from analyses endpoint
  check_nudge_eligibility   — daily cron: scans all active users, enqueues eligible nudges

See nudge_policy.py, nudge_templates.py, nudge_eligibility.py for the
extracted concerns.
"""
from __future__ import annotations

import logging
from uuid import UUID

import redis.asyncio as aioredis
from arq import ArqRedis
from supabase import Client

from app.advisor.nudge_eligibility import (
    find_milestone_eligible,
    find_re_engagement_eligible,
    find_weekly_checkin_eligible,
)
from app.repositories.advisor_repo import AdvisorRepository
from app.advisor.nudge_policy import (
    MAX_TOKENS_NUDGE,
    MODEL_HAIKU,
    TRIGGER_MILESTONE,
    TRIGGER_POST_ANALYSIS,
    TRIGGER_RE_ENGAGEMENT,
    TRIGGER_WEEKLY_CHECKIN,
)
from app.advisor.nudge_templates import get_prompt
from app.api.deps import get_llm_adapter as _get_llm_adapter
from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ARQ job: generate_nudge
# ---------------------------------------------------------------------------


async def generate_nudge(ctx: dict, user_id: str, trigger: str) -> None:
    """Generate and save a single nudge for a user.

    Entitlement is checked before generation. Skips silently if the user has
    hit their nudge cap for the current period (spec Section 3).

    Args:
        ctx:     ARQ worker context (supabase, redis injected at startup).
        user_id: UUID string of the target user.
        trigger: One of the TRIGGER_* constants.
    """
    if not settings.ADVISOR_ENABLED:
        logger.debug("Advisor disabled — skipping nudge for user %s", user_id)
        return

    supabase: Client = ctx["supabase"]
    redis: aioredis.Redis = ctx["redis"]
    uid = UUID(user_id)
    advisor_repo = AdvisorRepository(supabase)

    # Entitlement check (spec Section 7.3, A-5)
    from app.entitlement.service import EntitlementService
    ent_svc = EntitlementService(supabase=supabase, redis_client=redis)
    try:
        result = await ent_svc.check(uid, "advisor_nudge")
    except Exception as exc:
        logger.warning("Entitlement check failed for user %s: %s", user_id, exc)
        return

    if not result.allowed:
        logger.info(
            "Nudge skipped — entitlement denied for user %s (trigger=%s, code=%s)",
            user_id,
            trigger,
            result.error_code,
        )
        return

    # Build nudge prompt
    prompt = get_prompt(trigger)

    # Generate via Haiku
    llm = _get_llm_adapter()
    try:
        response = await llm.create_message(
            model=MODEL_HAIKU,
            system=(
                f"You are {settings.ADVISOR_PERSONA_NAME}, a warm personal style advisor. "
                "Keep responses brief and human. Never use generic phrases."
            ),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=MAX_TOKENS_NUDGE,
        )
        nudge_content = response.content.strip()
    except Exception as exc:
        logger.error("LLM call failed for nudge (user=%s, trigger=%s): %s", user_id, trigger, exc)
        return

    if not nudge_content:
        logger.warning("Empty nudge content from LLM — skipping (user=%s, trigger=%s)", user_id, trigger)
        return

    # Persist to advisor_nudges
    try:
        advisor_repo.insert_nudge({
            "user_id": user_id,
            "trigger": trigger,
            "content": nudge_content,
        })
    except Exception as exc:
        logger.error("Failed to save nudge for user %s: %s", user_id, exc)
        return

    logger.info("Nudge saved: user=%s trigger=%s", user_id, trigger)


# ---------------------------------------------------------------------------
# ARQ job: schedule_post_analysis_nudge
# ---------------------------------------------------------------------------


async def schedule_post_analysis_nudge(ctx: dict, user_id: str) -> None:
    """Enqueue a post-analysis nudge for a user.

    Called from the analysis endpoint after a successful analysis (spec Section
    16: one integration point guarded by ADVISOR_ENABLED).

    This is a thin wrapper that immediately enqueues ``generate_nudge`` so the
    analysis endpoint does not block on LLM latency.

    Args:
        ctx:     ARQ worker context.
        user_id: UUID string of the user who completed the analysis.
    """
    if not settings.ADVISOR_ENABLED:
        return

    arq_pool: ArqRedis = ctx.get("arq_pool")
    if arq_pool is None:
        # Fallback: run inline if no pool is available in context (e.g. tests)
        logger.debug("No arq_pool in ctx — running generate_nudge inline for user %s", user_id)
        await generate_nudge(ctx, user_id, TRIGGER_POST_ANALYSIS)
        return

    await arq_pool.enqueue_job("generate_nudge", user_id, TRIGGER_POST_ANALYSIS)
    logger.debug("Enqueued post-analysis nudge for user %s", user_id)


# ---------------------------------------------------------------------------
# Queue dispatch helper
# ---------------------------------------------------------------------------


async def _dispatch(
    ctx: dict,
    arq_pool: ArqRedis | None,
    user_id: str,
    trigger: str,
) -> None:
    """Dispatch a nudge job via ARQ pool or run inline as fallback."""
    if arq_pool is not None:
        await arq_pool.enqueue_job("generate_nudge", user_id, trigger)
    else:
        await generate_nudge(ctx, user_id, trigger)


# ---------------------------------------------------------------------------
# ARQ cron job: check_nudge_eligibility
# ---------------------------------------------------------------------------


async def check_nudge_eligibility(ctx: dict) -> None:
    """Daily cron: scan active users and enqueue nudge jobs for eligible ones.

    Delegates eligibility queries to nudge_eligibility module, then dispatches
    generate_nudge jobs for each eligible user.

    Post-analysis nudges are triggered directly from the analysis endpoint,
    not from this cron job.

    Args:
        ctx: ARQ worker context (supabase, redis, arq_pool).
    """
    if not settings.ADVISOR_ENABLED:
        logger.debug("Advisor disabled — skipping nudge eligibility check")
        return

    supabase: Client = ctx["supabase"]
    arq_pool: ArqRedis | None = ctx.get("arq_pool")
    advisor_repo = AdvisorRepository(supabase)

    enqueued = 0

    # 1. Weekly check-in
    try:
        weekly_users = await find_weekly_checkin_eligible(advisor_repo)
        for uid_str in weekly_users:
            await _dispatch(ctx, arq_pool, uid_str, TRIGGER_WEEKLY_CHECKIN)
            enqueued += 1
    except Exception as exc:
        logger.error("Weekly check-in eligibility scan failed: %s", exc)

    # 2. Milestone
    try:
        milestone_users = await find_milestone_eligible(advisor_repo)
        for uid_str in milestone_users:
            await _dispatch(ctx, arq_pool, uid_str, TRIGGER_MILESTONE)
            enqueued += 1
    except Exception as exc:
        logger.error("Milestone eligibility scan failed: %s", exc)

    # 3. Re-engagement
    try:
        re_engagement_users = await find_re_engagement_eligible(advisor_repo)
        for uid_str in re_engagement_users:
            await _dispatch(ctx, arq_pool, uid_str, TRIGGER_RE_ENGAGEMENT)
            enqueued += 1
    except Exception as exc:
        logger.error("Re-engagement eligibility scan failed: %s", exc)

    logger.info("Nudge eligibility check complete: enqueued=%d", enqueued)
