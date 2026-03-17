"""Public URL generation for post images.

Post images are served from a public bucket — no signed URLs needed.
In production, PUBLIC_STORAGE_BASE_URL points to CloudFront.
In development, falls back to Supabase public storage URL.
"""
from __future__ import annotations

from app.config import settings

# Buckets: raw-selfies (private), post-images (public), generated-images (public)
_PUBLIC_BUCKET_POSTS = "post-images"
_PUBLIC_BUCKET_GENERATED = "generated-images"


def get_public_url(bucket: str, storage_key: str) -> str:
    """Build a stable public URL for a storage object."""
    base = settings.PUBLIC_STORAGE_BASE_URL
    if base:
        return f"{base}/{bucket}/{storage_key}"
    # Fallback: Supabase public bucket URL
    return f"{settings.SUPABASE_URL}/storage/v1/object/public/{bucket}/{storage_key}"


def get_post_before_url(storage_key: str) -> str:
    """Public URL for a post's before image."""
    return get_public_url(_PUBLIC_BUCKET_POSTS, storage_key)


def get_post_after_url(storage_key: str) -> str:
    """Public URL for a post's after (generated) image."""
    return get_public_url(_PUBLIC_BUCKET_GENERATED, storage_key)
