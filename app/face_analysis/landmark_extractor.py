"""Landmark extraction — MediaPipe FaceLandmarker wrapper and mock adapter.

AC-1: Extract 468 3D facial landmarks from a single face.
AC-2: preload_model() called during FastAPI lifespan startup.
AC-4: Landmark vectors are ephemeral — never written to DB (ADR-1).

MediaPipe Tasks API (0.10.x+): FaceLandmarker replaces the removed mp.solutions
legacy API. Each request creates a new FaceLandmarker instance; model weights
are cached on disk after the first call to preload_model().
"""
from __future__ import annotations

import io
import logging
import pathlib
import urllib.request
from dataclasses import dataclass
from typing import Protocol

import numpy as np
import PIL.Image
from fastapi import HTTPException, status

from app.face_analysis.models import (
    FACE_ERROR_NOT_DETECTED,
    AnalysisResult,
    FaceShape,
    Suggestion,
)

logger = logging.getLogger(__name__)

# Module-level flag — set to True after preload_model() succeeds.
_model_preloaded: bool = False

# Model file — cached locally to avoid re-downloading on every restart.
_MODEL_CACHE_DIR = pathlib.Path.home() / ".cache" / "mediapipe"
_MODEL_PATH = _MODEL_CACHE_DIR / "face_landmarker.task"
_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
)


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
# Internal helpers
# ---------------------------------------------------------------------------


def _ensure_model() -> str:
    """Download FaceLandmarker model to disk if not already cached. Returns path."""
    if not _MODEL_PATH.exists():
        _MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("Downloading MediaPipe FaceLandmarker model to %s ...", _MODEL_PATH)
        urllib.request.urlretrieve(_MODEL_URL, _MODEL_PATH)
        logger.info(
            "MediaPipe FaceLandmarker model downloaded (%d bytes)",
            _MODEL_PATH.stat().st_size,
        )
    return str(_MODEL_PATH)


def _make_landmarker_options(model_path: str):  # type: ignore[return]
    """Build FaceLandmarkerOptions for IMAGE mode."""
    import mediapipe as mp

    return mp.tasks.vision.FaceLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=model_path),
        running_mode=mp.tasks.vision.RunningMode.IMAGE,
        num_faces=2,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )


# ---------------------------------------------------------------------------
# Preload (AC-2)
# ---------------------------------------------------------------------------


def preload_model() -> None:
    """Pre-load MediaPipe FaceLandmarker model into memory.

    Called once during FastAPI lifespan startup. Downloads the model file on
    first run, then creates and immediately closes a FaceLandmarker instance
    to trigger MediaPipe's internal weight caching. Subsequent instances reuse
    those cached weights.
    """
    global _model_preloaded

    model_path = _ensure_model()

    import mediapipe as mp

    options = _make_landmarker_options(model_path)
    with mp.tasks.vision.FaceLandmarker.create_from_options(options):
        pass

    _model_preloaded = True
    logger.info("MediaPipe FaceLandmarker model pre-loaded and cached")


def is_model_preloaded() -> bool:
    """Check if the MediaPipe model has been preloaded."""
    return _model_preloaded


# ---------------------------------------------------------------------------
# Landmark extraction
# ---------------------------------------------------------------------------


class LandmarkExtractor:
    """Extract 468 3D facial landmarks using MediaPipe FaceLandmarker.

    Creates a new FaceLandmarker instance per call (thread-safe). Model
    weights are pre-loaded via preload_model().
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
                        "code": FACE_ERROR_NOT_DETECTED,
                        "message": "Could not read the image. The file may be corrupted.",
                        "details": {
                            "zone": "whole",
                            "reason": "Image file is corrupted or unreadable",
                        },
                    }
                },
            ) from exc

        model_path = _ensure_model()
        options = _make_landmarker_options(model_path)

        with mp.tasks.vision.FaceLandmarker.create_from_options(options) as landmarker:
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_image)
            result = landmarker.detect(mp_image)

        if not result.face_landmarks:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": {
                        "code": FACE_ERROR_NOT_DETECTED,
                        "message": "No face was detected. Please upload a clear, front-facing selfie.",
                        "details": {
                            "zone": "whole",
                            "reason": "No face found in image",
                        },
                    }
                },
            )

        if len(result.face_landmarks) > 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": {
                        "code": FACE_ERROR_NOT_DETECTED,
                        "message": "Multiple faces detected. Please upload a selfie with only one face.",
                        "details": {
                            "zone": "whole",
                            "reason": "Multiple faces detected in frame",
                        },
                    }
                },
            )

        face_landmarks = result.face_landmarks[0]
        # Tasks API returns 478 landmarks (468 face + 10 iris refinement).
        # Slice to first 468 to match downstream classifier/scorer expectations.
        points = np.array(
            [[lm.x, lm.y, lm.z] for lm in face_landmarks[:468]],
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
