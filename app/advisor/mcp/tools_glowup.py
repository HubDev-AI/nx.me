"""Feature-specific glow-up tools — ``get_latest_photo`` + ``get_latest_glowup``.

Plan 2026-04-17-003 Unit 2. These two tools are the feature-explicit
siblings to the cross-feature ``get_latest_generation`` (Unit 9): they
return image bytes for the glow-up pipeline only, while the cross-feature
tool happily serves any completed ``jobs`` row regardless of
``source_type``.

``get_latest_glowup`` is Ada's primary visual anchor — whenever a
completed glow-up exists, it is the richest "what am I considering"
artifact the product has produced for the user. ``get_latest_photo`` is
intentionally de-prioritized in its description: it returns only the
source cleared upload (no generated "after") and should be used solely
as a pre-generation fallback for grooming questions that predate any
glow-up.

Both tools mirror ``tools_jobs.get_latest_generation``'s redaction and
storage-credentials contract: bytes come from
``supabase.storage.from_(bucket).download(path)`` via the repo, returning
base64-encoded Anthropic ``image`` content blocks. Signed URLs never
enter the payload or log stream — the whole point of the Unit 9 / Unit 2
rework.

Registry shape: this module exports the plural
``TOOL_SCHEMAS`` + ``HANDLERS`` surface (one entry per tool) so the
registry auto-registers both handlers from a single file drop.

Cross-user invariants (see ``registry.py`` for the full 4-layer stack):

* Neither tool's ``input_schema`` accepts ``user_id`` / ``uid`` / ``account``
  — the registry asserts this at construction time, and the Unit 9
  introspection test re-asserts it across the whole registry.
* Both handlers resolve the user from ``ctx.user_id`` only; any
  model-provided identifier would have been stripped upstream before
  the handler ran.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from app.advisor.mcp.context import McpContext
from app.advisor.mcp.tools_jobs import BUCKET_AFTER, BUCKET_BEFORE
from app.db.async_helpers import run_sync

logger = logging.getLogger(__name__)

# Anthropic content-block types. Re-declared locally (not imported from
# the registry) so this module stays self-contained — a tools_*.py file
# should never need to reach into registry internals.
CONTENT_BLOCK_TYPE_IMAGE = "image"
CONTENT_BLOCK_TYPE_TEXT = "text"
SOURCE_TYPE_BASE64 = "base64"

# Media-type map for base64 image blocks. Matches the dominant extensions
# the generation + upload pipelines write; JPEG is the sensible fallback
# because the existing image pipeline re-encodes to JPEG by default.
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

# Feature-metadata text-block tags written after the image block(s). The
# nudge generator (Unit 8) will key off these tags when it decides which
# observation_tag to favor, so they must stay stable.
FEATURE_TAG_GLOWUP = "glowup"
FEATURE_TAG_SOURCE_PHOTO = "source_photo"

# Cap for ``get_latest_photo``'s repo query. The tool intentionally
# returns exactly ONE source photo — the most recent cleared upload —
# because Ada reaches for this tool only when no glow-up exists and
# more than one pre-gen photo would flood the context.
SOURCE_PHOTO_FETCH_LIMIT = 1


def _media_type_for_path(path: str) -> str:
    """Guess the ``media_type`` for a storage key by extension.

    Anthropic requires a media_type on every base64 image block. Falls
    back to JPEG — the glow-up / upload pipeline writes JPEG by default,
    so the fallback matches the dominant case.
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


# ---------------------------------------------------------------------------
# get_latest_glowup — feature-specific "before + after" fetch
# ---------------------------------------------------------------------------

_GLOWUP_TOOL_NAME = "get_latest_glowup"

_GLOWUP_TOOL_DESCRIPTION = (
    "Returns the authenticated user's most recent completed glow-up as "
    "two images in order: the before (source) photo, then the "
    "AI-generated after photo. Images are returned inline as base64 — "
    "no URLs are exposed. A trailing text block carries "
    "'feature=glowup' metadata so the model can frame the reply "
    "correctly.\n\n"
    "Call this when the user asks about their glow-up, compares their "
    "current look to the generated one, asks what changed, or asks a "
    "styling question ('what hairstyle would suit me?', 'does this "
    "beard work?') where seeing both images would ground the answer. "
    "Prefer this over get_latest_photo whenever a glow-up is available "
    "— the after image shows what the user is actually thinking about.\n\n"
    "Do NOT call this when the user has not run a glow-up — the tool "
    "returns is_error=True. Do NOT call it when the user is asking "
    "general grooming advice not tied to their own face, and do NOT "
    "call it when the prior turn already fetched the same images. "
    "Never pass user_id — the server resolves the authenticated user."
)

_GLOWUP_TOOL_SCHEMA: dict[str, Any] = {
    "name": _GLOWUP_TOOL_NAME,
    "description": _GLOWUP_TOOL_DESCRIPTION,
    "input_schema": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
}


async def _handle_get_latest_glowup(ctx: McpContext) -> dict[str, Any]:
    """Return before + after glow-up images + ``feature=glowup`` metadata.

    Behavior:

    * Calls ``advisor_repo.get_latest_completed_glowup_with_images`` to
      resolve the newest completed glow-up row (``source_type`` filtered
      to ``glowup_analysis``). Repo-level filter prevents a make-up
      session (or any future polymorphic row) from leaking through this
      feature-specific tool.
    * When no glow-up exists, returns ``{"content": [...], "is_error":
      True}`` so the adapter can place ``is_error`` on the
      ``tool_result`` envelope per Anthropic's spec (not on an inner
      content block, where it is silently ignored).
    * Downloads before/after bytes via ``fetch_image_bytes`` (server-side
      storage creds; NEVER a signed URL). Each image becomes one Anthropic
      base64 ``image`` block. A single text block follows with
      ``feature=glowup`` + completed_at metadata so the model can
      reference the specific generation when replying.
    """
    row = await run_sync(
        ctx.advisor_repo.get_latest_completed_glowup_with_images, str(ctx.user_id)
    )
    if not row:
        return {
            "content": [
                {
                    "type": CONTENT_BLOCK_TYPE_TEXT,
                    "text": "no completed glow-up",
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
        ctx.logger.warning("get_latest_glowup: failed to fetch before image: %s", exc)

    try:
        after_bytes = await run_sync(
            ctx.advisor_repo.fetch_image_bytes, BUCKET_AFTER, after_key
        )
        blocks.append(_encode_image_block(after_bytes, after_key))
    except Exception as exc:
        ctx.logger.warning("get_latest_glowup: failed to fetch after image: %s", exc)

    if not blocks:
        # Both downloads failed — surface as a recoverable text block so
        # the model can apologize without the whole turn crashing.
        return {
            "content": [
                {
                    "type": CONTENT_BLOCK_TYPE_TEXT,
                    "text": (
                        f"feature={FEATURE_TAG_GLOWUP}; "
                        "image fetch unavailable right now"
                    ),
                }
            ],
            "is_error": True,
        }

    completed_at = str(row.get("completed_at") or "")
    created_at = str(row.get("created_at") or "")
    summary_parts = [f"feature={FEATURE_TAG_GLOWUP}"]
    if completed_at:
        summary_parts.append(f"completed_at={completed_at}")
    elif created_at:
        summary_parts.append(f"created_at={created_at}")
    blocks.append({"type": CONTENT_BLOCK_TYPE_TEXT, "text": "; ".join(summary_parts)})
    return {"content": blocks, "is_error": False}


# ---------------------------------------------------------------------------
# get_latest_photo — pre-generation fallback
# ---------------------------------------------------------------------------

_PHOTO_TOOL_NAME = "get_latest_photo"

_PHOTO_TOOL_DESCRIPTION = (
    "Returns the authenticated user's single most recent cleared source "
    "photo as one base64 image block, plus a trailing text block with "
    "'feature=source_photo' metadata. No signed URL is generated on "
    "this path.\n\n"
    "Use this ONLY when the user has no completed glow-up and a source "
    "photo alone is needed for a grooming question that predates any "
    "generation. Prefer get_latest_glowup whenever a glow-up exists — "
    "the glow-up is Ada's primary visual anchor, the source photo is "
    "only the pre-generation fallback.\n\n"
    "Do NOT call this when a glow-up is already available (call "
    "get_latest_glowup instead), when the question is general styling "
    "advice not tied to the user's own face, or when the prior turn "
    "already pulled in a photo. Never pass user_id — the server "
    "resolves the authenticated user."
)

_PHOTO_TOOL_SCHEMA: dict[str, Any] = {
    "name": _PHOTO_TOOL_NAME,
    "description": _PHOTO_TOOL_DESCRIPTION,
    "input_schema": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
}


async def _handle_get_latest_photo(ctx: McpContext) -> dict[str, Any]:
    """Return the single most recent cleared source photo + metadata.

    Uses the existing ``get_cleared_images(user_id, limit=1)`` repo
    query + ``fetch_image_bytes`` for the server-side download. Bucket
    is ``BUCKET_BEFORE`` (``raw-selfies``) — cleared uploads live
    alongside the glow-up's before-image pointer in the same bucket.

    When the user has no cleared images, the tool returns
    ``{"content": [text block], "is_error": True}`` so the adapter
    places ``is_error`` on the ``tool_result`` envelope. Download
    failures degrade the same way: better a textual "image fetch
    unavailable" than a pending tool_use the model cannot satisfy.
    """
    rows = await run_sync(
        ctx.advisor_repo.get_cleared_images,
        str(ctx.user_id),
        limit=SOURCE_PHOTO_FETCH_LIMIT,
    )
    if not rows:
        return {
            "content": [
                {
                    "type": CONTENT_BLOCK_TYPE_TEXT,
                    "text": "no source photo",
                }
            ],
            "is_error": True,
        }

    row = rows[0]
    storage_path = str(row.get("storage_path") or "")
    if not storage_path:
        return {
            "content": [
                {
                    "type": CONTENT_BLOCK_TYPE_TEXT,
                    "text": "no source photo",
                }
            ],
            "is_error": True,
        }

    try:
        img_bytes = await run_sync(
            ctx.advisor_repo.fetch_image_bytes, BUCKET_BEFORE, storage_path
        )
    except Exception as exc:
        ctx.logger.warning("get_latest_photo: failed to fetch source image: %s", exc)
        return {
            "content": [
                {
                    "type": CONTENT_BLOCK_TYPE_TEXT,
                    "text": (
                        f"feature={FEATURE_TAG_SOURCE_PHOTO}; "
                        "image fetch unavailable right now"
                    ),
                }
            ],
            "is_error": True,
        }

    return {
        "content": [
            _encode_image_block(img_bytes, storage_path),
            {
                "type": CONTENT_BLOCK_TYPE_TEXT,
                "text": f"feature={FEATURE_TAG_SOURCE_PHOTO}",
            },
        ],
        "is_error": False,
    }


# ---------------------------------------------------------------------------
# Registry surface — plural convention so both tools ship from one file.
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [_GLOWUP_TOOL_SCHEMA, _PHOTO_TOOL_SCHEMA]

HANDLERS: dict[str, Any] = {
    _GLOWUP_TOOL_NAME: _handle_get_latest_glowup,
    _PHOTO_TOOL_NAME: _handle_get_latest_photo,
}
