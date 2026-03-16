"""NSFW screening — port/adapter for content moderation.

AC-3: Images with AWS Rekognition confidence >=80% for explicit content
are quarantined. Pipeline must complete within <=5s.

Port/Adapter pattern:
  - NSFWScreenerPort: interface
  - RekognitionAdapter: real AWS Rekognition (staging/prod)
  - MockNSFWAdapter: always passes (local dev, testing non-NSFW features)
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Protocol

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
    screened: bool = True  # False if screening was skipped due to error


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

    Calls detect_moderation_labels via thread executor to avoid blocking
    the asyncio event loop. Typical latency <=3s. Cost: ~$0.001/image.
    """

    def __init__(self) -> None:
        import boto3  # Lazy import — only loaded when rekognition adapter is used

        self._client = boto3.client(
            "rekognition",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )

    async def screen(self, image_bytes: bytes) -> NSFWResult:
        loop = asyncio.get_event_loop()

        try:
            response = await loop.run_in_executor(
                None,
                lambda: self._client.detect_moderation_labels(Image={"Bytes": image_bytes}),
            )
        except Exception as exc:
            # Fail closed — reject the image if Rekognition is unavailable.
            # This prevents NSFW content from slipping through during outages.
            logger.critical("Rekognition unavailable — failing closed: %s", exc)
            return NSFWResult(is_explicit=True, confidence=0.0, labels=["SCREENING_UNAVAILABLE"], screened=False)

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
