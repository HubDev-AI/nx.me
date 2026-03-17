"""Mock generation adapter — deterministic results for testing."""
from __future__ import annotations

from app.generation.models import GenerationOptions, GenerationResult


class MockGeneratorAdapter:
    """Returns a deterministic result. No fal.ai calls."""

    async def generate(
        self,
        source_image_url: str,
        prompt: str,
        options: GenerationOptions,
    ) -> GenerationResult:
        return GenerationResult(
            image_url=source_image_url,  # Return source as "generated"
            seed=42,
            inference_time_ms=100,
            estimated_cost_usd=0.0,
        )
