"""Landmark extraction — MediaPipe FaceMesh wrapper and mock adapter.

AC-1: Extract 468 3D facial landmarks from a single face.
AC-2: preload_model() called during FastAPI lifespan startup.
AC-4: Landmark vectors are ephemeral — never written to DB (ADR-1).

MediaPipe FaceMesh is NOT thread-safe with shared instances.
Each request creates a new FaceMesh session reusing pre-loaded weights.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Protocol

import numpy as np
import PIL.Image
from fastapi import HTTPException, status

from app.face_analysis.models import (
    FACE_NOT_DETECTED,
    MULTIPLE_FACES,
    AnalysisResult,
    FaceShape,
    Suggestion,
)

logger = logging.getLogger(__name__)

# Module-level flag — set to True after preload_model() succeeds.
_model_preloaded: bool = False


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Landmarks:
    """468 3D facial landmarks — ephemeral, never persisted (ADR-1)."""

    points: np.ndarray  # shape (468, 3) — x, y, z normalized coordinates


class FaceAnalysisPort(Protocol):
    """Interface for face analysis adapters."""

    async def analyze(self, image_bytes: bytes) -> AnalysisResult:
        ...


# ---------------------------------------------------------------------------
# Preload (AC-2)
# ---------------------------------------------------------------------------


def preload_model() -> None:
    """Pre-load MediaPipe FaceMesh model into memory.

    Called once during FastAPI lifespan startup. Blocks until model weights
    are loaded. After this, creating new FaceMesh instances per request is
    lightweight (reuses cached model weights).
    """
    global _model_preloaded
    import mediapipe as mp

    # Creating and immediately closing a FaceMesh instance triggers model download
    # and caching. Subsequent instances reuse the cached weights.
    with mp.solutions.face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=2,
        refine_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    ) as _:
        pass

    _model_preloaded = True
    logger.info("MediaPipe FaceMesh model pre-loaded and cached")


def is_model_preloaded() -> bool:
    """Check if the MediaPipe model has been preloaded."""
    return _model_preloaded


# ---------------------------------------------------------------------------
# Landmark extraction
# ---------------------------------------------------------------------------


class LandmarkExtractor:
    """Extract 468 3D facial landmarks using MediaPipe FaceMesh.

    Creates a new FaceMesh instance per call (thread-safe).
    Model weights are pre-loaded via preload_model().
    """

    def extract(self, image_bytes: bytes) -> Landmarks:
        """Extract landmarks from a face image.

        Args:
            image_bytes: Raw image bytes (JPEG/PNG, already validated).

        Returns:
            Landmarks with 468 3D points.

        Raises:
            HTTPException 422: FACE_NOT_DETECTED or MULTIPLE_FACES.
        """
        import mediapipe as mp

        # Load image as RGB numpy array
        try:
            with PIL.Image.open(io.BytesIO(image_bytes)) as img:
                rgb_image = np.array(img.convert("RGB"))
        except Exception as exc:
            logger.warning("Failed to open image for landmark extraction: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": {
                        "code": FACE_NOT_DETECTED,
                        "message": "Could not read the image. The file may be corrupted.",
                        "retry_eligible": True,
                    }
                },
            ) from exc

        # Process with a fresh FaceMesh instance (reuses pre-loaded weights)
        with mp.solutions.face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=2,  # detect up to 2 to enforce single-face check
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        ) as face_mesh:
            results = face_mesh.process(rgb_image)

        if not results.multi_face_landmarks:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": {
                        "code": FACE_NOT_DETECTED,
                        "message": "No face was detected. Please upload a clear, front-facing selfie.",
                        "retry_eligible": True,
                    }
                },
            )

        if len(results.multi_face_landmarks) > 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": {
                        "code": MULTIPLE_FACES,
                        "message": "Multiple faces detected. Please upload a selfie with only one face.",
                        "retry_eligible": True,
                    }
                },
            )

        face_landmarks = results.multi_face_landmarks[0]
        points = np.array(
            [[lm.x, lm.y, lm.z] for lm in face_landmarks.landmark],
            dtype=np.float64,
        )

        return Landmarks(points=points)


# ---------------------------------------------------------------------------
# Mock adapter
# ---------------------------------------------------------------------------


class MockFaceAnalysisAdapter:
    """Mock adapter — returns deterministic results for local dev."""

    async def analyze(self, image_bytes: bytes) -> AnalysisResult:  # noqa: ARG002
        return AnalysisResult(
            face_shape=FaceShape.OVAL,
            symmetry_score=0.85,
            recommendations=[
                Suggestion(
                    rank=1, category="hair",
                    suggestion_text="Try layers that add volume at the crown to complement your oval face shape.",
                    rationale="Oval faces are well-balanced; layers enhance natural proportions.",
                ),
                Suggestion(
                    rank=2, category="eyebrows",
                    suggestion_text="A soft arch following your natural brow bone suits your face proportions.",
                    rationale="Your forehead-to-jaw ratio indicates a balanced oval structure.",
                ),
                Suggestion(
                    rank=3, category="accessories",
                    suggestion_text="Rectangular or geometric frames will complement your rounded jawline.",
                    rationale="Angular frames create visual contrast with oval face curves.",
                ),
                Suggestion(
                    rank=4, category="skincare",
                    suggestion_text=(
                        "Highlight your cheekbones with a subtle contour "
                        "to enhance your natural structure."
                    ),
                    rationale="Your cheekbone width is proportional to your face length.",
                ),
                Suggestion(
                    rank=5, category="grooming",
                    suggestion_text="Keep facial hair trimmed close to maintain your face shape definition.",
                    rationale="Your jaw-to-forehead ratio is well-balanced for a clean look.",
                ),
            ],
        )
