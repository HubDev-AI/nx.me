"""Nudge prompt templates — one per trigger type.

Spec Section 7.3: inline for MVP, will move to prompts/*.txt files later.
"""
from __future__ import annotations

from app.advisor.nudge_policy import (
    TRIGGER_MILESTONE,
    TRIGGER_POST_ANALYSIS,
    TRIGGER_RE_ENGAGEMENT,
    TRIGGER_WEEKLY_CHECKIN,
)

NUDGE_PROMPTS: dict[str, str] = {
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


def get_prompt(trigger: str) -> str:
    """Return the prompt template for a trigger type, defaulting to post_analysis."""
    return NUDGE_PROMPTS.get(trigger, NUDGE_PROMPTS[TRIGGER_POST_ANALYSIS])
