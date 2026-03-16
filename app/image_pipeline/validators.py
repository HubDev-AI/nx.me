"""Image validation — magic bytes and dimension checks.

AC-1: Reject files whose magic bytes do not match JPEG/PNG/HEIF.
AC-2: Reject files exceeding MAX_UPLOAD_SIZE_MB or MAX_IMAGE_DIMENSION_PX.
"""
from __future__ import annotations

import io
import logging

import PIL.Image

from fastapi import HTTPException, status

from app.config import settings
from app.image_pipeline.models import IMAGE_FORMAT_REJECTED, IMAGE_TOO_LARGE

logger = logging.getLogger(__name__)

# Align Pillow's decompression bomb guard with our configured max dimension.
PIL.Image.MAX_IMAGE_PIXELS = settings.MAX_IMAGE_DIMENSION_PX * settings.MAX_IMAGE_DIMENSION_PX

# ---------------------------------------------------------------------------
# Magic bytes signatures
# ---------------------------------------------------------------------------

_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_HEIF_FTYP = b"ftyp"
_HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"mif1"}


def _is_supported_format(data: bytes) -> bool:
    """Check if the first bytes match JPEG, PNG, or HEIF signatures."""
    if len(data) < 12:
        return False
    if data[:3] == _JPEG_MAGIC:
        return True
    if data[:8] == _PNG_MAGIC:
        return True
    # HEIF: bytes 4-8 = 'ftyp', bytes 8-12 = brand
    if data[4:8] == _HEIF_FTYP and data[8:12] in _HEIF_BRANDS:
        return True
    return False


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


class MagicBytesValidator:
    """Reject files whose magic bytes do not match JPEG, PNG, or HEIF (AC-1)."""

    def validate(self, file_bytes: bytes) -> None:
        if not _is_supported_format(file_bytes):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": {
                        "code": IMAGE_FORMAT_REJECTED,
                        "message": "Uploaded file is not a supported image format (JPEG, PNG, HEIF).",
                        "retry_eligible": True,
                    }
                },
            )


class DimensionValidator:
    """Reject files exceeding size or dimension limits (AC-2)."""

    def validate(self, file_bytes: bytes) -> None:
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if len(file_bytes) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": {
                        "code": IMAGE_TOO_LARGE,
                        "message": f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB}MB upload limit.",
                        "retry_eligible": True,
                    }
                },
            )

        try:
            with PIL.Image.open(io.BytesIO(file_bytes)) as img:
                width, height = img.size
        except PIL.Image.DecompressionBombError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": {
                        "code": IMAGE_TOO_LARGE,
                        "message": "Image dimensions exceed the maximum allowed.",
                        "retry_eligible": True,
                    }
                },
            )
        except Exception as exc:
            logger.warning("Failed to open image for dimension check: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": {
                        "code": IMAGE_FORMAT_REJECTED,
                        "message": "Could not read image dimensions. File may be corrupted.",
                        "retry_eligible": True,
                    }
                },
            ) from exc

        max_dim = settings.MAX_IMAGE_DIMENSION_PX
        if width > max_dim or height > max_dim:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": {
                        "code": IMAGE_TOO_LARGE,
                        "message": f"Image dimensions ({width}x{height}) exceed the {max_dim}px limit.",
                        "retry_eligible": True,
                    }
                },
            )
