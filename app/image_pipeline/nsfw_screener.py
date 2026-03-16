"""NSFW screening — port/adapter for content moderation.

AC-3: Images with AWS Rekognition confidence >=80% for explicit content
are quarantined. Pipeline must complete within <=5s.

Port/Adapter pattern:
  - NSFWScreenerPort: interface
  - RekognitionAdapter: real AWS Rekognition (staging/prod)
  - MockNSFWAdapter: always passes (local dev, testing non-NSFW features)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

import boto3

from app.config import settings

logger = logging.getLogger(__name__)

# Business rule from AC-A3 — not env-configurable.
NSFW_CONFIDENCE_THRESHOLD: float = 80.0


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NSFWResult:
    """Result of NSFW content screening."""

    is_explicit: bool
    confidence: float  # 0.0 – 100.0
    labels: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Port
# ---------------------------------------------------------------------------


class NSFWScreenerPort(Protocol):
    """Interface for NSFW content screening adapters."""

    async def screen(self, image_bytes: bytes) -> NSFWResult: ...


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------


class RekognitionAdapter:
    """AWS Rekognition adapter — real NSFW screening.

    Calls detect_moderation_labels synchronously. Typical latency <=3s.
    Cost: ~$0.001/image.
    """

    def __init__(self) -> None:
        self._client = boto3.client(
            "rekognition",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )

    async def screen(self, image_bytes: bytes) -> NSFWResult:
        try:
            response = self._client.detect_moderation_labels(
                Image={"Bytes": image_bytes},
            )
        except Exception as exc:
            logger.error("Rekognition detect_moderation_labels failed: %s", exc)
            # Fail open — allow the image through if Rekognition is unavailable.
            # A quarantine-review queue can catch false negatives later.
            return NSFWResult(is_explicit=False, confidence=0.0, labels=[])

        labels = response.get("ModerationLabels", [])
        if not labels:
            return NSFWResult(is_explicit=False, confidence=0.0, labels=[])

        max_confidence = max(label["Confidence"] for label in labels)
        label_names = [label["Name"] for label in labels]

        is_explicit = max_confidence >= NSFW_CONFIDENCE_THRESHOLD

        if is_explicit:
            logger.info(
                "NSFW content detected (confidence=%.1f%%, labels=%s)",
                max_confidence,
                label_names,
            )

        return NSFWResult(
            is_explicit=is_explicit,
            confidence=max_confidence,
            labels=label_names,
        )


class MockNSFWAdapter:
    """Mock adapter — always passes. For local dev when testing non-NSFW features."""

    async def screen(self, image_bytes: bytes) -> NSFWResult:  # noqa: ARG002
        return NSFWResult(is_explicit=False, confidence=0.0, labels=[])
