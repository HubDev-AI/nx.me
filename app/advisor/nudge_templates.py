"""Nudge prompt templates — one per trigger type.

Spec Section 7.3: inline for MVP, will move to prompts/*.txt files later.

Plan 2026-04-17-003 Unit 8 — ``post_analysis`` and ``post_glowup`` are
both served by the vision-grounded builder
:func:`build_vision_nudge_prompt`. The model looks at the attached
before/after images (fetched via the MCP registry — same code path Ada
chat uses), sees the user's stable ``style_profile``, and the last N
nudge bodies + model-authored ``observation_tag``s, then decides what
to say. There is no fixed topic taxonomy and no server-side rotation.
The earlier ``FOCUS_TOPICS = (hair, beard, brows, skin, fit,
accessories)`` rotation was culturally wrong on a women-primary
audience and has been removed entirely.
"""

from __future__ import annotations

from typing import Any

from app.advisor.nudge_policy import (
    TRIGGER_MILESTONE,
    TRIGGER_RE_ENGAGEMENT,
    TRIGGER_WEEKLY_CHECKIN,
)

# How many of the user's top recommendations to echo back in the
# vision-grounded prompt. Matches ``_USER_DATA_MAX_RECOMMENDATIONS`` in
# ``context_builder`` + ``summarize_memory_content`` so the "stable
# facts" block reads consistent across chat user_data and nudges.
_VISION_PROMPT_RECS_LIMIT = 3

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

    Raises KeyError for ``post_analysis`` / ``post_glowup`` — those two
    triggers are served by :func:`build_vision_nudge_prompt` with the
    actual before/after images attached, and should never flow through
    this generic template path.
    """
    return NUDGE_PROMPTS[trigger]


def _render_profile_block(profile: dict[str, Any] | None) -> str:
    """Render a ``style_profile.content`` dict into the same compact
    multi-line fragment the chat ``user_data`` block uses.

    Matches the comma-joined / label-free shape produced by
    ``context_builder.build_user_data_block`` so the "stable facts"
    line in the nudge prompt reads the same as what the chat surface
    shows the model in every other turn. Missing fields degrade quietly
    — a style_profile without recommendations or summary still
    produces a readable basics line.
    """
    if not profile:
        return "(no stable profile on file)"

    basics: list[str] = []
    face_shape = profile.get("face_shape")
    if face_shape:
        basics.append(f"{face_shape} face")
    symmetry_score = profile.get("symmetry_score")
    if symmetry_score is not None:
        try:
            basics.append(f"symmetry {float(symmetry_score):.2f}")
        except (TypeError, ValueError):
            pass

    lines: list[str] = []
    if basics:
        lines.append(", ".join(basics))

    recs = profile.get("recommendations")
    if isinstance(recs, list) and recs:
        rec_items = [str(r).strip() for r in recs if str(r).strip()]
        if rec_items:
            lines.append(", ".join(rec_items[:_VISION_PROMPT_RECS_LIMIT]))

    summary = profile.get("summary")
    if isinstance(summary, str) and summary.strip():
        lines.append(summary.strip())

    return "\n".join(lines) if lines else "(profile on file but empty)"


def _render_recent_nudges_block(recent_nudges: list[dict[str, Any]] | None) -> str:
    """Render a list of ``{body, observation_tag}`` rows into the
    "do not repeat" block the model consumes.

    Each row becomes a single bullet carrying the body + its
    ``observation_tag`` when present. Pre-Unit-8 rows with
    ``observation_tag=NULL`` render cleanly as "no tag" so the prompt
    stays usable during the roll-out window before the migration is
    applied everywhere.
    """
    if not recent_nudges:
        return "(none)"

    bullets: list[str] = []
    for row in recent_nudges:
        body = str(row.get("body") or row.get("content") or "").strip()
        if not body:
            continue
        raw_tag = row.get("observation_tag")
        tag = str(raw_tag).strip() if raw_tag else ""
        label = tag or "no tag"
        bullets.append(f"- [{label}] {body}")
    return "\n".join(bullets) if bullets else "(none)"


def build_vision_nudge_prompt(
    profile: dict[str, Any] | None,
    recent_nudges: list[dict[str, Any]] | None,
) -> str:
    """Build the user-message prompt body for a vision-grounded nudge.

    Plan 2026-04-17-003 Unit 8.

    Contract:
        * ``profile`` is the ``content`` dict of the user's stable
          ``style_profile`` row (face shape, symmetry, recommendations,
          optional summary). Same shape the chat ``user_data`` block
          consumes via ``_build_user_data``.
        * ``recent_nudges`` is the newest-first list returned by
          ``AdvisorRepository.get_recent_nudge_context``. Each row
          carries ``body`` (alias for ``content``), ``observation_tag``,
          and ``created_at``. ``observation_tag`` may be ``None`` for
          pre-Unit-8 rows and is rendered as "no tag".
        * The caller attaches before/after image blocks to the user
          message's ``content`` list — this builder only returns the
          text scaffolding. The prompt explicitly handles the degenerate
          "only one image attached" case (post_analysis has no after
          photo yet) by instructing the model to describe what is
          present without inventing an after.

    Output contract: the model must emit a single strict JSON object
    ``{"body": "<one warm sentence>", "observation_tag": "<1-3 words>"}``
    with nothing else. ``nudge_scheduler.generate_nudge`` parses the
    response via ``json.loads`` and drops the nudge on parse failure —
    no retry, next generation gets its own chance.
    """
    profile_block = _render_profile_block(profile)
    recent_block = _render_recent_nudges_block(recent_nudges)
    return (
        "Stable facts about this user:\n"
        f"{profile_block}\n\n"
        "Recent nudges you already sent (do not repeat the same idea "
        "or phrasing; label in square brackets is the observation_tag "
        "you previously chose):\n"
        f"{recent_block}\n\n"
        "Look at the attached before/after images. Pick the single "
        "most genuinely interesting specific thing about the new "
        "look — a detail that emerged, a contrast that reads well, a "
        "moment that lands. Write ONE warm sentence about that thing. "
        "If only a single image is attached (no generated 'after' "
        "yet), describe what is actually visible in the one image — "
        "do not invent details about a transformation that has not "
        "happened. After the sentence, choose a 1-3 word tag "
        "describing what you focused on (e.g. 'softer jaw', "
        "'cleaner brows', 'warmer undertone').\n\n"
        "Respond with a single strict JSON object and nothing else: "
        '{"body": "<one warm sentence>", '
        '"observation_tag": "<1-3 words>"}. '
        "No greetings, no sign-offs, no markdown, no prose outside "
        "the JSON."
    )
