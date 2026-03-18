"""Symmetry scoring from bilateral landmark pair distances.

AC-1: Returns symmetry_score in [0.0, 1.0].
Score = mean of bilateral pair distance ratios (min/max per pair).
Perfect symmetry = 1.0, maximum asymmetry = 0.0.
"""
from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
# Bilateral landmark pairs (left index, right index)
# Key mirrored pairs from MediaPipe FaceMesh 468-point model.
# ---------------------------------------------------------------------------

_BILATERAL_PAIRS: list[tuple[int, int]] = [
    # Eye corners
    (33, 263),
    (133, 362),
    # Cheekbones
    (234, 454),
    # Mouth corners
    (61, 291),
    # Eyebrow ends
    (70, 300),
    # Jaw corners
    (172, 397),
    # Inner eye corners
    (173, 398),
    # Nose sides
    (49, 279),
    # Lower jaw
    (136, 365),
    # Upper lip
    (37, 267),
]

# Midline reference landmark (nose tip)
_MIDLINE_REF = 1


class SymmetryScorer:
    """Compute facial symmetry from bilateral landmark pair distances.

    Measures how symmetric the face is by comparing distances from
    the midline to mirrored landmark pairs on left and right sides.
    """

    def score(self, points: np.ndarray) -> float:
        """Compute symmetry score from landmark points.

        Args:
            points: numpy array of shape (468, 3) — 3D landmark coordinates.

        Returns:
            Float in [0.0, 1.0]. 1.0 = perfect symmetry.
        """
        midline = points[_MIDLINE_REF]

        ratios: list[float] = []
        for left_idx, right_idx in _BILATERAL_PAIRS:
            left_dist = float(np.linalg.norm(points[left_idx] - midline))
            right_dist = float(np.linalg.norm(points[right_idx] - midline))

            # Ratio of smaller to larger distance — 1.0 = perfectly symmetric
            max_dist = max(left_dist, right_dist)
            if max_dist < 1e-8:
                ratios.append(1.0)
            else:
                ratios.append(min(left_dist, right_dist) / max_dist)

        if not ratios:
            return 1.0

        # Average ratio — already in [0.0, 1.0]
        symmetry = float(np.mean(ratios))

        # Clamp to valid range
        return max(0.0, min(1.0, symmetry))
