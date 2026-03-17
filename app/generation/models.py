"""Generation data models, enums, and constants."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal
from uuid import UUID


# ---------------------------------------------------------------------------
# Job status
# ---------------------------------------------------------------------------


class JobStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Queue lanes
# ---------------------------------------------------------------------------

LANE_PREMIUM = "generation:premium"
LANE_CREDIT = "generation:credit"
LANE_TRIAL = "generation:trial"

QUEUE_LANES = [LANE_PREMIUM, LANE_CREDIT, LANE_TRIAL]  # Priority order


# ---------------------------------------------------------------------------
# Failure reasons
# ---------------------------------------------------------------------------

FAILURE_IDENTITY = "IDENTITY_PRESERVATION_FAILED"
FAILURE_NSFW = "NSFW_CONTENT_DETECTED"
FAILURE_TIMEOUT = "GENERATION_TIMEOUT"
FAILURE_PROVIDER = "PROVIDER_ERROR"
FAILURE_CANCELLED = "CANCELLED"


# ---------------------------------------------------------------------------
# Generation options and results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GenerationOptions:
    """Parameters passed to the generation adapter."""

    model: str
    prompt: str
    negative_prompt: str
    reference_image_url: str
    id_weight: float = 0.85
    guidance_scale: float = 4.0
    num_inference_steps: int = 30
    image_size: str = "square_hd"
    max_sequence_length: str = "512"
    # Flux Dev img2img specific
    strength: float | None = None
    ip_adapter_scale: float | None = None
    # InstantID specific
    controlnet_conditioning_scale: float | None = None


@dataclass(frozen=True)
class GenerationResult:
    """Result from the generation adapter."""

    image_url: str  # URL of the generated image (from fal.ai CDN)
    seed: int | None = None
    inference_time_ms: int | None = None
    estimated_cost_usd: float | None = None


@dataclass(frozen=True)
class IdentityCheckResult:
    """Result of ArcFace identity comparison."""

    similarity_score: float
    identity_preserved: bool
    face_detected_in_output: bool = True


@dataclass(frozen=True)
class CandidateResult:
    """A single generation candidate with scoring."""

    image_url: str
    arcface_score: float
    wow_score: float
    generation_result: GenerationResult
    identity_check: IdentityCheckResult
    params_used: GenerationOptions
