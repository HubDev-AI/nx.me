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

# Plan 2026-04-17-003 Unit 8. New trigger — fires from the generation
# worker on every successful glow-up completion (both before_image_url
# and after_image_url populated). The nudge generator looks at the
# actual before/after images and decides what to say; there is NO
# fixed topic taxonomy, NO server-side rotation, and NO ``focus``
# column in ``advisor_nudges``. Dedup emerges from the model's own
# access to prior bodies + model-authored ``observation_tag``s in the
# prompt's "do not repeat" block.
TRIGGER_POST_GLOWUP = "post_glowup"

# Milestone analysis counts that trigger a nudge (spec Section 7.1)
MILESTONE_COUNTS: frozenset[int] = frozenset({5, 10})

# Eligibility windows (spec Section 7.1)
WEEKLY_CHECKIN_DAYS = 7
RE_ENGAGEMENT_DAYS = 14

# A-5: Model sourced from config — single source of truth
MODEL_HAIKU = settings.ADVISOR_MODEL_HAIKU

# Max tokens per nudge — keep short and warm (spec Section 11 brevity principle)
MAX_TOKENS_NUDGE = 128
