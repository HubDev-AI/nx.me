"""Minimal post-generation color normalization.

Non-destructive. No AI model. No skin smoothing.
Only matches brightness between source and generated output.
"""
from __future__ import annotations

import PIL.Image
from PIL import ImageEnhance, ImageStat

from app.config import settings


def normalize_output(
    source_img: PIL.Image.Image,
    generated_img: PIL.Image.Image,
) -> PIL.Image.Image:
    """Match generated image brightness to source. No skin touch."""
    src_brightness = ImageStat.Stat(source_img).mean[0]
    gen_brightness = ImageStat.Stat(generated_img).mean[0]

    # G-8: Brightness threshold and clamp values sourced from config
    if abs(src_brightness - gen_brightness) > settings.COLOR_NORM_BRIGHTNESS_DELTA:
        factor = src_brightness / max(gen_brightness, 1)
        factor = max(settings.COLOR_NORM_FACTOR_MIN, min(settings.COLOR_NORM_FACTOR_MAX, factor))
        generated_img = ImageEnhance.Brightness(generated_img).enhance(factor)

    return generated_img
