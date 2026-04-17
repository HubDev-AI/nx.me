"""Status-only job view — ``get_latest_job_status``.

Plan 2026-04-17-003 Unit 9. A sibling of ``tools_jobs.py``: same
polymorphic ``jobs`` table, but this tool returns only ``{status,
created_at, completed_at, feature}`` — no URLs, no image bytes. Ada
reaches for this when the user asks "is my glow-up done?" and no image
context is needed; cheaper than the image fetch and never exposes
media.

The two tools live in separate modules because the registry convention
(one ``TOOL_SCHEMA`` + ``handle`` per ``tools_*.py``) keeps the mapping
unambiguous — a single module exporting two tools would complicate the
discovery rule without any corresponding gain.
"""

from __future__ import annotations

from typing import Any

from app.advisor.mcp.context import McpContext
from app.db.async_helpers import run_sync

_TOOL_NAME = "get_latest_job_status"

CONTENT_BLOCK_TYPE_TEXT = "text"

_TOOL_DESCRIPTION = (
    "Returns the authenticated user's most recent job status as a text "
    "summary: status, source feature (glowup_analysis or "
    "makeup_session), created_at, and completed_at. No image bytes, no "
    "URLs.\n\n"
    "Call this when the user asks 'is my glow-up done?', 'did it work?', "
    "or 'when was this generated?'. Prefer it over get_latest_generation "
    "whenever you only need the state — it never exposes media and costs "
    "nothing to fetch.\n\n"
    "Do NOT call this when you already know the status from prior turns, "
    "and do NOT chain it with get_latest_generation (if you already plan "
    "to call the latter, skip the status fetch). Never pass user_id — "
    "the server resolves the authenticated user."
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


async def handle(ctx: McpContext) -> dict[str, Any]:
    """Return text describing the most recent job's state.

    Returns ``{"content": [text block], "is_error": False}`` — the
    "no jobs yet" case is a reportable outcome for the model, not an
    error on the ``tool_result`` envelope.
    """
    row = await run_sync(ctx.advisor_repo.get_latest_job_for_user, str(ctx.user_id))
    if not row:
        return {
            "content": [{"type": CONTENT_BLOCK_TYPE_TEXT, "text": "no jobs yet"}],
            "is_error": False,
        }

    status = str(row.get("status") or "unknown")
    feature = str(row.get("source_type") or "unknown")
    created_at = str(row.get("created_at") or "")
    completed_at = str(row.get("completed_at") or "")
    parts = [f"status={status}", f"feature={feature}"]
    if created_at:
        parts.append(f"created_at={created_at}")
    if completed_at:
        parts.append(f"completed_at={completed_at}")
    return {
        "content": [{"type": CONTENT_BLOCK_TYPE_TEXT, "text": "; ".join(parts)}],
        "is_error": False,
    }
