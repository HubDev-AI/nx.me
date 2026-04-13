"""Metadata stripping — remove all EXIF, IPTC, and XMP data from images.

AC-4: Stored files must have zero EXIF/IPTC/XMP metadata. A JPEG with GPS
coordinates must result in zero location metadata in the stored file.

Approach: Open the image, extract raw pixel data, create a fresh image from
those pixels, and re-encode. The original byte stream (and all its metadata
chunks) is discarded entirely.
"""

from __future__ import annotations

import io
import logging

import PIL.Image
import pillow_heif

# Register HEIF/HEIC format support with Pillow
pillow_heif.register_heif_opener()

logger = logging.getLogger(__name__)

# Re-encode quality settings
_JPEG_QUALITY = 95


class MetadataStripper:
    """Strip all metadata from an image by clean re-encode."""

    def strip(self, image_bytes: bytes, content_type: str) -> bytes:
        """Remove all EXIF/IPTC/XMP metadata and return clean bytes.

        Args:
            image_bytes: Raw image bytes (validated format).
            content_type: MIME type (image/jpeg, image/png, image/heif).

        Returns:
            Re-encoded image bytes with zero metadata.
        """
        with PIL.Image.open(io.BytesIO(image_bytes)) as original:
            # Create a fresh image from pixel data only — discards all metadata
            clean = PIL.Image.new(original.mode, original.size)
            clean.putdata(list(original.getdata()))

            # Preserve ICC profile if present (color accuracy, not PII)
            icc_profile = original.info.get("icc_profile")

            output = io.BytesIO()
            save_kwargs: dict = {}

            if icc_profile:
                save_kwargs["icc_profile"] = icc_profile

            fmt = _resolve_format(content_type)

            if fmt == "JPEG":
                save_kwargs["quality"] = _JPEG_QUALITY
                # JPEG doesn't support alpha — convert RGBA/LA to RGB
                if clean.mode in ("RGBA", "LA"):
                    clean = clean.convert("RGB")
                elif clean.mode == "P":
                    clean = clean.convert("RGB")
            elif fmt == "PNG":
                save_kwargs["optimize"] = True

            clean.save(output, format=fmt, **save_kwargs)
            result = output.getvalue()

        logger.debug(
            "Metadata stripped: %d bytes → %d bytes (%s)",
            len(image_bytes),
            len(result),
            fmt,
        )
        return result


def _resolve_format(content_type: str) -> str:
    """Map MIME content type to Pillow format string."""
    mapping = {
        "image/jpeg": "JPEG",
        "image/png": "PNG",
        "image/heif": "JPEG",  # Re-encode HEIF as JPEG for broad compatibility
        "image/heic": "JPEG",
    }
    return mapping.get(content_type, "JPEG")
