"""Nudge prompt templates — one per trigger type.

Spec Section 7.3: inline for MVP, will move to prompts/*.txt files later.

`post_analysis` is handled separately via `build_post_analysis_prompt`
because it must be grounded in the user's actual analysis result
(face_shape, symmetry_score, recommendations) to avoid hallucinating
content the user never saw.
"""

from __future__ import annotations

from app.advisor.nudge_policy import (
    TRIGGER_MILESTONE,
    TRIGGER_RE_ENGAGEMENT,
    TRIGGER_WEEKLY_CHECKIN,
)

# How many of the user's top recommendations to quote back in the prompt.
# Mirrors memory_manager.summarize_memory_content, which also caps at 3.
_POST_ANALYSIS_RECS_LIMIT = 3

NUDGE_PROMPTS: dict[str, str] = {
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
    """Return the prompt template for a generic trigger type.

    Raises KeyError for `post_analysis` — that trigger has its own
    grounded builder (`build_post_analysis_prompt`) and should never
    flow through this generic template path.
    """
    return NUDGE_PROMPTS[trigger]


def build_post_analysis_prompt(
    face_shape: str | None,
    symmetry_score: float | None,
    recommendations: list[str] | None,
) -> str:
    """Build a grounded user-message prompt for a post-analysis nudge.

    Reference the user's actual analysis result so the LLM has a
    concrete fact to anchor on — the prior generic prompt ("based on
    their latest result") silently hallucinated details the user
    never saw in their report.
    """
    recs = (recommendations or [])[:_POST_ANALYSIS_RECS_LIMIT]
    recs_block = "\n".join(f"- {r}" for r in recs) if recs else "- (none recorded)"
    shape = face_shape or "unknown"
    # Round symmetry to one decimal for prompt brevity; display value only.
    sym = f"{symmetry_score:.1f}" if isinstance(symmetry_score, (int, float)) else "unknown"
    return (
        "The user just completed a face analysis. Their actual result:\n"
        f"- Face shape: {shape}\n"
        f"- Symmetry score: {sym}\n"
        f"- Top recommendations:\n{recs_block}\n\n"
        "Write one warm, encouraging sentence that references at least "
        "one concrete element from this result (the face shape, the "
        "symmetry score, or one recommendation above). Do not invent "
        "details that are not in the result. No greetings. No sign-offs."
    )
