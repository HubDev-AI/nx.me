"""Face region parser — extracts per-region bounding boxes for makeup analysis.

Wraps the ``jonathandinu/face-parsing`` model (semantic segmentation) to
produce lip, eye, and cheek anchor bboxes used by the makeup analyzer.

Design:
- Model is lazy-loaded on first call and cached as a module-level singleton.
- All heavy imports (torch, transformers) are deferred inside functions so
  the module can be imported without a GPU/CUDA environment (tests, CI).
- Returns None when no face is detected rather than raising, so callers can
  produce a structured error response without an exception path.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)

# Semantic label indices for jonathandinu/face-parsing.
# Labels: 0=background, 1=skin, 2=nose, 3=eye_g, 4=r_eye, 5=l_eye,
#         6=r_brow, 7=l_brow, 8=r_ear, 9=l_ear, 10=mouth, 11=u_lip,
#         12=l_lip, 13=hair, 14=hat, 15=ear_r, 16=neck_l, 17=neck, 18=cloth
_LABEL_R_EYE = 4
_LABEL_L_EYE = 5
_LABEL_UPPER_LIP = 11
_LABEL_LOWER_LIP = 12
_LABEL_SKIN = 1

_model = None
_processor = None


def _load_model():
    global _model, _processor
    if _model is not None:
        return _model, _processor
    try:
        from transformers import SegformerForSemanticSegmentation, SegformerImageProcessor

        _processor = SegformerImageProcessor.from_pretrained("jonathandinu/face-parsing")
        _model = SegformerForSemanticSegmentation.from_pretrained("jonathandinu/face-parsing")
        _model.eval()
        logger.info("face-parsing model loaded")
    except Exception as exc:
        logger.error("face-parsing model load failed: %s", exc)
        raise
    return _model, _processor


def _mask_bbox(mask: "np.ndarray") -> tuple[int, int, int, int] | None:
    """Return (x1, y1, x2, y2) bounding box for non-zero pixels in *mask*."""
    import numpy as np

    ys, xs = np.where(mask)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def _cheek_bbox_from_skin(
    skin_mask: "np.ndarray",
    eye_bbox: tuple[int, int, int, int] | None,
) -> tuple[int, int, int, int] | None:
    """Approximate cheek region as lower-half skin excluding eye area."""
    h, w = skin_mask.shape
    lower_half = skin_mask.copy()
    lower_half[: h // 2, :] = 0

    if eye_bbox is not None:
        _, ey1, _, ey2 = eye_bbox
        lower_half[ey1:ey2, :] = 0

    return _mask_bbox(lower_half)


def parse_regions(segmentation_map: "np.ndarray") -> dict | None:
    """Derive lip / eye / cheek anchor bboxes from a segmentation label map.

    Args:
        segmentation_map: 2-D array of integer labels (H × W), from the
            face-parsing model's output after argmax.

    Returns:
        Dict with keys ``lip``, ``eye``, ``cheek`` — each a
        ``(x1, y1, x2, y2)`` tuple — or ``None`` if no face region was found.
    """
    import numpy as np

    lip_mask = np.isin(segmentation_map, [_LABEL_UPPER_LIP, _LABEL_LOWER_LIP])
    eye_mask = np.isin(segmentation_map, [_LABEL_R_EYE, _LABEL_L_EYE])
    skin_mask = segmentation_map == _LABEL_SKIN

    lip_bbox = _mask_bbox(lip_mask)
    eye_bbox = _mask_bbox(eye_mask)
    cheek_bbox = _cheek_bbox_from_skin(skin_mask, eye_bbox)

    if lip_bbox is None and eye_bbox is None:
        return None

    return {
        "lip": lip_bbox,
        "eye": eye_bbox,
        "cheek": cheek_bbox,
    }


def get_region_anchors(image_url: str) -> dict | None:
    """Download *image_url*, run the face-parsing model, return anchor bboxes.

    Returns None when no face is detected or the model cannot process the image.
    All exceptions are caught and logged — callers receive None rather than a
    crash so the analyzer can return a structured ``no_face`` error.
    """
    try:
        import io

        import requests
        import torch
        from PIL import Image

        model, processor = _load_model()

        resp = requests.get(image_url, timeout=10)
        resp.raise_for_status()
        image = Image.open(io.BytesIO(resp.content)).convert("RGB")

        inputs = processor(images=image, return_tensors="pt")
        with torch.no_grad():
            outputs = model(**inputs)

        logits = outputs.logits
        upsampled = torch.nn.functional.interpolate(
            logits,
            size=image.size[::-1],
            mode="bilinear",
            align_corners=False,
        )
        seg_map = upsampled.argmax(dim=1).squeeze().numpy()
        return parse_regions(seg_map)

    except Exception as exc:
        logger.warning("face region parsing failed for %s: %s", image_url, exc)
        return None
