"""Nudge trigger policies — when each nudge type fires.

Plan 2026-04-17-003 Unit 2: dropped post_analysis / weekly_checkin /
milestone / re_engagement triggers. Only post_glowup remains.
"""

from __future__ import annotations

from app.config import settings

# Plan 2026-04-17-003 Unit 8. Fires from the generation worker on every
# successful glow-up completion (both before_image_url and after_image_url
# populated). The nudge generator looks at the actual before/after images
# and decides what to say; there is NO fixed topic taxonomy, NO
# server-side rotation, and NO ``focus`` column in ``advisor_nudges``.
# Dedup emerges from the model's own access to prior bodies +
# model-authored ``observation_tag``s in the prompt's "do not repeat" block.
TRIGGER_POST_GLOWUP = "post_glowup"
TRIGGER_POST_MAKEUP = "post_makeup"

# A-5: Model sourced from config — single source of truth
MODEL_HAIKU = settings.ADVISOR_MODEL_HAIKU

# Max tokens per nudge — keep short and warm (spec Section 11 brevity principle)
MAX_TOKENS_NUDGE = 128
