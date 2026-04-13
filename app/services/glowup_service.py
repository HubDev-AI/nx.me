"""Glowup service — wraps FaceAnalysisService + GlowupAnalysisRepository.

Handles the POST /uploads/{id}/glowup/analyze flow:
  1. Verify upload exists and belongs to the user.
  2. Check face_mod_consent_at on the user row — 428 if NULL.
  3. Check face_detected on the upload row — 422 if False.
  4. Run FaceAnalysisService.analyze() on the upload's image.
  5. Write a glowup_analyses row (upsert: one per upload).
  6. Return {glowup_analysis_id, face_shape, symmetry_score, recommendations}.

This service class keeps the route handler thin.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from supabase import Client

from app.db.async_helpers import run_sync
from app.face_analysis.service import FaceAnalysisService
from app.repositories.glowup_analysis_repo import GlowupAnalysisRepository
from app.repositories.upload_repo import UploadRepository

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GlowupAnalysisResult:
    """Return type for GlowupService.create_analysis()."""

    glowup_analysis_id: UUID
    face_shape: str
    symmetry_score: float
    recommendations: list[dict]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class GlowupService:
    """Orchestrates face analysis + glowup_analyses write for POST /glowup/analyze."""

    def __init__(self, supabase: Client) -> None:
        self._supabase = supabase
        self._upload_repo = UploadRepository(supabase)
        self._analysis_repo = GlowupAnalysisRepository(supabase)

    async def create_analysis(
        self,
        upload_id: str,
        user_id: str,
    ) -> GlowupAnalysisResult:
        """Run face analysis for the given upload and persist the result.

        Args:
            upload_id: UUID string of the uploads row.
            user_id: Authenticated user's UUID string.

        Returns:
            GlowupAnalysisResult with glowup_analysis_id, face_shape,
            symmetry_score, and recommendations.

        Raises:
            HTTPException 404: Upload not found or not owned by user.
            HTTPException 422: Face not detected in the upload.
            HTTPException 428: User has not granted face-mod consent.
        """
        # Step 1: Verify the upload exists and belongs to the user.
        upload = await run_sync(
            self._upload_repo.get_by_id_for_owner_check, upload_id, user_id
        )
        if not upload:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "UPLOAD_NOT_FOUND",
                        "message": "Upload not found.",
                    }
                },
            )

        # Step 2: Check face_mod_consent_at — 428 if the user has not consented.
        consent_row = await run_sync(self._get_consent_row, user_id)
        if not consent_row or not consent_row.get("face_mod_consent_at"):
            raise HTTPException(
                status_code=status.HTTP_428_PRECONDITION_REQUIRED,
                detail={
                    "error": {
                        "code": "FACE_MOD_CONSENT_REQUIRED",
                        "message": (
                            "You must grant consent for AI face modification "
                            "before analyzing. Call POST /users/me/face-mod-consent first."
                        ),
                    }
                },
            )

        # Step 3: Check that a face was detected during upload.
        if not upload.get("face_detected"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": {
                        "code": "FACE_NOT_DETECTED",
                        "message": "No face detected in the uploaded image. Please try a different photo.",
                    }
                },
            )

        # Step 4: Idempotency — return existing analysis if one already exists.
        existing = await run_sync(self._analysis_repo.get_by_upload_id, upload_id)
        if existing:
            recs = existing.get("recommendations") or []
            logger.info(
                "Returning cached glowup analysis %s for upload %s",
                existing["id"],
                upload_id,
            )
            return GlowupAnalysisResult(
                glowup_analysis_id=UUID(existing["id"]),
                face_shape=existing["face_shape"] or "",
                symmetry_score=float(existing["symmetry_score"] or 0.0),
                recommendations=recs,
            )

        # Step 5: Run face analysis on the upload's image.
        face_svc = FaceAnalysisService(self._supabase)
        result = await face_svc.analyze(upload["image_url"])

        # Step 6: Persist the glowup_analyses row.
        recs_json = [
            {
                "rank": s.rank,
                "category": s.category,
                "suggestion_text": s.suggestion_text,
                "rationale": s.rationale,
            }
            for s in result.recommendations
        ]
        analysis_id = uuid4()
        now_utc = datetime.now(tz=timezone.utc).isoformat()

        await run_sync(
            self._analysis_repo.insert,
            {
                "id": str(analysis_id),
                "upload_id": upload_id,
                "face_shape": result.face_shape.value,
                "symmetry_score": result.symmetry_score,
                "recommendations": recs_json,
                "created_at": now_utc,
            },
        )

        logger.info(
            "Glowup analysis %s created for upload %s (shape=%s)",
            analysis_id,
            upload_id,
            result.face_shape,
        )

        return GlowupAnalysisResult(
            glowup_analysis_id=analysis_id,
            face_shape=result.face_shape.value,
            symmetry_score=result.symmetry_score,
            recommendations=recs_json,
        )

    def _get_consent_row(self, user_id: str) -> dict | None:
        """Fetch face_mod_consent_at for the given user."""
        result = (
            self._supabase.table("users")
            .select("face_mod_consent_at")
            .eq("id", user_id)
            .maybe_single()
            .execute()
        )
        return result.data if result else None
