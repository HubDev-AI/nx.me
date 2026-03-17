"""Nudge eligibility scans — database queries to find users eligible for nudges.

Each function returns a list of user-ID strings eligible for that trigger type.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from supabase import Client

from app.advisor.nudge_policy import (
    MILESTONE_COUNTS,
    RE_ENGAGEMENT_DAYS,
    TRIGGER_MILESTONE,
    TRIGGER_RE_ENGAGEMENT,
    WEEKLY_CHECKIN_DAYS,
)
from app.config import settings

logger = logging.getLogger(__name__)


async def find_weekly_checkin_eligible(supabase: Client) -> list[str]:
    """Users with goals whose last nudge was more than WEEKLY_CHECKIN_DAYS ago.

    Returns:
        List of user-ID strings eligible for a weekly check-in nudge.
    """
    now_utc = datetime.now(tz=timezone.utc)
    weekly_cutoff = (now_utc - timedelta(days=WEEKLY_CHECKIN_DAYS)).isoformat()

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

    eligible: list[str] = []
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
            eligible.append(uid_str)
        elif last_nudge_rows[0]["created_at"] < weekly_cutoff:
            eligible.append(uid_str)

    return eligible


async def find_milestone_eligible(supabase: Client) -> list[str]:
    """Users whose analysis insight count exactly matches a milestone count.

    Deduplicates against recent milestone nudges (within
    ADVISOR_MILESTONE_DEDUP_HOURS).

    Returns:
        List of user-ID strings eligible for a milestone nudge.
    """
    now_utc = datetime.now(tz=timezone.utc)
    recent_milestone_cutoff = (
        now_utc - timedelta(hours=settings.ADVISOR_MILESTONE_DEDUP_HOURS)
    ).isoformat()

    eligible: list[str] = []

    for milestone_count in MILESTONE_COUNTS:
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
            # Avoid duplicate milestone nudges within dedup window
            existing = (
                supabase.table("advisor_nudges")
                .select("id")
                .eq("user_id", uid_str)
                .eq("trigger", TRIGGER_MILESTONE)
                .gt("created_at", recent_milestone_cutoff)
                .limit(1)
                .execute()
            )
            if not existing.data:
                eligible.append(uid_str)

    return eligible


async def find_re_engagement_eligible(supabase: Client) -> list[str]:
    """Users whose last activity was more than RE_ENGAGEMENT_DAYS ago.

    Deduplicates against recent re-engagement nudges to prevent spam.

    Returns:
        List of user-ID strings eligible for a re-engagement nudge.
    """
    now_utc = datetime.now(tz=timezone.utc)
    re_engagement_cutoff = (
        now_utc - timedelta(days=RE_ENGAGEMENT_DAYS)
    ).isoformat()
    last_re_engagement_nudge_cutoff = (
        now_utc - timedelta(days=RE_ENGAGEMENT_DAYS)
    ).isoformat()

    # "Last activity" = most recent analysis insight
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

    eligible: list[str] = []
    for uid_str in inactive_users:
        # Avoid spamming: skip if a re-engagement nudge was sent recently
        existing = (
            supabase.table("advisor_nudges")
            .select("id")
            .eq("user_id", uid_str)
            .eq("trigger", TRIGGER_RE_ENGAGEMENT)
            .gt("created_at", last_re_engagement_nudge_cutoff)
            .limit(1)
            .execute()
        )
        if not existing.data:
            eligible.append(uid_str)

    return eligible
