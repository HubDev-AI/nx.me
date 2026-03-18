"""Face analysis data models and error codes.

C-2 LOCKED: No attractiveness score or ranking in any model field.
ADR-1: Landmark vectors are ephemeral — never persisted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


# ---------------------------------------------------------------------------
# Face shape classification
# ---------------------------------------------------------------------------


class FaceShape(StrEnum):
    """Face shape categories — maps to analyses.face_shape CHECK constraint."""

    OVAL = "oval"
    ROUND = "round"
    SQUARE = "square"
    HEART = "heart"
    OBLONG = "oblong"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Suggestion:
    """A single improvement suggestion tied to face shape and proportions."""

    rank: int  # 1-5
    category: str  # e.g., "eyebrows", "hair", "skincare", "accessories", "grooming"
    suggestion_text: str  # actionable advice — no attractiveness language
    rationale: str  # ties suggestion to face shape and proportions


@dataclass(frozen=True)
class AnalysisResult:
    """Result of face analysis — only this is persisted (not landmarks)."""

    face_shape: FaceShape
    symmetry_score: float  # [0.0, 1.0]
    recommendations: list[Suggestion] = field(default_factory=list)  # exactly 5 items


# ---------------------------------------------------------------------------
# Error codes
# ---------------------------------------------------------------------------

FACE_NOT_DETECTED = "FACE_NOT_DETECTED"
MULTIPLE_FACES = "MULTIPLE_FACES"
FACE_OBSTRUCTED = "FACE_OBSTRUCTED"
IMAGE_TOO_BLURRY = "IMAGE_TOO_BLURRY"
