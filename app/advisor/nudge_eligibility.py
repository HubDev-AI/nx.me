"""Nudge eligibility scans — database queries to find users eligible for nudges.

Each function returns a list of user-ID strings eligible for that trigger type.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.advisor.nudge_policy import (
    MILESTONE_COUNTS,
    RE_ENGAGEMENT_DAYS,
    TRIGGER_MILESTONE,
    TRIGGER_RE_ENGAGEMENT,
    WEEKLY_CHECKIN_DAYS,
)
from app.config import settings
from app.db.async_helpers import run_sync
from app.repositories.advisor_repo import AdvisorRepository

logger = logging.getLogger(__name__)


async def find_weekly_checkin_eligible(advisor_repo: AdvisorRepository) -> list[str]:
    """Users with goals whose last nudge was more than WEEKLY_CHECKIN_DAYS ago.

    Returns:
        List of user-ID strings eligible for a weekly check-in nudge.
    """
    now_utc = datetime.now(tz=timezone.utc)
    weekly_cutoff = (now_utc - timedelta(days=WEEKLY_CHECKIN_DAYS)).isoformat()

    user_ids_with_goals = await run_sync(advisor_repo.get_all_goal_user_ids)

    eligible: list[str] = []
    for uid_str in user_ids_with_goals:
        last_nudge = await run_sync(advisor_repo.get_latest_nudge_for_user, uid_str)
        if not last_nudge:
            # Never had a nudge — eligible
            eligible.append(uid_str)
        elif last_nudge["created_at"] < weekly_cutoff:
            eligible.append(uid_str)

    return eligible


async def find_milestone_eligible(advisor_repo: AdvisorRepository) -> list[str]:
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

    # Single COUNT query grouped by user_id — avoids fetching every insight row.
    count_per_user = await run_sync(advisor_repo.count_insights_by_user)

    eligible: list[str] = []

    for milestone_count in MILESTONE_COUNTS:
        milestone_users = [
            uid_str
            for uid_str, cnt in count_per_user.items()
            if cnt == milestone_count
        ]

        for uid_str in milestone_users:
            # Avoid duplicate milestone nudges within dedup window
            recent = await run_sync(
                advisor_repo.find_recent_nudges,
                uid_str, TRIGGER_MILESTONE, recent_milestone_cutoff,
            )
            if not recent:
                eligible.append(uid_str)

    return eligible


async def find_re_engagement_eligible(advisor_repo: AdvisorRepository) -> list[str]:
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
    insight_date_rows = await run_sync(advisor_repo.get_all_insights_with_timestamps)

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
        recent = await run_sync(
            advisor_repo.find_recent_nudges,
            uid_str, TRIGGER_RE_ENGAGEMENT, last_re_engagement_nudge_cutoff,
        )
        if not recent:
            eligible.append(uid_str)

    return eligible
