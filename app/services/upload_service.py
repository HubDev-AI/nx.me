"""Upload service — wraps ImagePipeline + UploadRepository.

Handles the POST /uploads flow:
  1. Run ImagePipeline.process() (NSFW gate, metadata strip, storage write).
  2. Run face detection to set face_detected on the upload row.
  3. Write an uploads row.
  4. Return {upload_id, face_detected}.

This service class keeps the route handler thin.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from supabase import Client

from app.face_analysis.service import FaceAnalysisService
from app.image_pipeline.pipeline import ImagePipeline
from app.repositories.upload_repo import UploadRepository

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UploadResult:
    """Return type for UploadService.create_upload()."""

    upload_id: UUID
    face_detected: bool
    image_url: str


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class UploadService:
    """Orchestrates image pipeline + uploads table write for POST /uploads."""

    def __init__(self, supabase: Client) -> None:
        self._supabase = supabase
        self._upload_repo = UploadRepository(supabase)

    async def create_upload(
        self,
        file_bytes: bytes,
        content_type: str,
        user_id: str,
    ) -> UploadResult:
        """Run the image pipeline and create an uploads row.

        Args:
            file_bytes: Raw uploaded image bytes.
            content_type: MIME type from the upload.
            user_id: Authenticated user's UUID string.

        Returns:
            UploadResult with upload_id, face_detected, and image_url.

        Raises:
            HTTPException 422: IMAGE_FORMAT_REJECTED, IMAGE_TOO_LARGE, IMAGE_QUARANTINED.
        """
        # Step 1: Image pipeline — validates, NSFW-screens, strips metadata, stores.
        # Raises HTTPException 422 on format/size/quarantine failures.
        pipeline = ImagePipeline(self._supabase)
        processed = await pipeline.process(file_bytes, content_type, user_id)

        # Step 2: Detect whether a face is present (non-blocking — failure = face_detected=False).
        # We attempt a lightweight analysis and record whether a face was found.
        # Full analysis (landmarks + recommendations) happens later in POST /glowup/analyze.
        face_detected = False
        try:
            face_svc = FaceAnalysisService(self._supabase)
            await face_svc.analyze(processed.storage_key)
            face_detected = True
        except Exception:
            # No face detected or analysis failed — acceptable, record False.
            face_detected = False

        # Step 3: Derive the public image URL (storage key → public URL pattern).
        # The raw-selfies bucket is private — store the storage_key so signed URLs
        # can be generated on demand. We store storage_key as image_url to keep
        # things simple; the route layer signs it when needed.
        image_url = processed.storage_key or ""

        # Step 4: Write uploads row.
        upload_id = uuid4()
        now_utc = datetime.now(tz=timezone.utc).isoformat()
        nsfw_label = "cleared"  # Pipeline already raised if quarantined

        self._upload_repo.insert(
            {
                "id": str(upload_id),
                "user_id": user_id,
                "image_url": image_url,
                "nsfw_result": nsfw_label,
                "face_detected": face_detected,
                "last_accessed_at": now_utc,
                "created_at": now_utc,
            }
        )

        logger.info(
            "Upload %s created for user %s (face_detected=%s)",
            upload_id,
            user_id,
            face_detected,
        )

        return UploadResult(
            upload_id=upload_id,
            face_detected=face_detected,
            image_url=image_url,
        )
