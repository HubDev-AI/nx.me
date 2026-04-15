"""Tests for nudge eligibility scans.

Pins the batch-dedup behaviour so the N+1 → single-query refactor doesn't
regress and so future changes respect the "recently nudged users are
excluded" invariant.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.advisor import nudge_eligibility
from app.advisor.nudge_policy import (
    MILESTONE_COUNTS,
    TRIGGER_MILESTONE,
    TRIGGER_RE_ENGAGEMENT,
)


def _make_repo(
    *,
    goal_users: set[str] | None = None,
    recent_nudge_users: set[str] | None = None,
    counts_by_user: dict[str, int] | None = None,
    insight_rows: list[dict] | None = None,
    recent_nudge_by_trigger: dict[str, set[str]] | None = None,
) -> MagicMock:
    """Build a MagicMock AdvisorRepository with canned responses."""
    repo = MagicMock()
    repo.get_all_goal_user_ids.return_value = goal_users or set()
    repo.count_insights_by_user.return_value = counts_by_user or {}
    repo.get_all_insights_with_timestamps.return_value = insight_rows or []

    by_trigger = recent_nudge_by_trigger or {}

    def fake_batch(since: str, trigger: str | None = None) -> set[str]:
        if trigger is None:
            return recent_nudge_users or set()
        return by_trigger.get(trigger, set())

    repo.get_user_ids_with_nudge_since.side_effect = fake_batch
    return repo


class TestWeeklyCheckinEligible:
    @pytest.mark.asyncio
    async def test_excludes_users_with_recent_nudge(self):
        repo = _make_repo(
            goal_users={"a", "b", "c"},
            recent_nudge_users={"b"},
        )
        eligible = await nudge_eligibility.find_weekly_checkin_eligible(repo)
        assert set(eligible) == {"a", "c"}
        # Exactly ONE batch query — not one per user (N+1 prevention).
        assert repo.get_user_ids_with_nudge_since.call_count == 1

    @pytest.mark.asyncio
    async def test_no_goal_users_returns_empty(self):
        repo = _make_repo(goal_users=set())
        eligible = await nudge_eligibility.find_weekly_checkin_eligible(repo)
        assert eligible == []


class TestMilestoneEligible:
    @pytest.mark.asyncio
    async def test_excludes_users_with_recent_milestone_nudge(self):
        milestone = next(iter(MILESTONE_COUNTS))
        repo = _make_repo(
            counts_by_user={"a": milestone, "b": milestone, "c": milestone - 1},
            recent_nudge_by_trigger={TRIGGER_MILESTONE: {"a"}},
        )
        eligible = await nudge_eligibility.find_milestone_eligible(repo)
        assert set(eligible) == {"b"}

    @pytest.mark.asyncio
    async def test_one_batch_query_regardless_of_user_count(self):
        milestone = next(iter(MILESTONE_COUNTS))
        repo = _make_repo(
            counts_by_user={f"u{i}": milestone for i in range(50)},
            recent_nudge_by_trigger={TRIGGER_MILESTONE: set()},
        )
        eligible = await nudge_eligibility.find_milestone_eligible(repo)
        assert len(eligible) == 50
        # Must remain a single batch call — not 50.
        assert repo.get_user_ids_with_nudge_since.call_count == 1


class TestReEngagementEligible:
    @pytest.mark.asyncio
    async def test_inactive_users_minus_recent_nudged(self):
        # Both users are inactive (created_at in the past), but one was
        # already re-engaged recently and must be excluded.
        old_ts = "2020-01-01T00:00:00+00:00"
        repo = _make_repo(
            insight_rows=[
                {"user_id": "a", "created_at": old_ts},
                {"user_id": "b", "created_at": old_ts},
            ],
            recent_nudge_by_trigger={TRIGGER_RE_ENGAGEMENT: {"a"}},
        )
        eligible = await nudge_eligibility.find_re_engagement_eligible(repo)
        assert eligible == ["b"]
