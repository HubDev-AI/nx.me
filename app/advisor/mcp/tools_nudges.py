"""``get_recent_nudges`` — Ada reads the user's recent passive nudges on demand.

Plan 2026-04-17-003 Unit 9. Wraps
``AdvisorRepository.get_recent_nudges_for_context`` (added in Unit 4)
without side-effects on ``read_at``. Input surface is intentionally
limited to safe, non-identifying knobs: ``limit`` and ``since_days``.
User scoping is resolved from ``ctx.user_id``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.advisor.mcp.context import McpContext
from app.db.async_helpers import run_sync

_TOOL_NAME = "get_recent_nudges"

# Tight bounds on both inputs — the registry strips unknown args, but we
# still need to guard against a model passing ``limit=1000`` or
# ``since_days=-1``. Enforced here + clamped in the handler.
_MIN_LIMIT = 1
_MAX_LIMIT = 20
_DEFAULT_LIMIT = 5

_MIN_SINCE_DAYS = 1
_MAX_SINCE_DAYS = 60
_DEFAULT_SINCE_DAYS = 14

_TOOL_DESCRIPTION = (
    "Returns the authenticated user's most recent advisor nudges as a "
    "short bulleted list of {body, created_at} records. "
    "Nudges are product-authored messages the user saw on a passive "
    "surface (e.g., after a completed analysis or glow-up).\n\n"
    "Call this when the user references a nudge ('you said I should try "
    "bangs'), when you want to avoid re-treading the same advice, or "
    "when the prior turn left nudge context outside what you already "
    "have.\n\n"
    "Do NOT call this as small talk — the list may be empty, and that is "
    "not an error. Never pass user_id — the server resolves the "
    "authenticated user from the session."
)

TOOL_SCHEMA: dict[str, Any] = {
    "name": _TOOL_NAME,
    "description": _TOOL_DESCRIPTION,
    "input_schema": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "minimum": _MIN_LIMIT,
                "maximum": _MAX_LIMIT,
                "description": (
                    f"Maximum number of nudges to return (default {_DEFAULT_LIMIT})."
                ),
            },
            "since_days": {
                "type": "integer",
                "minimum": _MIN_SINCE_DAYS,
                "maximum": _MAX_SINCE_DAYS,
                "description": (
                    f"Only return nudges created within the last N days "
                    f"(default {_DEFAULT_SINCE_DAYS})."
                ),
            },
        },
        "additionalProperties": False,
    },
}


def _clamp(value: Any, lo: int, hi: int, default: int) -> int:
    """Coerce + clamp a numeric input to ``[lo, hi]``; use ``default`` on coerce failure."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


async def handle(
    ctx: McpContext,
    limit: int | None = None,
    since_days: int | None = None,
) -> dict[str, Any]:
    """Return the newest matching nudges as a single text block.

    Output shape is a human-readable bullet list so the model can quote
    or reference it verbatim. JSON would force the model to parse and
    re-render which is cheaper on tokens but worse for voice fidelity.
    Returns ``{"content": [...], "is_error": False}`` — an empty nudge
    list is a reportable outcome, not an envelope-level error.
    """
    n_limit = _clamp(
        limit if limit is not None else _DEFAULT_LIMIT,
        _MIN_LIMIT,
        _MAX_LIMIT,
        _DEFAULT_LIMIT,
    )
    n_days = _clamp(
        since_days if since_days is not None else _DEFAULT_SINCE_DAYS,
        _MIN_SINCE_DAYS,
        _MAX_SINCE_DAYS,
        _DEFAULT_SINCE_DAYS,
    )
    since_iso = (datetime.now(tz=timezone.utc) - timedelta(days=n_days)).isoformat()
    rows = await run_sync(
        ctx.advisor_repo.get_recent_nudges_for_context,
        user_id=str(ctx.user_id),
        limit=n_limit,
        since_iso=since_iso,
    )
    if not rows:
        return {
            "content": [{"type": "text", "text": "no recent nudges"}],
            "is_error": False,
        }

    lines: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        body = row.get("body") or ""
        body_str = (
            str(body).replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()
        )
        if not body_str:
            continue
        created_at = str(row.get("created_at", "")).strip()
        if created_at:
            lines.append(f"- ({created_at}) {body_str}")
        else:
            lines.append(f"- {body_str}")
    text = "\n".join(lines) if lines else "no recent nudges"
    return {"content": [{"type": "text", "text": text}], "is_error": False}
