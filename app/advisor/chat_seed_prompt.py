"""Chat-seeds prompt builder.

Plan 2026-04-20-001 Unit 5. Builds the text scaffolding for the Haiku
vision call that generates suggested chat seeds. Image blocks are
attached by the caller (same pattern as nudge_scheduler).

Voice/tone and image-guard constants are imported from nudge_templates so
the ban list and phrasing stay in one place (feedback_no_hardcoded_urls —
no magic strings duplicated across modules).
"""

from __future__ import annotations

from typing import Any

from app.advisor.nudge_templates import (
    IMAGE_TEXT_GUARD,
    VOICE_TONE_BLOCK,
    _render_profile_block,
)


def build_chat_seeds_prompt(profile: dict[str, Any] | None) -> str:
    """Build the user-message prompt body for the chat-seeds Haiku call.

    Plan 2026-04-20-001 Unit 5.

    Contract:
        * ``profile`` is the ``content`` dict of the user's stable
          ``style_profile`` row (face shape, symmetry, recommendations,
          optional summary), or ``None`` when no profile exists yet.
        * The caller attaches image blocks to the user message's
          ``content`` list after this text block — this builder only
          returns the text scaffolding.

    Output contract: the model must emit a single strict JSON object
    ``{"seeds": [{"label": "...", "text": "..."}, ...]}`` with exactly 3
    seeds and nothing else outside the JSON.
    """
    profile_block = _render_profile_block(profile)
    return (
        "Stable facts about this user:\n"
        f"{profile_block}\n\n"
        f"{VOICE_TONE_BLOCK}\n"
        f"{IMAGE_TEXT_GUARD}\n\n"
        "Look at the attached image. Suggest 3 curious questions the user "
        "might want to ask Ada right now. Each question should be short, in "
        "the user's voice, and framed as a first-person question.\n\n"
        "Respond with a single strict JSON object and nothing else: "
        '{"seeds": [{"label": "<short chip label, \u226424 chars>", '
        '"text": "<user-voice question ending with \'?\', \u2264140 chars>"}, '
        "...]} "
        "Emit exactly 3 seeds. "
        "No greetings, no sign-offs, no markdown, no prose outside the JSON."
    )
