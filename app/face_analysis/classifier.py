"""Face shape classification from landmark measurements.

AC-1: Returns face_shape from {oval, round, square, heart, oblong}.

Classification uses jaw/forehead/cheekbone width ratios derived from
MediaPipe FaceMesh landmark coordinates.
"""

from __future__ import annotations

import logging
import math

import numpy as np

from app.face_analysis.models import FaceShape

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Key landmark indices (MediaPipe FaceMesh 468-point model)
# ---------------------------------------------------------------------------

_FOREHEAD_TOP = 10
_CHIN = 152
_LEFT_TEMPLE = 70
_RIGHT_TEMPLE = 300
_LEFT_CHEEK = 234
_RIGHT_CHEEK = 454
_LEFT_JAW = 172
_RIGHT_JAW = 397


def _distance(points: np.ndarray, i: int, j: int) -> float:
    """Euclidean distance between two 3D landmark points."""
    return float(np.linalg.norm(points[i] - points[j]))


def _angle_at_chin(points: np.ndarray) -> float:
    """Compute jaw angle at chin (in degrees).

    Angle formed by left_jaw → chin → right_jaw.
    Wider angle = more angular jaw (square face indicator).
    """
    v1 = points[_LEFT_JAW] - points[_CHIN]
    v2 = points[_RIGHT_JAW] - points[_CHIN]

    cos_angle = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-8)
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    return math.degrees(math.acos(float(cos_angle)))


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


class FaceShapeClassifier:
    """Classify face shape from 468 3D landmark coordinates.

    Classification rules (applied in order, first match wins):
    1. Oblong:  face_length / cheekbone_width > 1.3
    2. Round:   face_length / cheekbone_width < 1.1 AND jaw/cheek ratio > 0.85
    3. Square:  face_length / cheekbone_width < 1.1 AND jaw_angle > 140°
    4. Heart:   forehead_width / jaw_width > 1.2
    5. Oval:    default
    """

    def classify(self, points: np.ndarray) -> FaceShape:
        """Classify face shape from landmark points.

        Args:
            points: numpy array of shape (468, 3) — 3D landmark coordinates.

        Returns:
            FaceShape enum value.
        """
        face_length = _distance(points, _FOREHEAD_TOP, _CHIN)
        forehead_width = _distance(points, _LEFT_TEMPLE, _RIGHT_TEMPLE)
        cheekbone_width = _distance(points, _LEFT_CHEEK, _RIGHT_CHEEK)
        jaw_width = _distance(points, _LEFT_JAW, _RIGHT_JAW)
        jaw_angle = _angle_at_chin(points)

        # Avoid division by zero
        if cheekbone_width < 1e-8 or jaw_width < 1e-8:
            logger.warning("Degenerate face measurements — defaulting to oval")
            return FaceShape.OVAL

        length_cheek_ratio = face_length / cheekbone_width
        jaw_cheek_ratio = jaw_width / cheekbone_width
        forehead_jaw_ratio = forehead_width / jaw_width

        # Rules applied in order, first match wins.
        # Note: faces with length/cheek ratio in [1.1, 1.3] and forehead/jaw <= 1.2
        # fall through to Oval (default). This is intentional — moderately elongated
        # faces without other distinguishing features are classified as oval.

        # Rule 1: Oblong
        if length_cheek_ratio > 1.3:
            return FaceShape.OBLONG

        # Rule 2: Round
        if length_cheek_ratio < 1.1 and jaw_cheek_ratio > 0.85:
            return FaceShape.ROUND

        # Rule 3: Square
        if length_cheek_ratio < 1.1 and jaw_angle > 140:
            return FaceShape.SQUARE

        # Rule 4: Heart
        if forehead_jaw_ratio > 1.2:
            return FaceShape.HEART

        # Rule 5: Default — Oval
        return FaceShape.OVAL
