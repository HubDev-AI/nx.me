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
from app.repositories.image_repo import ImageRepository

logger = logging.getLogger(__name__)

PUBLIC_BUCKET = "post-images"
AVATAR_BUCKET = "avatars"
RAW_SELFIES_BUCKET = "raw-selfies"
GENERATED_IMAGES_BUCKET = "generated-images"


@dataclass(frozen=True)
class PublishedImageURLs:
    """Public CDN URLs + storage keys for a published post's before/after.

    ``before_key``/``after_key`` are the storage keys inside
    :data:`PUBLIC_BUCKET` (derivation matches :func:`publish_post_images`).
    Callers need them to reach :meth:`OrphanedStorageKeyRepository.record`
    on partial-failure paths that must not orphan CDN-reachable blobs
    (see ``POST /v1/posts`` publish-pending pre-record).
    """

    before_url: str
    after_url: str
    before_key: str
    after_key: str


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

    Returns the public CDN URLs and storage keys for both images.

    Raises ``RuntimeError`` if any copy operation fails.
    """
    image_repo = ImageRepository(supabase)

    before_public_key = f"before/{user_id}/{before_image['storage_key'].split('/')[-1]}"
    after_public_key = f"after/{user_id}/{after_image['storage_key'].split('/')[-1]}"

    for src_img, public_key in [
        (before_image, before_public_key),
        (after_image, after_public_key),
    ]:
        raw_bytes = image_repo.download(
            src_img.get("bucket", "raw-selfies"), src_img["storage_key"]
        )
        image_repo.upload_public(
            PUBLIC_BUCKET,
            public_key,
            raw_bytes,
            "image/jpeg",
            upsert=True,
        )

    return PublishedImageURLs(
        before_url=get_public_url(before_public_key),
        after_url=get_public_url(after_public_key),
        before_key=before_public_key,
        after_key=after_public_key,
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
    image_repo = ImageRepository(supabase)
    return image_repo.build_avatar_signed_url(
        avatar_storage_key, settings.SIGNED_URL_EXPIRY_SECONDS
    )
