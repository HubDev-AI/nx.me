"""Image processing pipeline — orchestrates validation, NSFW screening,
metadata stripping, and storage.

Interface Contract (Story 3-1):
  ImagePipeline.process(file_bytes, content_type, user_id) -> ProcessedImage

Pipeline steps (synchronous, every upload):
  1. MagicBytesValidator — reject unsupported formats
  2. DimensionValidator — reject oversized files/dimensions
  3. NSFWScreener — quarantine explicit content
  4. MetadataStripper — remove all EXIF/IPTC/XMP
  5. StorageAdapter — write clean bytes to raw-selfies bucket
  6. Write images row to database
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from supabase import Client

from app.config import settings
from app.image_pipeline.metadata_stripper import MetadataStripper
from app.image_pipeline.models import IMAGE_QUARANTINED, ProcessedImage
from app.image_pipeline.nsfw_screener import NSFWScreenerPort
from app.image_pipeline.storage import StoragePort
from app.image_pipeline.validators import DimensionValidator, MagicBytesValidator
from app.repositories.image_repo import ImageRepository

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# File extension mapping
_CONTENT_TYPE_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/heif": "jpg",  # re-encoded as JPEG
    "image/heic": "jpg",
}


def _get_nsfw_screener() -> NSFWScreenerPort:
    """Resolve NSFW screener adapter from config (lazy import)."""
    if settings.ADAPTER__NSFW_ADAPTER == "rekognition":
        try:
            from app.image_pipeline.nsfw_screener import RekognitionAdapter

            return RekognitionAdapter()
        except ImportError:
            logger.warning(
                "Rekognition adapter not available, falling back to mock NSFW screener. "
                "This is expected in development but NOT in production."
            )
    from app.image_pipeline.nsfw_screener import MockNSFWAdapter

    return MockNSFWAdapter()


def _get_storage_adapter(image_repo: ImageRepository) -> StoragePort:
    """Resolve storage adapter from config (lazy import)."""
    if settings.ADAPTER__STORAGE_ADAPTER == "supabase":
        from app.image_pipeline.storage import SupabaseStorageAdapter

        return SupabaseStorageAdapter(image_repo)
    from app.image_pipeline.storage import LocalStorageAdapter

    return LocalStorageAdapter()


class ImagePipeline:
    """Orchestrates the full image processing pipeline."""

    BUCKET = "raw-selfies"

    def __init__(self, supabase: Client) -> None:
        self._image_repo = ImageRepository(supabase)
        self._magic_validator = MagicBytesValidator()
        self._dimension_validator = DimensionValidator()
        self._nsfw_screener = _get_nsfw_screener()
        self._metadata_stripper = MetadataStripper()
        self._storage = _get_storage_adapter(self._image_repo)

    async def process(
        self,
        file_bytes: bytes,
        content_type: str,
        user_id: str,
    ) -> ProcessedImage:
        """Run the full image processing pipeline.

        Args:
            file_bytes: Raw uploaded image bytes.
            content_type: MIME type from the upload.
            user_id: Authenticated user's UUID string.

        Returns:
            ProcessedImage with storage_key, image_id, and status.

        Raises:
            HTTPException 422: IMAGE_FORMAT_REJECTED, IMAGE_TOO_LARGE, or IMAGE_QUARANTINED.
        """
        image_id = uuid4()
        now_utc = datetime.now(tz=timezone.utc).isoformat()

        # Step 1: Magic bytes validation (AC-1)
        # Step 2: Size and dimension validation (AC-2)
        try:
            self._magic_validator.validate(file_bytes)
            self._dimension_validator.validate(file_bytes)
        except (ValueError, TypeError, OSError) as exc:
            logger.warning("Image validation failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Image validation failed. Please upload a valid JPEG or PNG image.",
            ) from exc

        # Step 3: NSFW screening (AC-3)
        nsfw_result = await self._nsfw_screener.screen(file_bytes)

        if nsfw_result.is_explicit:
            # Write quarantined images row — no file written to storage
            try:
                self._image_repo.create(
                    {
                        "id": str(image_id),
                        "user_id": user_id,
                        "storage_key": None,
                        "bucket": None,
                        "image_type": "selfie",
                        "status": "quarantined",
                        "screened_at": now_utc,
                    }
                )
            except Exception as exc:
                # DB failure must not mask the quarantine decision — fail closed
                logger.error(
                    "Failed to insert quarantined images row for user %s: %s",
                    user_id,
                    exc,
                )
                raise  # Fail closed — do not allow unrecorded quarantined images

            logger.info(
                "Image quarantined for user %s (confidence=%.1f%%, labels=%s)",
                user_id,
                nsfw_result.confidence,
                nsfw_result.labels,
            )

            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": {
                        "code": IMAGE_QUARANTINED,
                        "message": "Image did not pass content screening.",
                        "retry_eligible": True,
                    }
                },
            )

        # Step 4: Strip metadata (AC-4)
        clean_bytes = self._metadata_stripper.strip(file_bytes, content_type)

        # Step 5: Write to storage
        ext = _CONTENT_TYPE_EXT.get(content_type, "jpg")
        storage_key = f"{user_id}/{image_id}.{ext}"

        # Determine content type after re-encode (HEIF → JPEG)
        store_content_type = content_type
        if content_type in ("image/heif", "image/heic"):
            store_content_type = "image/jpeg"

        await self._storage.upload(
            self.BUCKET, storage_key, clean_bytes, store_content_type
        )

        # Step 6: Write images row — delete uploaded file on DB failure
        try:
            self._image_repo.create(
                {
                    "id": str(image_id),
                    "user_id": user_id,
                    "storage_key": storage_key,
                    "bucket": self.BUCKET,
                    "image_type": "selfie",
                    "status": "cleared",
                    "screened_at": now_utc,
                }
            )
        except Exception as exc:
            logger.error(
                "images INSERT failed for %s — deleting orphaned file %s: %s",
                user_id,
                storage_key,
                exc,
            )
            try:
                self._image_repo.remove(self.BUCKET, [storage_key])
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Failed to delete orphaned file %s/%s", self.BUCKET, storage_key
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Image processing failed.",
            ) from exc

        logger.info("Image processed for user %s: %s (cleared)", user_id, storage_key)

        return ProcessedImage(
            storage_key=storage_key,
            image_id=image_id,
            status="cleared",
        )
