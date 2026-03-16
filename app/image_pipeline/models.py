"""Image pipeline data models and error codes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID


# ---------------------------------------------------------------------------
# Error codes (AC-A10, AC-A3)
# ---------------------------------------------------------------------------

IMAGE_FORMAT_REJECTED = "IMAGE_FORMAT_REJECTED"
IMAGE_TOO_LARGE = "IMAGE_TOO_LARGE"
IMAGE_QUARANTINED = "IMAGE_QUARANTINED"


# ---------------------------------------------------------------------------
# Pipeline result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProcessedImage:
    """Result of the image processing pipeline."""

    storage_key: str | None  # None for quarantined images
    image_id: UUID
    status: Literal["cleared", "quarantined"]
