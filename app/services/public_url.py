"""Storage URL helpers for post images and user avatars.

Only images the user explicitly publishes (via POST /posts) go to
the public bucket. Raw selfies and generated images stay private
until the user chooses to share.

Buckets:
  raw-selfies       — PRIVATE (uploads, owner-only signed URLs)
  generated-images   — PRIVATE (generation results, owner-only signed URLs)
  post-images        — PUBLIC  (both before + after, copied on post creation)
  avatars            — PRIVATE (owner-only signed URLs)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from supabase import Client

from app.config import settings

logger = logging.getLogger(__name__)

PUBLIC_BUCKET = "post-images"
AVATAR_BUCKET = "avatars"


@dataclass(frozen=True)
class PublishedImageURLs:
    """Public CDN URLs for a published post's before/after images."""

    before_url: str
    after_url: str


def publish_post_images(
    supabase: Client,
    *,
    user_id: str,
    before_image: dict,
    after_image: dict,
) -> PublishedImageURLs:
    """Copy before/after images from private buckets to the public bucket.

    Each ``image`` dict must contain ``storage_key`` and ``bucket`` fields
    (as stored in the ``images`` table).

    Returns the public CDN URLs for both images.

    Raises ``RuntimeError`` if any copy operation fails.
    """
    before_public_key = f"before/{user_id}/{before_image['storage_key'].split('/')[-1]}"
    after_public_key = f"after/{user_id}/{after_image['storage_key'].split('/')[-1]}"

    for src_img, public_key in [
        (before_image, before_public_key),
        (after_image, after_public_key),
    ]:
        raw_bytes = supabase.storage.from_(src_img.get("bucket", "raw-selfies")).download(
            src_img["storage_key"]
        )
        supabase.storage.from_(PUBLIC_BUCKET).upload(
            path=public_key,
            file=raw_bytes,
            file_options={"content-type": "image/jpeg", "upsert": "true"},
        )

    return PublishedImageURLs(
        before_url=get_public_url(before_public_key),
        after_url=get_public_url(after_public_key),
    )


def get_public_url(storage_key: str) -> str:
    """Build a stable public CDN URL for a published post image."""
    base = settings.PUBLIC_STORAGE_BASE_URL
    if base:
        return f"{base}/{PUBLIC_BUCKET}/{storage_key}"
    return f"{settings.SUPABASE_URL}/storage/v1/object/public/{PUBLIC_BUCKET}/{storage_key}"


def build_avatar_url(supabase: Client, avatar_storage_key: str | None) -> str | None:
    """Generate a signed URL for an avatar stored in the private avatars bucket.

    Returns None if no key is provided or the signed URL request fails.
    """
    if not avatar_storage_key:
        return None
    try:
        return supabase.storage.from_(AVATAR_BUCKET).create_signed_url(
            avatar_storage_key, settings.SIGNED_URL_EXPIRY_SECONDS
        )["signedURL"]
    except Exception:
        logger.warning("Failed to generate signed URL for avatar key: %s", avatar_storage_key)
        return None
