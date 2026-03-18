"""Minimal post-generation color normalization.

Non-destructive. No AI model. No skin smoothing.
Only matches brightness between source and generated output.
"""
from __future__ import annotations

import PIL.Image
from PIL import ImageEnhance, ImageStat


def normalize_output(
    source_img: PIL.Image.Image,
    generated_img: PIL.Image.Image,
) -> PIL.Image.Image:
    """Match generated image brightness to source. No skin touch."""
    src_brightness = ImageStat.Stat(source_img).mean[0]
    gen_brightness = ImageStat.Stat(generated_img).mean[0]

    if abs(src_brightness - gen_brightness) > 20:
        factor = src_brightness / max(gen_brightness, 1)
        factor = max(0.8, min(1.2, factor))
        generated_img = ImageEnhance.Brightness(generated_img).enhance(factor)

    return generated_img
