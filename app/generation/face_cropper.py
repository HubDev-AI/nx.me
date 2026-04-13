"""Face crop and composite — focus generation on face/hair/shoulders.

When face occupies < threshold of image area, crop before generation
and composite back after. Color-matched blending at edges.
"""

from __future__ import annotations

import numpy as np
import PIL.Image


def compute_crop(
    image_size: tuple[int, int],
    face_bbox: tuple[int, int, int, int],
    face_confidence: float,
) -> tuple[int, int, int, int] | None:
    """Return crop box (x1, y1, x2, y2) or None if no crop needed."""
    img_w, img_h = image_size
    fx, fy, fw, fh = face_bbox
    face_area = fw * fh
    img_area = img_w * img_h
    face_ratio = face_area / img_area

    if face_ratio > 0.40:
        return None  # Face fills frame

    if face_confidence < 0.85:
        return None  # Low confidence — don't crop on bad detection

    cx, cy = fx + fw / 2, fy + fh / 2
    pad = 2.0 if face_ratio > 0.15 else 1.5

    crop_size = max(fw, fh) * pad
    crop_size = min(crop_size, min(img_w, img_h))

    x1 = max(0, int(cx - crop_size / 2))
    y1 = max(0, int(cy - crop_size / 2))
    x2 = min(img_w, int(cx + crop_size / 2))
    y2 = min(img_h, int(cy + crop_size / 2))

    return (x1, y1, x2, y2)


def get_face_ratio(
    image_size: tuple[int, int],
    face_bbox: tuple[int, int, int, int],
) -> float:
    """Compute face area / image area ratio."""
    img_w, img_h = image_size
    _, _, fw, fh = face_bbox
    return (fw * fh) / (img_w * img_h)


def composite_glowup(
    original_img: PIL.Image.Image,
    generated_img: PIL.Image.Image,
    crop_box: tuple[int, int, int, int],
    face_bbox: tuple[int, int, int, int],
) -> PIL.Image.Image:
    """Blend generated glow-up back into original frame."""
    x1, y1, x2, y2 = crop_box
    crop_w, crop_h = x2 - x1, y2 - y1

    # Resize generated to match crop
    result = generated_img.resize((crop_w, crop_h), PIL.Image.LANCZOS)

    # Color-match before compositing
    result = _match_color_stats(result, original_img.crop(crop_box))

    # Dynamic feather radius
    face_size = max(face_bbox[2], face_bbox[3])
    feather_px = max(15, int(face_size * 0.08))

    # Feathered mask
    mask = PIL.Image.new("L", (crop_w, crop_h), 255)
    mask_array = np.array(mask)
    for i in range(feather_px):
        alpha = int(255 * i / feather_px)
        mask_array[i, :] = np.minimum(mask_array[i, :], alpha)
        mask_array[-(i + 1), :] = np.minimum(mask_array[-(i + 1), :], alpha)
        mask_array[:, i] = np.minimum(mask_array[:, i], alpha)
        mask_array[:, -(i + 1)] = np.minimum(mask_array[:, -(i + 1)], alpha)
    mask = PIL.Image.fromarray(mask_array)

    # Composite
    canvas = original_img.copy()
    canvas.paste(result, (x1, y1), mask)
    return canvas


def _match_color_stats(
    generated: PIL.Image.Image,
    original_crop: PIL.Image.Image,
) -> PIL.Image.Image:
    """Match mean brightness/color of generated to original crop."""
    gen_arr = np.array(generated, dtype=float)
    orig_arr = np.array(original_crop, dtype=float)

    for c in range(3):
        gen_mean = gen_arr[:, :, c].mean()
        orig_mean = orig_arr[:, :, c].mean()
        if gen_mean > 0:
            factor = orig_mean / gen_mean
            factor = max(0.8, min(1.2, factor))
            gen_arr[:, :, c] *= factor

    gen_arr = np.clip(gen_arr, 0, 255).astype(np.uint8)
    return PIL.Image.fromarray(gen_arr)
