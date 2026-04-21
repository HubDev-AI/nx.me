"""Makeup analyzer — MST bin, undertone, region anchors, preset ranking.

Produces a ``MakeupAnalysis`` from a selfie URL. The heavy ML work is
isolated in ``face_parsing.get_region_anchors()`` so unit tests can stub it.

Public surface consumed by Unit 6 (POST /makeup/generate):
- ``analyze(image_url, user_id)`` — returns ``MakeupAnalysis`` or raises ``AnalysisError``
- ``analyzer_stale(analysis_row)`` — True when the DB row is >89 days old or biometric
  fields were purged

MST classification is approximated from the image's dominant skin-region RGB
mean (no dedicated ML model shipped in v1 — a dedicated model or fal classifier
can replace this later with no callers changing).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.generation.face_parsing import get_region_anchors
from app.generation.preset_registry import get_available_presets

logger = logging.getLogger(__name__)

_MST_THRESHOLDS = [
    (235, 1),
    (220, 2),
    (205, 3),
    (190, 4),
    (170, 5),
    (150, 6),
    (125, 7),
    (100, 8),
    (75, 9),
]


class AnalysisError(RuntimeError):
    """Raised when analysis cannot complete (e.g. no face detected)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class MakeupAnalysis:
    mst_bin: int
    undertone: str
    region_anchors: dict
    recommended_preset_ranking: list[str]
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


def _classify_mst(mean_rgb: tuple[float, float, float]) -> int:
    """Map mean skin-region RGB to Monk Skin Tone bin 1–10."""
    brightness = 0.299 * mean_rgb[0] + 0.587 * mean_rgb[1] + 0.114 * mean_rgb[2]
    for threshold, bin_val in _MST_THRESHOLDS:
        if brightness >= threshold:
            return bin_val
    return 10


def _classify_undertone(mean_rgb: tuple[float, float, float]) -> str:
    """Heuristic: warm = red > blue, cool = blue > red, else neutral."""
    r, _, b = mean_rgb
    diff = r - b
    if diff > 15:
        return "warm"
    if diff < -15:
        return "cool"
    return "neutral"


def _rank_presets(mst_bin: int, undertone: str) -> list[str]:
    """Order available presets by undertone-preset affinity."""
    presets = get_available_presets(mst_bin=mst_bin)

    _WARM_PREFERRED = {"bold_red", "soft_glam", "bridal"}
    _COOL_PREFERRED = {"smoky_eye", "dramatic_night"}

    def _score(preset_slug: str) -> int:
        if undertone == "warm" and preset_slug in _WARM_PREFERRED:
            return 0
        if undertone == "cool" and preset_slug in _COOL_PREFERRED:
            return 0
        if undertone == "neutral":
            return 1
        return 2

    ranked = sorted(presets, key=lambda p: (_score(p.slug), p.slug))
    return [p.slug for p in ranked]


def _mean_skin_rgb(image_url: str, skin_mask_bbox: tuple | None) -> tuple[float, float, float]:
    """Fetch image and compute mean RGB of the skin region (or full image if no mask)."""
    import io

    import numpy as np
    import requests
    from PIL import Image

    resp = requests.get(image_url, timeout=10)
    resp.raise_for_status()
    img = Image.open(io.BytesIO(resp.content)).convert("RGB")
    arr = np.array(img, dtype=float)

    if skin_mask_bbox is not None:
        x1, y1, x2, y2 = skin_mask_bbox
        region = arr[y1 : y2 + 1, x1 : x2 + 1]
        if region.size > 0:
            arr = region

    means = arr.reshape(-1, 3).mean(axis=0)
    return float(means[0]), float(means[1]), float(means[2])


def analyze(image_url: str, user_id: str) -> MakeupAnalysis:
    """Run the makeup analyzer on *image_url* and return a ``MakeupAnalysis``.

    Raises ``AnalysisError`` when no face is detected.
    All other exceptions propagate to the caller (Unit 6 handles them as
    non-retryable failures).
    """
    region_anchors = get_region_anchors(image_url)
    if region_anchors is None:
        raise AnalysisError("no_face")

    cheek_bbox = region_anchors.get("cheek")
    mean_rgb = _mean_skin_rgb(image_url, cheek_bbox)

    mst_bin = _classify_mst(mean_rgb)
    undertone = _classify_undertone(mean_rgb)
    ranking = _rank_presets(mst_bin, undertone)

    return MakeupAnalysis(
        mst_bin=mst_bin,
        undertone=undertone,
        region_anchors=region_anchors,
        recommended_preset_ranking=ranking,
    )


def analyzer_stale(analysis_row: dict) -> bool:
    """Return True when the DB analysis row should be refreshed.

    Staleness conditions (OR):
    - ``created_at`` older than 89 days
    - Any biometric field (mst_bin, undertone, region_anchors) is None/absent
      (post-purge state after ``nullify_biometric_fields`` ran)
    """
    created_at_raw = analysis_row.get("created_at")
    if created_at_raw is None:
        return True

    if isinstance(created_at_raw, str):
        created_at = datetime.fromisoformat(created_at_raw)
    else:
        created_at = created_at_raw

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    age_limit = datetime.now(tz=timezone.utc) - timedelta(days=89)
    if created_at < age_limit:
        return True

    for field_name in ("mst_bin", "undertone", "region_anchors"):
        if analysis_row.get(field_name) is None:
            return True

    return False
