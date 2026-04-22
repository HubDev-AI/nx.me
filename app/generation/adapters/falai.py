"""fal.ai adapter — real generation via Flux PuLID / Flux Dev / InstantID.

Implements GlowUpGeneratorPort. Lazy-imports fal_client to avoid
dependency when using MockGeneratorAdapter.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass

from app.config import settings
from app.generation.models import GenerationOptions, GenerationResult

logger = logging.getLogger(__name__)

_FAL_MAKEUP_ENDPOINT = "fal-ai/image-apps-v2/makeup-application"


@dataclass
class MakeupAdapterResult:
    fal_request_id: str
    fal_output_url: str


class MakeupAdapterError(Exception):
    """Typed error from apply_makeup_preset — categorised by retry posture."""

    def __init__(
        self, *, kind: str, reason: str, retry_after: int | None = None
    ) -> None:
        super().__init__(reason)
        self.kind = kind  # "non_retryable" | "retryable" | "config"
        self.reason = reason
        self.retry_after = retry_after


def _parse_retry_after(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return max(0, int(raw))
    except ValueError:
        from datetime import datetime, timezone
        from email.utils import parsedate_to_datetime

        try:
            dt = parsedate_to_datetime(raw)
            return max(0, int((dt - datetime.now(tz=timezone.utc)).total_seconds()))
        except Exception:
            return None


class FalAiAdapter:
    """Real fal.ai generation adapter."""

    async def _ensure_public_url(self, source_image_url: str) -> str:
        """Upload image to fal CDN if the source URL is not publicly reachable.

        Local/LAN Supabase storage URLs can't be fetched by fal.ai servers,
        so we download the bytes and upload to fal's CDN first.
        """
        from ipaddress import ip_address
        from urllib.parse import urlparse

        parsed = urlparse(source_image_url)
        host = parsed.hostname or ""

        # Check if host is local/private (localhost, 127.x, 192.168.x, 10.x, etc.)
        is_local = host in ("localhost", "0.0.0.0")
        if not is_local:
            try:
                is_local = ip_address(host).is_private
            except ValueError:
                is_local = False

        if not is_local:
            return source_image_url

        import fal_client
        import httpx

        logger.info("Uploading local image to fal CDN (source host=%s)", host)
        async with httpx.AsyncClient() as http:
            resp = await http.get(source_image_url)
            resp.raise_for_status()

        cdn_url = await fal_client.upload_async(resp.content, content_type="image/jpeg")
        logger.info("Image uploaded to fal CDN: %s", cdn_url)
        return cdn_url

    async def generate(
        self,
        source_image_url: str,
        prompt: str,
        options: GenerationOptions,
    ) -> GenerationResult:
        """Call fal.ai API for image generation using native async client."""
        import fal_client

        start_ms = int(time.time() * 1000)

        # Ensure fal.ai can reach the image
        source_image_url = await self._ensure_public_url(source_image_url)

        # Build request based on model
        if "flux-2" in options.model or "flux2" in options.model:
            request = self._build_flux2_edit_request(source_image_url, prompt, options)
        elif "nano-banana-pro" in options.model:
            request = self._build_nano_banana_pro_request(
                source_image_url, prompt, options
            )
        elif "nano-banana-2" in options.model:
            request = self._build_nano_banana_2_request(
                source_image_url, prompt, options
            )
        elif "nano-banana" in options.model:
            request = self._build_nano_banana_request(source_image_url, prompt, options)
        elif "kontext" in options.model:
            request = self._build_kontext_request(source_image_url, prompt, options)
        elif "flux-pulid" in options.model:
            request = self._build_pulid_request(source_image_url, prompt, options)
        elif "flux-general" in options.model:
            request = self._build_flux_dev_request(source_image_url, prompt, options)
        elif "instantid" in options.model:
            request = self._build_instantid_request(source_image_url, prompt, options)
        else:
            raise ValueError(f"Unknown model: {options.model}")

        # Native async call with timeout protection
        result = await asyncio.wait_for(
            fal_client.run_async(options.model, arguments=request),
            timeout=settings.GENERATION_TIMEOUT_SECONDS,
        )

        elapsed_ms = int(time.time() * 1000) - start_ms

        # Extract image URL from result
        image_url = self._extract_image_url(result)

        logger.info(
            "fal.ai generation complete: model=%s, time=%dms",
            options.model,
            elapsed_ms,
        )

        return GenerationResult(
            image_url=image_url,
            seed=result.get("seed"),
            inference_time_ms=elapsed_ms,
            estimated_cost_usd=self._estimate_cost(options.model),
        )

    def _build_flux2_edit_request(
        self, source_url: str, prompt: str, opts: GenerationOptions
    ) -> dict:
        """FLUX.2 [flex] Edit — tunable guidance + steps for portrait glow-ups.

        Optimal settings for identity-preserving portrait edits:
        - guidance_scale 3.5-4.0: balanced adherence without over-stylizing
        - num_inference_steps 30-40: good facial detail fidelity
        - image_size square_hd: works for portrait selfies
        """
        return {
            "prompt": prompt,
            "image_urls": [source_url],
            "guidance_scale": opts.guidance_scale,
            "num_inference_steps": opts.num_inference_steps,
            "image_size": opts.image_size,
            "output_format": "jpeg",
        }

    def _build_nano_banana_pro_request(
        self, source_url: str, prompt: str, opts: GenerationOptions
    ) -> dict:
        """Nano Banana Pro (Gemini 3 Pro Image) — top-tier reasoning-guided identity edits.

        4x more expensive than v1 ($0.15/image) but strongest semantic reasoning
        and multi-image context understanding.
        """
        return {
            "prompt": prompt,
            "image_urls": [source_url],
            "aspect_ratio": "1:1",
            "output_format": "jpeg",
            "resolution": "1K",
        }

    def _build_nano_banana_2_request(
        self, source_url: str, prompt: str, opts: GenerationOptions
    ) -> dict:
        """Nano Banana 2 (Gemini 3.1 Flash Image) — reasoning-guided identity-preserving edits.

        Supports 1K/2K/4K resolution and thinking_level for better results.
        """
        return {
            "prompt": prompt,
            "image_urls": [source_url],
            "aspect_ratio": "1:1",
            "output_format": "jpeg",
            "resolution": "1K",
            "thinking_level": "high",
        }

    def _build_nano_banana_request(
        self, source_url: str, prompt: str, opts: GenerationOptions
    ) -> dict:
        """Nano Banana (Gemini 2.5 Flash Image) — best identity preservation + natural edits."""
        return {
            "prompt": prompt,
            "image_urls": [source_url],
            "aspect_ratio": "1:1",
            "output_format": "jpeg",
        }

    def _build_kontext_request(
        self, source_url: str, prompt: str, opts: GenerationOptions
    ) -> dict:
        """FLUX Kontext — iterative editing that preserves identity naturally."""
        return {
            "prompt": prompt,
            "image_url": source_url,
            "guidance_scale": opts.guidance_scale,
            "num_inference_steps": opts.num_inference_steps,
            "aspect_ratio": "1:1",
            "output_format": "jpeg",
        }

    def _build_pulid_request(
        self, source_url: str, prompt: str, opts: GenerationOptions
    ) -> dict:
        return {
            "prompt": prompt,
            "reference_image_url": source_url,
            "id_weight": opts.id_weight,
            "true_cfg": opts.true_cfg,
            "guidance_scale": opts.guidance_scale,
            "num_inference_steps": opts.num_inference_steps,
            "negative_prompt": opts.negative_prompt,
            "image_size": opts.image_size,
            "max_sequence_length": opts.max_sequence_length,
        }

    def _build_flux_dev_request(
        self, source_url: str, prompt: str, opts: GenerationOptions
    ) -> dict:
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
            request["ip_adapters"] = [
                {
                    "path": "h94/IP-Adapter-FaceID",
                    "image_url": source_url,
                    "scale": opts.ip_adapter_scale,
                }
            ]
        return request

    def _build_instantid_request(
        self, source_url: str, prompt: str, opts: GenerationOptions
    ) -> dict:
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
        raise ValueError(
            f"Could not extract image URL from fal.ai response: {list(result.keys())}"
        )

    # ------------------------------------------------------------------
    # Makeup — apply_makeup_preset
    # ------------------------------------------------------------------

    async def apply_makeup_preset(
        self,
        image_url: str,
        fal_style: str,
        fal_intensity: str,
        *,
        idempotency_key: str | None = None,
        aspect_ratio: str = "3:4",
    ) -> MakeupAdapterResult:
        """Call the makeup-application fal endpoint; return result or raise MakeupAdapterError."""
        import fal_client
        from fal_client.client import FalClientHTTPError, FalClientTimeoutError

        public_url = await self._ensure_public_url(image_url)

        arguments = {
            "image_url": public_url,
            "style": fal_style,
            "intensity": fal_intensity,
            "aspect_ratio": aspect_ratio,
        }

        headers: dict[str, str] = {
            "X-Fal-Store-IO": "0",
            "X-Fal-Object-Lifecycle-Preference": json.dumps(
                {"expiration_duration_seconds": 300}
            ),
        }
        if idempotency_key:
            headers["X-Fal-Idempotency-Key"] = idempotency_key

        captured_request_id: list[str] = []

        def _on_enqueue(request_id: str) -> None:
            captured_request_id.append(request_id)

        try:
            result = await fal_client.subscribe_async(
                _FAL_MAKEUP_ENDPOINT,
                arguments=arguments,
                headers=headers,
                on_enqueue=_on_enqueue,
                client_timeout=settings.GENERATION_TIMEOUT_SECONDS,
            )
        except FalClientTimeoutError:
            raise MakeupAdapterError(kind="retryable", reason="fal_timeout")
        except FalClientHTTPError as exc:
            raise self._map_fal_http_error(exc) from exc

        output_url = result.get("output_url") or ""
        if not output_url or not output_url.startswith("https://"):
            logger.error(
                "fal malformed 200 for %s — full response: %r",
                _FAL_MAKEUP_ENDPOINT,
                result,
            )
            raise MakeupAdapterError(
                kind="non_retryable", reason="fal_malformed_response"
            )

        request_id = captured_request_id[0] if captured_request_id else ""
        return MakeupAdapterResult(fal_request_id=request_id, fal_output_url=output_url)

    def _map_fal_http_error(self, exc: object) -> MakeupAdapterError:
        from fal_client.client import FalClientHTTPError

        assert isinstance(exc, FalClientHTTPError)
        code = exc.status_code
        error_type = (
            exc.response_headers.get("X-Fal-Error-Type")
            or exc.response_headers.get("x-fal-error-type")
            or ""
        )

        if (
            code in (400, 422)
            or "bad_request" in error_type
            or "content_filter" in error_type
        ):
            return MakeupAdapterError(
                kind="non_retryable", reason=f"fal_bad_request: {exc}"
            )
        if code == 429:
            retry_after = _parse_retry_after(
                exc.response_headers.get("Retry-After")
                or exc.response_headers.get("retry-after")
            )
            return MakeupAdapterError(
                kind="retryable", reason="fal_rate_limited", retry_after=retry_after
            )
        if code == 401:
            return MakeupAdapterError(kind="config", reason="fal_auth_invalid")
        if code == 402:
            return MakeupAdapterError(kind="config", reason="fal_billing_required")
        if (
            code in (502, 503)
            or "runner_" in error_type
            or "internal_error" in error_type
        ):
            return MakeupAdapterError(
                kind="retryable", reason=f"fal_server_error_{code}"
            )
        return MakeupAdapterError(kind="retryable", reason=f"fal_unknown_status_{code}")

    def _estimate_cost(self, model: str) -> float:
        """Estimate cost per generation by model (from config)."""
        if "flux-2" in model or "flux2" in model:
            return settings.FAL_COST_FLUX2_FLEX
        if "nano-banana-pro" in model:
            return settings.FAL_COST_NANO_BANANA_PRO
        if "nano-banana-2" in model:
            return settings.FAL_COST_NANO_BANANA_2
        if "nano-banana" in model:
            return settings.FAL_COST_NANO_BANANA
        if "kontext" in model:
            return settings.FAL_COST_KONTEXT
        if "pulid" in model:
            return settings.FAL_COST_FLUX_PULID
        if "flux-general" in model:
            return settings.FAL_COST_FLUX_DEV_IMG2IMG
        if "instantid" in model:
            return settings.FAL_COST_INSTANTID
        return settings.FAL_COST_DEFAULT
