"""``get_style_profile`` — Ada reads the user's stable style facts on demand.

Plan 2026-04-17-003 Unit 9. Wraps ``AdvisorRepository.get_style_profile``,
which returns the single row introduced by Unit 7. Zero inputs — the
authenticated user is the only scope, enforced by ``ctx.user_id``.

Description contract (per Unit 9 template):
  * What it returns — the user's current face-shape, symmetry, and
    current recommendations (one row, upserted on every analysis).
  * When to call — any styling question grounded in stable traits where
    re-asking the user for their face shape would be redundant.
  * When NOT to call — pure chit-chat, or when the user is asking about
    someone other than themselves. Never pass user_id.
"""

from __future__ import annotations

from typing import Any

from app.advisor.mcp.context import McpContext

_TOOL_NAME = "get_style_profile"
_TOOL_DESCRIPTION = (
    "Returns the authenticated user's stable style profile — face shape, "
    "symmetry score, current top recommendations, and the timestamp of the "
    "last analysis that updated it. The row is a single upserted record, "
    "not a history.\n\n"
    "Call this when the user asks a styling question that benefits from "
    "their known traits ('what hairstyle would suit me?', 'what looks work "
    "with my face shape?', 'should I grow my beard?') and you do not "
    "already have the profile in context. Prefer this over asking the user "
    "to re-describe themselves.\n\n"
    "Do NOT call this when no analysis has been run (the tool returns "
    "'no profile' text — do not treat it as an error), when the user is "
    "asking general advice not tied to their own face, or when a recent "
    "turn already surfaced the profile. Never pass user_id — the server "
    "resolves the authenticated user from the session."
)

TOOL_SCHEMA: dict[str, Any] = {
    "name": _TOOL_NAME,
    "description": _TOOL_DESCRIPTION,
    "input_schema": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
}


async def handle(ctx: McpContext) -> list[dict[str, Any]]:
    """Return a single text content block summarizing the profile.

    No image blocks — this tool is text-only. Returns a terse "no profile"
    message when the user has never completed an analysis so the model can
    reply sensibly instead of crashing.
    """
    profile = ctx.advisor_repo.get_style_profile(str(ctx.user_id))
    if not profile:
        return [{"type": "text", "text": "no profile yet"}]

    content = profile.get("content") or {}
    parts: list[str] = []
    face_shape = content.get("face_shape")
    if face_shape:
        parts.append(f"{face_shape} face")
    symmetry = content.get("symmetry_score")
    if symmetry is not None:
        try:
            parts.append(f"symmetry {float(symmetry):.2f}")
        except (TypeError, ValueError):
            pass
    recs = content.get("recommendations")
    if isinstance(recs, list) and recs:
        rec_items = [str(r).strip() for r in recs if str(r).strip()]
        if rec_items:
            parts.append("recs: " + ", ".join(rec_items[:3]))
    last_updated = content.get("last_updated_at")
    if last_updated:
        parts.append(f"updated {last_updated}")
    text = "; ".join(parts) if parts else "profile exists but empty"
    return [{"type": "text", "text": text}]
