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
from app.advisor.persona import SOUL_MD
from app.repositories.advisor_repo import AdvisorRepository
from app.advisor.nudge_policy import (
    MAX_TOKENS_NUDGE,
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

    # Generate via Haiku — same SOUL.md persona as chat (spec §1, §12).
    llm = _get_llm_adapter()
    try:
        response = await llm.create_message(
            model=settings.ADVISOR_MODEL_HAIKU,
            system=SOUL_MD,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Write a brief check-in nudge in your voice. "
                        "One or two sentences, no greeting.\n\n" + prompt
                    ),
                }
            ],
            max_tokens=MAX_TOKENS_NUDGE,
        )
        nudge_content = response.content.strip()
    except Exception as exc:
        logger.error(
            "LLM call failed for nudge (user=%s, trigger=%s): %s", user_id, trigger, exc
        )
        return

    if not nudge_content:
        logger.warning(
            "Empty nudge content from LLM — skipping (user=%s, trigger=%s)",
            user_id,
            trigger,
        )
        return

    # Persist to advisor_nudges
    try:
        advisor_repo.insert_nudge(
            {
                "user_id": user_id,
                "trigger": trigger,
                "content": nudge_content,
            }
        )
    except Exception as exc:
        logger.error("Failed to save nudge for user %s: %s", user_id, exc)
        return

    logger.info("Nudge saved: user=%s trigger=%s", user_id, trigger)


# ---------------------------------------------------------------------------
# Memory manager builder (also used by write_analysis_insight_job)
# ---------------------------------------------------------------------------


async def _build_memory_manager(ctx: dict):
    """Construct a MemoryManager from worker context resources.

    Extracted so tests can patch this without standing up real Supabase/Redis.
    """
    from app.advisor.memory_manager import MemoryManager
    from app.api.deps import get_embedding_adapter, get_llm_adapter

    supabase: Client = ctx["supabase"]
    return MemoryManager(
        advisor_repo=AdvisorRepository(supabase),
        llm_adapter=get_llm_adapter(),
        embedding_adapter=get_embedding_adapter(),
    )


# ---------------------------------------------------------------------------
# ARQ job: write_analysis_insight_job
# ---------------------------------------------------------------------------


async def write_analysis_insight_job(
    ctx: dict,
    user_id: str,
    face_shape: str,
    symmetry_score: float,
    recommendations: list[str],
    upload_id: str,
) -> None:
    """Persist an `analysis_insight` memory row after a face analysis completes.

    Fire-and-forget: any failure is logged and swallowed so a missing memory
    never turns a successful analysis into a 5xx (spec §4.5, §16).
    """
    if not settings.ADVISOR_ENABLED:
        return

    try:
        mm = await _build_memory_manager(ctx)
        await mm.write_analysis_insight(
            user_id=UUID(user_id),
            face_shape=face_shape,
            symmetry_score=symmetry_score,
            recommendations=recommendations,
            upload_id=upload_id,
        )
        logger.info("Analysis insight written for user %s", user_id)
    except Exception:
        logger.warning(
            "Failed to write analysis insight for user %s",
            user_id,
            exc_info=True,
            extra={"metric": "advisor.analysis_insight_failure", "user_id": user_id},
        )


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
        logger.debug(
            "No arq_pool in ctx — running generate_nudge inline for user %s", user_id
        )
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
