"""Nudge trigger policies — when each nudge type fires.

Spec Section 7.1: trigger types, eligibility windows, milestone counts.
"""

from __future__ import annotations

from app.config import settings

# Trigger string constants — spec Section 7.1
TRIGGER_POST_ANALYSIS = "post_analysis"
TRIGGER_WEEKLY_CHECKIN = "weekly_checkin"
TRIGGER_MILESTONE = "milestone"
TRIGGER_RE_ENGAGEMENT = "re_engagement"

# Milestone analysis counts that trigger a nudge (spec Section 7.1)
MILESTONE_COUNTS: frozenset[int] = frozenset({5, 10})

# Eligibility windows (spec Section 7.1)
WEEKLY_CHECKIN_DAYS = 7
RE_ENGAGEMENT_DAYS = 14

# A-5: Model sourced from config — single source of truth
MODEL_HAIKU = settings.ADVISOR_MODEL_HAIKU

# Max tokens per nudge — keep short and warm (spec Section 11 brevity principle)
MAX_TOKENS_NUDGE = 128
