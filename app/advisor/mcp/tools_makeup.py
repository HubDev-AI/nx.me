"""Feature-specific makeup tool — ``get_latest_makeup``.

Plan 2026-04-21-001 Unit 10. Mirrors tools_glowup.py: returns the
user's most recent completed makeup session as before + after images,
plus a trailing text block with ``feature=makeup`` metadata and the
applied preset + intensity.

Both images are returned inline as base64 — no signed URLs enter the
payload or log stream (consistent with tools_glowup / tools_jobs
storage-credentials contract).

Registry shape: single-tool singular convention (TOOL_SCHEMA + handle)
because makeup ships exactly one tool from this file.

Cross-user invariants (enforced by registry at construction time):
* ``input_schema`` does not accept ``user_id`` / ``uid`` / ``account``.
* Handler resolves the user from ``ctx.user_id`` only.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from app.advisor.mcp.context import McpContext
from app.advisor.mcp.tools_jobs import BUCKET_AFTER, BUCKET_BEFORE
from app.db.async_helpers import run_sync

logger = logging.getLogger(__name__)

# Anthropic content-block types — re-declared locally so this module
# stays self-contained (mirrors tools_glowup.py convention).
CONTENT_BLOCK_TYPE_IMAGE = "image"
CONTENT_BLOCK_TYPE_TEXT = "text"
SOURCE_TYPE_BASE64 = "base64"

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

FEATURE_TAG_MAKEUP = "makeup"

_MAKEUP_TOOL_NAME = "get_latest_makeup"

_MAKEUP_TOOL_DESCRIPTION = (
    "Returns the authenticated user's most recent completed makeup session "
    "as two images in order: the before (source) photo, then the "
    "AI-generated after photo with makeup applied. Images are returned "
    "inline as base64 — no URLs are exposed. A trailing text block carries "
    "'feature=makeup' metadata plus the applied preset and intensity.\n\n"
    "Call this when the user asks about their makeup look, asks what "
    "preset or intensity was applied, compares their look before and after, "
    "or asks a makeup styling question where seeing both images grounds the "
    "answer.\n\n"
    "Do NOT call this when the user has not run a makeup session — the tool "
    "returns is_error=True. Do NOT call it when the prior turn already "
    "fetched the same images. Never pass user_id — the server resolves "
    "the authenticated user."
)

TOOL_SCHEMA: dict[str, Any] = {
    "name": _MAKEUP_TOOL_NAME,
    "description": _MAKEUP_TOOL_DESCRIPTION,
    "input_schema": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
}


def _media_type_for_path(path: str) -> str:
    lowered = (path or "").lower()
    for ext, media_type in _EXTENSION_TO_MEDIA_TYPE.items():
        if lowered.endswith(ext):
            return media_type
    return DEFAULT_IMAGE_MEDIA_TYPE


def _encode_image_block(data: bytes, path: str) -> dict[str, Any]:
    return {
        "type": CONTENT_BLOCK_TYPE_IMAGE,
        "source": {
            "type": SOURCE_TYPE_BASE64,
            "media_type": _media_type_for_path(path),
            "data": base64.b64encode(data).decode("ascii"),
        },
    }


async def handle(ctx: McpContext) -> dict[str, Any]:
    """Return before + after makeup images + ``feature=makeup`` metadata."""
    row = await run_sync(
        ctx.advisor_repo.get_latest_completed_makeup_with_images, str(ctx.user_id)
    )
    if not row:
        return {
            "content": [
                {
                    "type": CONTENT_BLOCK_TYPE_TEXT,
                    "text": "no completed makeup session",
                }
            ],
            "is_error": True,
        }

    before_key = str(row.get("before_image_url") or "")
    after_key = str(row.get("after_image_url") or "")

    blocks: list[dict[str, Any]] = []
    try:
        before_bytes = await run_sync(
            ctx.advisor_repo.fetch_image_bytes, BUCKET_BEFORE, before_key
        )
        blocks.append(_encode_image_block(before_bytes, before_key))
    except Exception as exc:
        ctx.logger.warning("get_latest_makeup: failed to fetch before image: %s", exc)

    try:
        after_bytes = await run_sync(
            ctx.advisor_repo.fetch_image_bytes, BUCKET_AFTER, after_key
        )
        blocks.append(_encode_image_block(after_bytes, after_key))
    except Exception as exc:
        ctx.logger.warning("get_latest_makeup: failed to fetch after image: %s", exc)

    if not blocks:
        return {
            "content": [
                {
                    "type": CONTENT_BLOCK_TYPE_TEXT,
                    "text": (
                        f"feature={FEATURE_TAG_MAKEUP}; "
                        "image fetch unavailable right now"
                    ),
                }
            ],
            "is_error": True,
        }

    completed_at = str(row.get("completed_at") or "")
    created_at = str(row.get("created_at") or "")
    preset_slug = str(row.get("preset_slug") or "")
    intensity = str(row.get("intensity") or "")

    summary_parts = [f"feature={FEATURE_TAG_MAKEUP}"]
    if completed_at:
        summary_parts.append(f"completed_at={completed_at}")
    elif created_at:
        summary_parts.append(f"created_at={created_at}")
    if preset_slug:
        summary_parts.append(f"preset={preset_slug}")
    if intensity:
        summary_parts.append(f"intensity={intensity}")

    blocks.append({"type": CONTENT_BLOCK_TYPE_TEXT, "text": "; ".join(summary_parts)})
    return {"content": blocks, "is_error": False}
