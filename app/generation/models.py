"""Generation data models, enums, and constants."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


# ---------------------------------------------------------------------------
# Job status
# ---------------------------------------------------------------------------


class JobStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Failure reasons
# ---------------------------------------------------------------------------

FAILURE_IDENTITY = "IDENTITY_PRESERVATION_FAILED"
FAILURE_NSFW = "NSFW_CONTENT_DETECTED"
FAILURE_TIMEOUT = "GENERATION_TIMEOUT"
FAILURE_PROVIDER = "PROVIDER_ERROR"
FAILURE_CANCELLED = "CANCELLED"

# Failure reasons caused by the provider/system (not the user).
# Worker auto-releases credits for these. User-caused failures (NSFW, IDENTITY)
# require the client to initiate the "Report issue" → refund flow.
NON_USER_FAILURE_REASONS: frozenset[str] = frozenset(
    [
        FAILURE_TIMEOUT,
        FAILURE_PROVIDER,
    ]
)


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
    id_weight: float = 0.95
    true_cfg: float = 1.0
    guidance_scale: float = 4.0
    num_inference_steps: int = 35
    image_size: str = "square_hd"
    max_sequence_length: int = 512
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
