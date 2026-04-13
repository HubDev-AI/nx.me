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
# Error codes — must match mobile parseApiError FACE_ERROR_CODES taxonomy
# ---------------------------------------------------------------------------

# Legacy uppercase constants — kept for backwards-compat references only.
# Prefer the FACE_* constants below for all new code.
FACE_NOT_DETECTED = "face_not_detected"
MULTIPLE_FACES = "face_not_detected"  # treated as "no single face" on mobile
FACE_OBSTRUCTED = "face_obscured"
IMAGE_TOO_BLURRY = "face_not_detected"

# Canonical face-error codes (mobile taxonomy)
FACE_ERROR_NOT_DETECTED = "face_not_detected"
FACE_ERROR_TOO_CLOSE = "face_too_close"
FACE_ERROR_TOO_FAR = "face_too_far"
FACE_ERROR_LIGHTING_TOO_DARK = "lighting_too_dark"
FACE_ERROR_LIGHTING_TOO_BRIGHT = "lighting_too_bright"
FACE_ERROR_OBSCURED = "face_obscured"


@dataclass(frozen=True)
class FaceErrorDetails:
    """Structured details for a face-analysis error.

    zone: which part of the frame/face is problematic.
    reason: short human-readable description, e.g. "Face occupies >80% of frame".
    """

    zone: str  # center | top | bottom | left | right | whole
    reason: str
