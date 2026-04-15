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
    # One batch query instead of N — users with ANY nudge inside the window
    # are NOT eligible; everyone else (goal user \ recent) is.
    recently_nudged = await run_sync(
        advisor_repo.get_user_ids_with_nudge_since, weekly_cutoff
    )
    return [uid for uid in user_ids_with_goals if uid not in recently_nudged]


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
    # One batch query for dedup — replaces O(n) find_recent_nudges calls.
    recently_nudged = await run_sync(
        advisor_repo.get_user_ids_with_nudge_since,
        recent_milestone_cutoff,
        TRIGGER_MILESTONE,
    )

    eligible: list[str] = []
    for milestone_count in MILESTONE_COUNTS:
        for uid_str, cnt in count_per_user.items():
            if cnt == milestone_count and uid_str not in recently_nudged:
                eligible.append(uid_str)

    return eligible


async def find_re_engagement_eligible(advisor_repo: AdvisorRepository) -> list[str]:
    """Users whose last activity was more than RE_ENGAGEMENT_DAYS ago.

    Deduplicates against recent re-engagement nudges to prevent spam.

    Returns:
        List of user-ID strings eligible for a re-engagement nudge.
    """
    now_utc = datetime.now(tz=timezone.utc)
    re_engagement_cutoff = (now_utc - timedelta(days=RE_ENGAGEMENT_DAYS)).isoformat()
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
    # One batch query for dedup — replaces O(n) find_recent_nudges calls.
    recently_nudged = await run_sync(
        advisor_repo.get_user_ids_with_nudge_since,
        last_re_engagement_nudge_cutoff,
        TRIGGER_RE_ENGAGEMENT,
    )
    return [uid for uid in inactive_users if uid not in recently_nudged]
