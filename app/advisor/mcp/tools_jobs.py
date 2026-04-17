"""Cross-feature generation tool — ``get_latest_generation``.

Plan 2026-04-17-003 Unit 9. The ``jobs`` table is polymorphic
(``source_type`` is ``glowup_analysis`` or ``makeup_session`` per
migration 0034) and Ada often does not know which feature the user is
referencing. This tool exposes the polymorphic row as a single
cross-feature fetch: it returns the before + after images as base64
Anthropic ``image`` blocks plus a text block carrying
``feature=<source_type>`` so the model can frame the reply correctly.
No signed URL anywhere in the path.

A sibling module ``tools_job_status.py`` exposes a status-only view for
state queries that don't need image bytes — Unit 9 kept the two tools in
separate modules because the registry indexes one ``TOOL_SCHEMA`` per
file.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from app.advisor.mcp.context import McpContext

logger = logging.getLogger(__name__)

_TOOL_NAME = "get_latest_generation"

# Bucket names for the two stored URL columns. These mirror the canonical
# split in ``app/api/jobs.py`` (before in ``raw-selfies``, after in
# ``generated-images``) — keeping them as named constants so the tool
# module is the single point at which the bucket convention is referenced
# (per ``feedback_no_hardcoded_urls``).
BUCKET_BEFORE = "raw-selfies"
BUCKET_AFTER = "generated-images"

# Anthropic vision block fields (base64 source).
IMAGE_MEDIA_TYPE_JPEG = "image/jpeg"
IMAGE_MEDIA_TYPE_PNG = "image/png"
IMAGE_MEDIA_TYPE_WEBP = "image/webp"
DEFAULT_IMAGE_MEDIA_TYPE = IMAGE_MEDIA_TYPE_JPEG

_EXTENSION_TO_MEDIA_TYPE: dict[str, str] = {
    ".jpg": IMAGE_MEDIA_TYPE_JPEG,
    ".jpeg": IMAGE_MEDIA_TYPE_JPEG,
    ".png": IMAGE_MEDIA_TYPE_PNG,
    ".webp": IMAGE_MEDIA_TYPE_WEBP,
}

CONTENT_BLOCK_TYPE_IMAGE = "image"
CONTENT_BLOCK_TYPE_TEXT = "text"
SOURCE_TYPE_BASE64 = "base64"


def _media_type_for_path(path: str) -> str:
    """Guess the ``media_type`` for a storage key by extension.

    Anthropic requires a media_type on every base64 image block. Falls
    back to JPEG — the generation pipeline writes JPEG by default, so
    the fallback matches the dominant case.
    """
    lowered = (path or "").lower()
    for ext, media_type in _EXTENSION_TO_MEDIA_TYPE.items():
        if lowered.endswith(ext):
            return media_type
    return DEFAULT_IMAGE_MEDIA_TYPE


def _encode_image_block(data: bytes, path: str) -> dict[str, Any]:
    """Encode raw image bytes into an Anthropic base64 image content block."""
    return {
        "type": CONTENT_BLOCK_TYPE_IMAGE,
        "source": {
            "type": SOURCE_TYPE_BASE64,
            "media_type": _media_type_for_path(path),
            "data": base64.b64encode(data).decode("ascii"),
        },
    }


_TOOL_DESCRIPTION = (
    "Returns the authenticated user's most recent completed generation "
    "as two images (before, then after) plus a text block carrying the "
    "feature name (glowup_analysis or makeup_session). Images are "
    "returned inline as base64 — no URLs are exposed.\n\n"
    "Call this when the user asks about their latest result, compares "
    "their current look to the generated one, asks what changed, or "
    "asks a styling question ('what hairstyle would suit me?') where "
    "seeing both images would ground the answer. Prefer this "
    "cross-feature fetch when the user does not name the feature — it "
    "works for any completed job.\n\n"
    "Do NOT call this when the user has no completed generation — the "
    "tool returns 'no completed generation' text (not an error). Do NOT "
    "call it on purely textual small-talk. Never pass user_id — the "
    "server resolves the authenticated user."
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
    """Return the latest generation's before/after images + feature metadata."""
    row = ctx.advisor_repo.get_latest_completed_job_with_images(str(ctx.user_id))
    if not row:
        return [{"type": CONTENT_BLOCK_TYPE_TEXT, "text": "no completed generation"}]

    feature = str(row.get("source_type") or "unknown")
    before_key = str(row.get("before_image_url") or "")
    after_key = str(row.get("after_image_url") or "")

    blocks: list[dict[str, Any]] = []
    try:
        before_bytes = ctx.advisor_repo.fetch_image_bytes(BUCKET_BEFORE, before_key)
        blocks.append(_encode_image_block(before_bytes, before_key))
    except Exception as exc:
        ctx.logger.warning(
            "get_latest_generation: failed to fetch before image: %s", exc
        )

    try:
        after_bytes = ctx.advisor_repo.fetch_image_bytes(BUCKET_AFTER, after_key)
        blocks.append(_encode_image_block(after_bytes, after_key))
    except Exception as exc:
        ctx.logger.warning(
            "get_latest_generation: failed to fetch after image: %s", exc
        )

    if not blocks:
        # Both downloads failed — surface as recoverable text rather than
        # raising (registry would otherwise emit a generic error result).
        return [
            {
                "type": CONTENT_BLOCK_TYPE_TEXT,
                "text": (f"feature={feature}; image fetch unavailable right now"),
            }
        ]

    # One text block with feature metadata after the images so the model
    # can reason about which feature it's looking at when both are
    # plausible.
    created_at = str(row.get("created_at") or "")
    completed_at = str(row.get("completed_at") or "")
    summary_parts = [f"feature={feature}"]
    if completed_at:
        summary_parts.append(f"completed_at={completed_at}")
    elif created_at:
        summary_parts.append(f"created_at={created_at}")
    blocks.append({"type": CONTENT_BLOCK_TYPE_TEXT, "text": "; ".join(summary_parts)})
    return blocks
