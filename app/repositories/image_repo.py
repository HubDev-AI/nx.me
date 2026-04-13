"""Image repository — all supabase queries for the images table and storage buckets.

Follows the same pattern as UserRepository: constructor takes a Client,
methods are synchronous (callers use run_sync for async handlers).
"""

from __future__ import annotations

import logging

from supabase import Client

logger = logging.getLogger(__name__)


class ImageRepository:
    """Encapsulates all DB and storage calls related to the images table."""

    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    # ------------------------------------------------------------------
    # images table — read
    # ------------------------------------------------------------------

    def get_by_id(self, image_id: str) -> dict | None:
        """Fetch a single image row by ID. Returns None if not found."""
        result = (
            self._sb.table("images")
            .select("*")
            .eq("id", image_id)
            .maybe_single()
            .execute()
        )
        return result.data or None

    def get_by_id_with_fields(self, image_id: str, fields: str) -> dict | None:
        """Fetch an image by ID selecting specific fields. Returns None if not found."""
        result = (
            self._sb.table("images")
            .select(fields)
            .eq("id", image_id)
            .maybe_single()
            .execute()
        )
        return result.data or None

    def get_by_id_single(self, image_id: str) -> dict:
        """Fetch a single image row using .single() (raises if not found)."""
        result = (
            self._sb.table("images")
            .select("storage_key, bucket")
            .eq("id", image_id)
            .single()
            .execute()
        )
        return result.data

    def get_by_ids(self, image_ids: list[str]) -> list[dict]:
        """Batch-fetch image rows by IDs."""
        result = (
            self._sb.table("images")
            .select("id, storage_key, bucket")
            .in_("id", image_ids)
            .execute()
        )
        return result.data or []

    def get_by_status(self, status: str, user_id: str) -> list[dict]:
        """Fetch images by status filtered by user_id."""
        result = (
            self._sb.table("images")
            .select("*")
            .eq("status", status)
            .eq("user_id", user_id)
            .execute()
        )
        return result.data or []

    # ------------------------------------------------------------------
    # images table — write
    # ------------------------------------------------------------------

    def create(self, image_data: dict) -> dict:
        """Insert a new image row. Returns the inserted row."""
        result = self._sb.table("images").insert(image_data).execute()
        return result.data[0] if result.data else {}

    # ------------------------------------------------------------------
    # Storage operations
    # ------------------------------------------------------------------

    def create_signed_url(self, bucket: str, key: str, expires_in: int) -> str:
        """Create a signed URL for a private storage object.

        Returns the signedURL string.  When SUPABASE_PUBLIC_URL is set (local
        dev), rewrites the host so mobile devices on the LAN can reach storage.
        """
        from app.config import settings

        result = self._sb.storage.from_(bucket).create_signed_url(key, expires_in)
        url = result["signedURL"]
        if settings.SUPABASE_PUBLIC_URL and settings.SUPABASE_URL:
            url = url.replace(settings.SUPABASE_URL, settings.SUPABASE_PUBLIC_URL, 1)
        return url

    def upload(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        """Upload bytes to a storage bucket."""
        self._sb.storage.from_(bucket).upload(
            path=key,
            file=data,
            file_options={"content-type": content_type},
        )
        logger.info("Uploaded %s/%s (%d bytes)", bucket, key, len(data))

    def update_file(
        self, bucket: str, key: str, data: bytes, content_type: str
    ) -> None:
        """Overwrite an existing file in storage."""
        self._sb.storage.from_(bucket).update(
            path=key,
            file=data,
            file_options={"content-type": content_type},
        )
        logger.info("Updated %s/%s (%d bytes)", bucket, key, len(data))

    def remove(self, bucket: str, keys: list[str]) -> None:
        """Remove one or more files from a storage bucket."""
        self._sb.storage.from_(bucket).remove(keys)
        logger.info("Removed %d file(s) from %s", len(keys), bucket)

    def download(self, bucket: str, key: str) -> bytes:
        """Download bytes from a storage bucket."""
        return self._sb.storage.from_(bucket).download(key)

    def create_signed_url_with_upsert(
        self,
        bucket: str,
        key: str,
        expires_in: int,
    ) -> str:
        """Create a signed URL; thin alias of create_signed_url for clarity."""
        return self.create_signed_url(bucket, key, expires_in)

    def upload_public(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str,
        upsert: bool = True,
    ) -> None:
        """Upload to a public bucket (supports upsert for overwrite)."""
        file_options: dict = {"content-type": content_type}
        if upsert:
            file_options["upsert"] = "true"
        self._sb.storage.from_(bucket).upload(
            path=key,
            file=data,
            file_options=file_options,
        )
        logger.info("Uploaded (public) %s/%s (%d bytes)", bucket, key, len(data))

    def build_avatar_signed_url(
        self, avatar_storage_key: str, expires_in: int
    ) -> str | None:
        """Generate a signed URL for an avatar in the private avatars bucket.

        Returns None if the signed URL request fails.
        """
        try:
            return self.create_signed_url("avatars", avatar_storage_key, expires_in)
        except Exception:
            logger.warning(
                "Failed to generate signed URL for avatar key: %s", avatar_storage_key
            )
            return None
