"""Public URL generation for post images.

Only images the user explicitly publishes (via POST /posts) go to
the public bucket. Raw selfies and generated images stay private
until the user chooses to share.

Buckets:
  raw-selfies       — PRIVATE (uploads, owner-only signed URLs)
  generated-images   — PRIVATE (generation results, owner-only signed URLs)
  post-images        — PUBLIC  (both before + after, copied on post creation)
"""
from __future__ import annotations

from app.config import settings

PUBLIC_BUCKET = "post-images"


def get_public_url(storage_key: str) -> str:
    """Build a stable public CDN URL for a published post image."""
    base = settings.PUBLIC_STORAGE_BASE_URL
    if base:
        return f"{base}/{PUBLIC_BUCKET}/{storage_key}"
    return f"{settings.SUPABASE_URL}/storage/v1/object/public/{PUBLIC_BUCKET}/{storage_key}"
