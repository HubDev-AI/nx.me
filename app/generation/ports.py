"""Generation port — interface for AI generation adapters.

The worker calls GlowUpGeneratorPort.generate() — never fal.ai directly.
Adapters: FalAiAdapter (real), MockGeneratorAdapter (testing).
"""
from __future__ import annotations

from typing import Protocol

from app.generation.models import GenerationOptions, GenerationResult


class GlowUpGeneratorPort(Protocol):
    """Interface for glow-up image generation."""

    async def generate(
        self,
        source_image_url: str,
        prompt: str,
        options: GenerationOptions,
    ) -> GenerationResult:
        """Generate a glow-up image from the source.

        Args:
            source_image_url: Signed URL to the source selfie.
            prompt: Full generation prompt.
            options: Model-specific parameters.

        Returns:
            GenerationResult with the generated image URL.

        Raises:
            Exception: On provider failure (circuit breaker handles retries).
        """
        ...
