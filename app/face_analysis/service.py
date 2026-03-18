"""Face analysis service — orchestrates the full analysis pipeline.

Interface Contract (Story 3-2):
  FaceAnalysisService.analyze(image_storage_key: str) -> AnalysisResult

Pipeline steps:
  1. Fetch image bytes from Supabase Storage
  2. Extract landmarks via MediaPipe FaceMesh (ephemeral — ADR-1)
  3. Classify face shape from landmark ratios
  4. Score bilateral symmetry
  5. Generate recommendations
  6. Discard landmarks, return AnalysisResult
"""
from __future__ import annotations

import asyncio
import logging

from supabase import Client

from app.config import settings
from app.face_analysis.classifier import FaceShapeClassifier
from app.face_analysis.landmark_extractor import (
    FaceAnalysisPort,
    LandmarkExtractor,
    MockFaceAnalysisAdapter,
)
from fastapi import HTTPException, status

from app.face_analysis.models import AnalysisResult
from app.face_analysis.recommendation import RecommendationEngine
from app.face_analysis.symmetry_scorer import SymmetryScorer
from app.repositories.image_repo import ImageRepository

logger = logging.getLogger(__name__)


def _get_face_analysis_adapter() -> FaceAnalysisPort:
    """Resolve face analysis adapter from config (lazy import)."""
    if settings.ADAPTER__FACE_ANALYSIS_ADAPTER == "mediapipe":
        # Return a MediaPipeAdapter that wraps the full pipeline
        return _MediaPipeAdapter()
    return MockFaceAnalysisAdapter()


class _MediaPipeAdapter:
    """Real face analysis using MediaPipe FaceMesh + classifier + scorer + recommender."""

    def __init__(self) -> None:
        self._extractor = LandmarkExtractor()
        self._classifier = FaceShapeClassifier()
        self._scorer = SymmetryScorer()
        self._recommender = RecommendationEngine()

    async def analyze(self, image_bytes: bytes) -> AnalysisResult:
        """Run the full analysis pipeline on image bytes.

        MediaPipe FaceMesh is CPU-bound and not thread-safe with shared
        instances. LandmarkExtractor creates a fresh FaceMesh per call.
        We run the sync extraction in an executor to avoid blocking the
        event loop.
        """
        loop = asyncio.get_running_loop()

        # CPU-bound: extract landmarks in executor
        landmarks = await loop.run_in_executor(
            None, self._extractor.extract, image_bytes
        )

        # These are fast in-memory computations — no executor needed
        face_shape = self._classifier.classify(landmarks.points)
        symmetry_score = self._scorer.score(landmarks.points)
        recommendations = self._recommender.recommend(face_shape)

        # Landmarks are discarded here (ADR-1) — only derived values returned
        logger.info("Face analysis complete: shape=%s, symmetry=%.3f", face_shape, symmetry_score)

        return AnalysisResult(
            face_shape=face_shape,
            symmetry_score=round(symmetry_score, 4),
            recommendations=recommendations,
        )


class FaceAnalysisService:
    """Orchestrates face analysis from a storage key.

    Called by POST /analyses handler (story 3-3).
    Fetches the image from Supabase Storage, delegates to the configured
    face analysis adapter.
    """

    def __init__(self, supabase: Client) -> None:
        self._image_repo = ImageRepository(supabase)
        self._adapter = _get_face_analysis_adapter()

    async def analyze(self, image_storage_key: str) -> AnalysisResult:
        """Analyze a face image stored in the raw-selfies bucket.

        Args:
            image_storage_key: Storage key in the 'raw-selfies' bucket.

        Returns:
            AnalysisResult with face_shape, symmetry_score, and 5 recommendations.

        Raises:
            HTTPException 422: FACE_NOT_DETECTED, MULTIPLE_FACES.
        """
        # Fetch image bytes from Supabase Storage
        try:
            image_bytes = self._image_repo.download("raw-selfies", image_storage_key)
        except Exception as exc:
            logger.error("Failed to download image %s: %s", image_storage_key, exc)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": {
                        "code": "IMAGE_NOT_FOUND",
                        "message": "Could not retrieve image for analysis.",
                        "retry_eligible": False,
                    }
                },
            ) from exc

        if not image_bytes:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": {
                        "code": "IMAGE_NOT_FOUND",
                        "message": "Image file is empty or missing.",
                        "retry_eligible": False,
                    }
                },
            )

        return await self._adapter.analyze(image_bytes)
