"""fal.ai adapter — real generation via Flux PuLID / Flux Dev / InstantID.

Implements GlowUpGeneratorPort. Lazy-imports fal_client to avoid
dependency when using MockGeneratorAdapter.
"""
from __future__ import annotations

import asyncio
import logging
import time

from app.config import settings
from app.generation.models import GenerationOptions, GenerationResult

logger = logging.getLogger(__name__)


class FalAiAdapter:
    """Real fal.ai generation adapter."""

    def __init__(self) -> None:
        import fal_client
        self._client = fal_client

    async def generate(
        self,
        source_image_url: str,
        prompt: str,
        options: GenerationOptions,
    ) -> GenerationResult:
        """Call fal.ai API for image generation."""
        loop = asyncio.get_running_loop()
        start_ms = int(time.time() * 1000)

        # Build request based on model
        if "flux-pulid" in options.model:
            request = self._build_pulid_request(source_image_url, prompt, options)
        elif "flux-general" in options.model:
            request = self._build_flux_dev_request(source_image_url, prompt, options)
        elif "instantid" in options.model:
            request = self._build_instantid_request(source_image_url, prompt, options)
        else:
            raise ValueError(f"Unknown model: {options.model}")

        # Run sync fal_client call in executor
        result = await loop.run_in_executor(
            None,
            lambda: self._client.subscribe(options.model, arguments=request),
        )

        elapsed_ms = int(time.time() * 1000) - start_ms

        # Extract image URL from result
        image_url = self._extract_image_url(result)

        logger.info(
            "fal.ai generation complete: model=%s, time=%dms",
            options.model, elapsed_ms,
        )

        return GenerationResult(
            image_url=image_url,
            seed=result.get("seed"),
            inference_time_ms=elapsed_ms,
            estimated_cost_usd=self._estimate_cost(options.model),
        )

    def _build_pulid_request(self, source_url: str, prompt: str, opts: GenerationOptions) -> dict:
        return {
            "prompt": prompt,
            "reference_image_url": source_url,
            "id_weight": opts.id_weight,
            "guidance_scale": opts.guidance_scale,
            "num_inference_steps": opts.num_inference_steps,
            "negative_prompt": opts.negative_prompt,
            "image_size": opts.image_size,
            "max_sequence_length": opts.max_sequence_length,
        }

    def _build_flux_dev_request(self, source_url: str, prompt: str, opts: GenerationOptions) -> dict:
        request: dict = {
            "prompt": prompt,
            "image_url": source_url,
            "strength": opts.strength or 0.55,
            "guidance_scale": opts.guidance_scale,
            "num_inference_steps": opts.num_inference_steps,
            "negative_prompt": opts.negative_prompt,
            "image_size": opts.image_size,
        }
        if opts.ip_adapter_scale:
            request["ip_adapters"] = [{
                "path": "h94/IP-Adapter-FaceID",
                "image_url": source_url,
                "scale": opts.ip_adapter_scale,
            }]
        return request

    def _build_instantid_request(self, source_url: str, prompt: str, opts: GenerationOptions) -> dict:
        return {
            "prompt": prompt,
            "face_image_url": source_url,
            "controlnet_conditioning_scale": opts.controlnet_conditioning_scale or 0.80,
            "guidance_scale": opts.guidance_scale,
            "num_inference_steps": opts.num_inference_steps,
            "negative_prompt": opts.negative_prompt,
            "model_type": "SDXL-v2-plus",
            "width": 1024,
            "height": 1024,
        }

    def _extract_image_url(self, result: dict) -> str:
        """Extract the generated image URL from fal.ai response."""
        if "images" in result and result["images"]:
            return result["images"][0]["url"]
        if "image" in result and isinstance(result["image"], dict):
            return result["image"]["url"]
        if "image" in result and isinstance(result["image"], str):
            return result["image"]
        raise ValueError(f"Could not extract image URL from fal.ai response: {list(result.keys())}")

    def _estimate_cost(self, model: str) -> float:
        """Estimate cost per generation by model (from config)."""
        costs = {
            settings.FAL_MODEL_PRIMARY: settings.FAL_COST_FLUX_PULID,
            settings.FAL_MODEL_FALLBACK_1: settings.FAL_COST_FLUX_DEV_IMG2IMG,
            settings.FAL_MODEL_FALLBACK_2: settings.FAL_COST_INSTANTID,
        }
        return costs.get(model, settings.FAL_COST_DEFAULT)
