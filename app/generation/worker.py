"""ARQ worker functions for generation pipeline.

process_generation_job: full lifecycle (reserve → generate → identity → commit/release)
watchdog_stuck_jobs: cron job to recover stuck processing jobs
"""
from __future__ import annotations

import asyncio
import io
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from supabase import Client

from app.config import settings
from app.generation.color_normalizer import normalize_output
from app.generation.cost_tracker import CostTracker
from app.generation.face_cropper import compute_crop, composite_glowup, get_face_ratio
from app.generation.identity_checker import check_identity
from app.generation.models import (
    FAILURE_IDENTITY,
    FAILURE_NSFW,
    FAILURE_PROVIDER,
    FAILURE_TIMEOUT,
    GenerationOptions,
    JobStatus,
)
from app.generation.ports import GlowUpGeneratorPort
from app.generation.prompt_builder import build_prompt
from app.repositories.analysis_repo import AnalysisRepository
from app.repositories.image_repo import ImageRepository
from app.repositories.job_repo import JobRepository

logger = logging.getLogger(__name__)


def _get_generator() -> GlowUpGeneratorPort:
    """Resolve generator adapter from config (lazy import)."""
    if settings.ADAPTER__IMAGE_GENERATION_ADAPTER == "falai":
        from app.generation.adapters.falai import FalAiAdapter
        return FalAiAdapter()
    from app.generation.adapters.mock import MockGeneratorAdapter
    return MockGeneratorAdapter()


async def _fetch_and_claim_job(
    job_repo: JobRepository,
    cost_tracker: CostTracker,
    job_id: str,
    supabase: Client,
) -> dict | None:
    """Fetch job, run pre-flight checks, and claim it.

    Returns the job_data dict if the job was claimed successfully,
    or None if the job should not be processed (terminal state, cancelled,
    emergency stop, circuit open, or claim race lost).
    """
    job_data = job_repo.get_by_id_single(job_id)
    if not job_data:
        logger.error("Job %s not found", job_id)
        return None

    # Check if already cancelled/terminal before processing (P1-3)
    if job_data["status"] in (JobStatus.CANCELLED, JobStatus.COMPLETED, JobStatus.FAILED):
        logger.info("Job %s already in terminal state '%s' — skipping", job_id, job_data["status"])
        return None

    # Pre-flight checks — now using _fail_job which releases credits (P2-6)
    if await cost_tracker.is_emergency_stopped():
        logger.warning("Emergency stop active — failing job %s", job_id)
        await _fail_job(job_repo, job_id, job_data, "PROVIDER_ERROR", supabase=supabase)
        return None

    if await cost_tracker.is_circuit_open():
        logger.warning("Circuit breaker open — failing job %s", job_id)
        await _fail_job(job_repo, job_id, job_data, FAILURE_PROVIDER, supabase=supabase)
        return None

    # Claim job with conditional update — only if still queued (P1-3)
    claim_result = job_repo.claim(job_id)
    if not claim_result:
        logger.info("Job %s not in queued state — aborting", job_id)
        return None

    return job_data


async def _build_generation_context(
    job_repo: JobRepository,
    image_repo: ImageRepository,
    analysis_repo: AnalysisRepository,
    job_data: dict,
) -> tuple[GenerationOptions, str, dict, str]:
    """Fetch analysis, build prompt, sign source URL, assemble GenerationOptions.

    Returns (options, source_url, adaptive_params, prompt).
    """
    # Fetch analysis for prompt building
    analysis = None
    if job_data.get("analysis_id"):
        analysis_row = analysis_repo.get_for_worker(job_data["analysis_id"])
        if analysis_row:
            from app.face_analysis.models import AnalysisResult, FaceShape, Suggestion
            recs = analysis_row.get("recommendations") or []
            analysis = AnalysisResult(
                face_shape=FaceShape(analysis_row["face_shape"]),
                symmetry_score=analysis_row["symmetry_score"],
                recommendations=[
                    Suggestion(
                        rank=r.get("rank", i + 1),
                        category=r.get("category", ""),
                        suggestion_text=r.get("suggestion_text", ""),
                        rationale=r.get("rationale", ""),
                    )
                    for i, r in enumerate(recs)
                ],
            )

    # Build prompt
    if analysis:
        prompt, negative, adaptive_params = build_prompt(analysis)
    else:
        prompt = "Professional portrait with improved styling"
        negative = ""
        adaptive_params = {"id_weight": 0.85, "guidance_scale": 4.0, "num_inference_steps": 30}

    # Get source image signed URL
    source_img = image_repo.get_by_id_single(job_data["original_image_id"])
    source_url = image_repo.create_signed_url(source_img["bucket"], source_img["storage_key"], 300)

    options = GenerationOptions(
        model=settings.FAL_MODEL_PRIMARY,
        prompt=prompt,
        negative_prompt=negative,
        reference_image_url=source_url,
        id_weight=adaptive_params["id_weight"],
        guidance_scale=adaptive_params["guidance_scale"],
        num_inference_steps=adaptive_params["num_inference_steps"],
    )

    return options, source_url, adaptive_params, prompt


async def _generate_and_validate(
    job_repo: JobRepository,
    image_repo: ImageRepository,
    cost_tracker: CostTracker,
    generator: GlowUpGeneratorPort,
    job_id: str,
    job_data: dict,
    options: GenerationOptions,
    source_url: str,
    adaptive_params: dict,
    prompt: str,
    negative: str,
    storage_key: str,
    user_id: str,
    supabase: Client,
) -> tuple[object, bytes, bytes, object] | None:
    """Generate image, screen for NSFW, check identity, retry if needed.

    Returns (gen_result, gen_image_bytes, source_image_bytes, identity_result) on success,
    or None if the job was failed (NSFW or identity).
    """
    import httpx

    # Generate
    gen_result = await generator.generate(source_url, prompt, options)

    # Track cost
    if gen_result.estimated_cost_usd:
        await cost_tracker.record_cost(gen_result.estimated_cost_usd)
        await cost_tracker.increment_user_daily(user_id)

    # Download generated image from provider immediately — the fal.ai
    # URL must not be used for any downstream processing after this point.
    async with httpx.AsyncClient() as client:
        resp = await client.get(gen_result.image_url)
        resp.raise_for_status()
        gen_image_bytes = resp.content

    # Write raw generated image to NXME storage before any checks
    # (architecture.md §160: write to storage first, never use provider
    # URL for downstream processing).  The file is overwritten later
    # after color normalization.
    image_repo.upload("generated-images", storage_key, gen_image_bytes, "image/jpeg")

    # NSFW screen output — uses in-memory bytes (from NXME storage write)
    if settings.ADAPTER__NSFW_ADAPTER == "rekognition":
        from app.image_pipeline.nsfw_screener import RekognitionAdapter
        screener = RekognitionAdapter()
        nsfw_result = await screener.screen(gen_image_bytes)

        if nsfw_result.is_explicit:
            # Clean up the already-uploaded image before failing
            try:
                image_repo.remove("generated-images", [storage_key])
            except Exception:
                logger.warning("Failed to remove NSFW image %s from storage", storage_key)
            await _fail_job(job_repo, job_id, job_data, FAILURE_NSFW, supabase=supabase)
            return None

    # Download source for identity check
    async with httpx.AsyncClient() as client:
        resp = await client.get(source_url)
        resp.raise_for_status()
        source_image_bytes = resp.content

    # Identity check — uses in-memory bytes, not provider URLs
    loop = asyncio.get_running_loop()
    identity_result = await loop.run_in_executor(
        None,
        check_identity,
        source_image_bytes,
        gen_image_bytes,
        settings.IDENTITY_SIMILARITY_THRESHOLD,
    )

    # Identity failed → retry once
    if not identity_result.identity_preserved:
        logger.info("Identity check failed (%.3f < %.2f) — retrying with tighter params",
                    identity_result.similarity_score, settings.IDENTITY_SIMILARITY_THRESHOLD)

        retry_options = GenerationOptions(
            model=settings.FAL_MODEL_PRIMARY,
            prompt=prompt,
            negative_prompt=negative,
            reference_image_url=source_url,
            id_weight=min(adaptive_params["id_weight"] + 0.10, 0.95),
            guidance_scale=max(adaptive_params["guidance_scale"] - 0.5, 3.5),
            num_inference_steps=adaptive_params["num_inference_steps"],
        )

        retry_result = await generator.generate(source_url, prompt, retry_options)

        if retry_result.estimated_cost_usd:
            await cost_tracker.record_cost(retry_result.estimated_cost_usd)

        # Download retry image from provider and overwrite storage
        async with httpx.AsyncClient() as client:
            resp = await client.get(retry_result.image_url)
            resp.raise_for_status()
            retry_image_bytes = resp.content

        image_repo.update_file("generated-images", storage_key, retry_image_bytes, "image/jpeg")

        retry_identity = await loop.run_in_executor(
            None,
            check_identity,
            source_image_bytes,
            retry_image_bytes,
            settings.IDENTITY_SIMILARITY_THRESHOLD,
        )

        if retry_identity.identity_preserved:
            gen_result = retry_result
            gen_image_bytes = retry_image_bytes
            identity_result = retry_identity
        else:
            # Clean up stored image on identity failure
            try:
                image_repo.remove("generated-images", [storage_key])
            except Exception:
                logger.warning("Failed to remove image %s after identity failure", storage_key)
            await _fail_job(job_repo, job_id, job_data, FAILURE_IDENTITY,
                            identity_score=retry_identity.similarity_score,
                            supabase=supabase)
            return None

    return gen_result, gen_image_bytes, source_image_bytes, identity_result


async def _finalize_job(
    job_repo: JobRepository,
    image_repo: ImageRepository,
    ledger: object,
    job_id: str,
    job_data: dict,
    user_id: str,
    storage_key: str,
    gen_result: object,
    gen_image_bytes: bytes,
    source_image_bytes: bytes,
    identity_result: object,
    options: GenerationOptions,
) -> None:
    """Color-normalize output, persist image row, commit credit, mark job completed."""
    import PIL.Image

    gen_img = PIL.Image.open(io.BytesIO(gen_image_bytes))
    source_img_pil = PIL.Image.open(io.BytesIO(source_image_bytes))

    gen_img = normalize_output(source_img_pil, gen_img)

    output_buffer = io.BytesIO()
    gen_img.save(output_buffer, format="JPEG", quality=95)
    output_bytes = output_buffer.getvalue()

    # Overwrite with color-normalized version
    image_repo.update_file("generated-images", storage_key, output_bytes, "image/jpeg")

    # Create images row for generated image
    gen_image_row = image_repo.create({
        "user_id": user_id,
        "storage_key": storage_key,
        "bucket": "generated-images",
        "image_type": "generated_after",
        "status": "cleared",
    })

    gen_image_id = gen_image_row.get("id") if gen_image_row else None

    # Commit credit
    if job_data.get("credit_reservation_id"):
        ledger.commit(UUID(job_data["credit_reservation_id"]))

    # Update job → completed
    job_repo.update(job_id, {
        "status": JobStatus.COMPLETED,
        "generated_image_id": gen_image_id,
        "identity_similarity_score": identity_result.similarity_score,
        "identity_preserved": True,
        "estimated_cost_usd": gen_result.estimated_cost_usd,
        "model_used": options.model,
        "updated_at": datetime.now(tz=timezone.utc).isoformat(),
    })


async def process_generation_job(ctx: dict, job_id: str) -> None:
    """Full generation lifecycle orchestrator.

    1. Fetch job + source image
    2. Build prompt from analysis
    3. Call generator (GlowUpGeneratorPort)
    4. Write generated image to NXME storage (fal.ai URL not used after this)
    5. NSFW screen output (from in-memory bytes)
    6. ArcFace identity check (from in-memory bytes)
    7. Color normalization + overwrite in storage
    8. Commit credit, update job → COMPLETED
    """
    supabase: Client = ctx["supabase"]
    redis = ctx["redis"]
    cost_tracker = CostTracker(redis)
    generator = _get_generator()
    job_repo = JobRepository(supabase)
    image_repo = ImageRepository(supabase)
    analysis_repo = AnalysisRepository(supabase)
    from app.entitlement.ledger import CreditLedger
    ledger = CreditLedger(supabase)
    user_id_for_concurrent: str | None = None

    # Fetch job data FIRST — needed for credit release in all failure paths (P2-6)
    job_data = await _fetch_and_claim_job(job_repo, cost_tracker, job_id, supabase)
    if job_data is None:
        return

    try:
        user_id = job_data["user_id"]
        user_id_for_concurrent = user_id

        # Concurrent guard — INCR at job start, DECR in all exit paths
        concurrent_key = f"concurrent:{user_id}"
        await redis.incr(concurrent_key)
        await redis.expire(concurrent_key, settings.GENERATION_TIMEOUT_SECONDS + 60)

        options, source_url, adaptive_params, prompt = await _build_generation_context(
            job_repo, image_repo, analysis_repo, job_data
        )

        storage_key = f"{user_id}/{job_id}.jpg"

        validate_result = await _generate_and_validate(
            job_repo, image_repo, cost_tracker, generator,
            job_id, job_data, options, source_url, adaptive_params,
            prompt, options.negative_prompt, storage_key, user_id, supabase,
        )
        if validate_result is None:
            return

        gen_result, gen_image_bytes, source_image_bytes, identity_result = validate_result

        await _finalize_job(
            job_repo, image_repo, ledger,
            job_id, job_data, user_id, storage_key,
            gen_result, gen_image_bytes, source_image_bytes,
            identity_result, options,
        )

        # Record success for circuit breaker
        await cost_tracker.record_success()

        logger.info("Job %s completed: identity=%.3f, cost=$%.4f",
                    job_id, identity_result.similarity_score,
                    gen_result.estimated_cost_usd or 0)

    except Exception as exc:
        logger.exception("Job %s failed: %s", job_id, exc)
        await cost_tracker.record_failure()
        await _fail_job(job_repo, job_id, job_data if 'job_data' in locals() else {}, FAILURE_PROVIDER, supabase=supabase)
    finally:
        # Always DECR concurrent counter
        if user_id_for_concurrent:
            await redis.decr(f"concurrent:{user_id_for_concurrent}")


async def _fail_job(
    job_repo: JobRepository,
    job_id: str,
    job_data: dict,
    failure_reason: str,
    identity_score: float | None = None,
    supabase: Client | None = None,
) -> None:
    """Fail a job: release credit, update status."""
    # Release credit reservation
    if job_data.get("credit_reservation_id") and supabase is not None:
        try:
            from app.entitlement.ledger import CreditLedger
            _ledger = CreditLedger(supabase)
            _ledger.release(UUID(job_data["credit_reservation_id"]))
        except Exception as exc:
            logger.error("Failed to release credit for job %s: %s", job_id, exc)

    update: dict = {
        "status": JobStatus.FAILED,
        "failure_reason": failure_reason,
        "updated_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    if identity_score is not None:
        update["identity_similarity_score"] = identity_score
        update["identity_preserved"] = False

    job_repo.update(job_id, update)
    logger.info("Job %s failed: %s", job_id, failure_reason)


# ---------------------------------------------------------------------------
# Stuck-job watchdog
# ---------------------------------------------------------------------------


async def watchdog_stuck_jobs(ctx: dict) -> None:
    """Cron: recover jobs stuck in 'processing' beyond timeout."""
    supabase: Client = ctx["supabase"]
    job_repo = JobRepository(supabase)
    threshold = datetime.now(tz=timezone.utc) - timedelta(
        seconds=settings.GENERATION_TIMEOUT_SECONDS + 30
    )

    stuck_jobs = job_repo.get_stuck_jobs(threshold.isoformat())

    for job in stuck_jobs:
        logger.warning("Recovering stuck job %s", job["id"])
        await _fail_job(job_repo, job["id"], job, FAILURE_TIMEOUT, supabase=supabase)
