"""Nudge scheduler — ARQ jobs for advisor-initiated nudges.

Spec Section 7: Ada-initiated messages, all tiers (capped). In-app feed only.

Jobs:
  generate_nudge            — generate + save a single nudge via Haiku
  schedule_post_analysis_nudge — lightweight wrapper called from analyses endpoint
  check_nudge_eligibility   — daily cron: scans all active users, enqueues eligible nudges

Trigger types (spec Section 7.1):
  post_analysis   — after face analysis completes
  weekly_checkin  — 7 days since last nudge, if goals exist
  milestone       — 5th or 10th analysis
  re_engagement   — 14 days since last activity
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

import redis.asyncio as aioredis
from arq import ArqRedis
from supabase import Client

from app.config import settings

logger = logging.getLogger(__name__)

# Model used for nudge generation (spec Section 10)
_MODEL_HAIKU = "claude-3-haiku-20240307"

# Max tokens per nudge — keep short and warm (spec Section 11 brevity principle)
_MAX_TOKENS_NUDGE = 128

# Trigger string constants — spec Section 7.1
TRIGGER_POST_ANALYSIS = "post_analysis"
TRIGGER_WEEKLY_CHECKIN = "weekly_checkin"
TRIGGER_MILESTONE = "milestone"
TRIGGER_RE_ENGAGEMENT = "re_engagement"

# Milestone analysis counts that trigger a nudge (spec Section 7.1)
_MILESTONE_COUNTS = {5, 10}

# Eligibility windows (spec Section 7.1)
_WEEKLY_CHECKIN_DAYS = 7
_RE_ENGAGEMENT_DAYS = 14


# ---------------------------------------------------------------------------
# Prompt templates — inline for MVP (spec Section 7.3)
# ---------------------------------------------------------------------------

_NUDGE_PROMPTS: dict[str, str] = {
    TRIGGER_POST_ANALYSIS: (
        "The user just completed a face analysis. "
        "Give a single warm, encouraging tip based on their latest result. "
        "One sentence. No greetings. No sign-offs."
    ),
    TRIGGER_WEEKLY_CHECKIN: (
        "It has been a week since the user's last nudge. "
        "They have active style goals. "
        "Check in with a brief, motivating observation. "
        "One sentence. No greetings. No sign-offs."
    ),
    TRIGGER_MILESTONE: (
        "The user has just reached an analysis milestone. "
        "Celebrate their consistency with one warm sentence. "
        "No greetings. No sign-offs."
    ),
    TRIGGER_RE_ENGAGEMENT: (
        "The user has been away for two weeks. "
        "Gently invite them back with something fresh to try. "
        "One sentence. No greetings. No sign-offs."
    ),
}


# ---------------------------------------------------------------------------
# LLM adapter factory (mirrors generation worker pattern)
# ---------------------------------------------------------------------------


def _get_llm_adapter():
    """Resolve LLM adapter from config (lazy import)."""
    if settings.ADAPTER__LLM_ADAPTER == "anthropic":
        from app.advisor.adapters.anthropic_adapter import AnthropicAdapter
        return AnthropicAdapter()
    from app.advisor.adapters.mock import MockLLMAdapter
    return MockLLMAdapter()


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
    prompt = _NUDGE_PROMPTS.get(trigger, _NUDGE_PROMPTS[TRIGGER_POST_ANALYSIS])

    # Generate via Haiku
    llm = _get_llm_adapter()
    try:
        response = await llm.create_message(
            model=_MODEL_HAIKU,
            system=(
                f"You are {settings.ADVISOR_PERSONA_NAME}, a warm personal style advisor. "
                "Keep responses brief and human. Never use generic phrases."
            ),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=_MAX_TOKENS_NUDGE,
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
        supabase.table("advisor_nudges").insert({
            "user_id": user_id,
            "trigger": trigger,
            "content": nudge_content,
        }).execute()
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
# ARQ cron job: check_nudge_eligibility
# ---------------------------------------------------------------------------


async def check_nudge_eligibility(ctx: dict) -> None:
    """Daily cron: scan active users and enqueue nudge jobs for eligible ones.

    Eligibility rules (spec Section 7.1):
      weekly_checkin  — last nudge > WEEKLY_CHECKIN_DAYS ago, user has goals
      milestone       — completed analysis count is exactly in MILESTONE_COUNTS
      re_engagement   — last activity > RE_ENGAGEMENT_DAYS ago

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

    now_utc = datetime.now(tz=timezone.utc)
    weekly_cutoff = (now_utc - timedelta(days=_WEEKLY_CHECKIN_DAYS)).isoformat()
    re_engagement_cutoff = (now_utc - timedelta(days=_RE_ENGAGEMENT_DAYS)).isoformat()

    enqueued = 0

    # ------------------------------------------------------------------
    # 1. Weekly check-in: users with goals, last nudge > 7 days ago
    # ------------------------------------------------------------------
    try:
        # Fetch users who have at least one 'goal' memory
        goal_users_result = (
            supabase.table("user_memories")
            .select("user_id")
            .eq("type", "goal")
            .execute()
        )
        user_ids_with_goals = {
            row["user_id"] for row in (goal_users_result.data or [])
        }

        for uid_str in user_ids_with_goals:
            # Find most recent nudge for this user
            last_nudge_result = (
                supabase.table("advisor_nudges")
                .select("created_at")
                .eq("user_id", uid_str)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            last_nudge_rows = last_nudge_result.data or []

            if not last_nudge_rows:
                # Never had a nudge — eligible
                eligible = True
            else:
                last_nudge_at = last_nudge_rows[0]["created_at"]
                eligible = last_nudge_at < weekly_cutoff

            if eligible:
                if arq_pool is not None:
                    await arq_pool.enqueue_job("generate_nudge", uid_str, TRIGGER_WEEKLY_CHECKIN)
                else:
                    await generate_nudge(ctx, uid_str, TRIGGER_WEEKLY_CHECKIN)
                enqueued += 1

    except Exception as exc:
        logger.error("Weekly check-in eligibility scan failed: %s", exc)

    # ------------------------------------------------------------------
    # 2. Milestone: users with exactly 5 or 10 completed analyses
    # ------------------------------------------------------------------
    try:
        for milestone_count in _MILESTONE_COUNTS:
            # Fetch users whose analysis insight count equals the milestone
            # We use a count query per user — approach: fetch all analysis
            # insights grouped by user_id and filter by count.
            # Supabase does not support GROUP BY with aggregate filters directly
            # in the SDK, so we fetch users who have exactly `milestone_count`
            # analysis insights by counting per user.
            all_insights_result = (
                supabase.table("user_memories")
                .select("user_id")
                .eq("type", "analysis_insight")
                .execute()
            )
            insight_rows = all_insights_result.data or []

            # Count per user
            count_per_user: dict[str, int] = {}
            for row in insight_rows:
                uid_str = row["user_id"]
                count_per_user[uid_str] = count_per_user.get(uid_str, 0) + 1

            milestone_users = [
                uid_str
                for uid_str, cnt in count_per_user.items()
                if cnt == milestone_count
            ]

            for uid_str in milestone_users:
                # Avoid duplicate milestone nudges: check if a milestone nudge
                # was already sent when count was at this level.
                # Heuristic: if a milestone nudge exists from the last 48 hours,
                # skip (the milestone was already celebrated).
                recent_milestone_cutoff = (
                    now_utc - timedelta(hours=settings.ADVISOR_MILESTONE_DEDUP_HOURS)
                ).isoformat()
                existing = (
                    supabase.table("advisor_nudges")
                    .select("id")
                    .eq("user_id", uid_str)
                    .eq("trigger", TRIGGER_MILESTONE)
                    .gt("created_at", recent_milestone_cutoff)
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    continue

                if arq_pool is not None:
                    await arq_pool.enqueue_job("generate_nudge", uid_str, TRIGGER_MILESTONE)
                else:
                    await generate_nudge(ctx, uid_str, TRIGGER_MILESTONE)
                enqueued += 1

    except Exception as exc:
        logger.error("Milestone eligibility scan failed: %s", exc)

    # ------------------------------------------------------------------
    # 3. Re-engagement: users with last activity > 14 days ago
    # ------------------------------------------------------------------
    try:
        # "Last activity" = most recent analysis insight (proxy for app usage).
        # Fetch users whose most recent analysis insight is older than the cutoff.
        all_insight_dates_result = (
            supabase.table("user_memories")
            .select("user_id, created_at")
            .eq("type", "analysis_insight")
            .execute()
        )
        insight_date_rows = all_insight_dates_result.data or []

        # Latest insight per user
        latest_activity: dict[str, str] = {}
        for row in insight_date_rows:
            uid_str = row["user_id"]
            row_ts = row["created_at"]
            if uid_str not in latest_activity or row_ts > latest_activity[uid_str]:
                latest_activity[uid_str] = row_ts

        inactive_users = [
            uid_str
            for uid_str, last_ts in latest_activity.items()
            if last_ts < re_engagement_cutoff
        ]

        for uid_str in inactive_users:
            # Avoid spamming: skip if a re-engagement nudge was sent in the
            # last RE_ENGAGEMENT_DAYS to prevent back-to-back nudges.
            last_re_engagement_cutoff = (
                now_utc - timedelta(days=_RE_ENGAGEMENT_DAYS)
            ).isoformat()
            existing = (
                supabase.table("advisor_nudges")
                .select("id")
                .eq("user_id", uid_str)
                .eq("trigger", TRIGGER_RE_ENGAGEMENT)
                .gt("created_at", last_re_engagement_cutoff)
                .limit(1)
                .execute()
            )
            if existing.data:
                continue

            if arq_pool is not None:
                await arq_pool.enqueue_job("generate_nudge", uid_str, TRIGGER_RE_ENGAGEMENT)
            else:
                await generate_nudge(ctx, uid_str, TRIGGER_RE_ENGAGEMENT)
            enqueued += 1

    except Exception as exc:
        logger.error("Re-engagement eligibility scan failed: %s", exc)

    logger.info("Nudge eligibility check complete: enqueued=%d", enqueued)
