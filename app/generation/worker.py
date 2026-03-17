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
from app.generation.identity_checker import check_identity
from app.generation.models import (
    FAILURE_IDENTITY,
    FAILURE_NSFW,
    FAILURE_PROVIDER,
    FAILURE_TIMEOUT,
    GenerationOptions,
    JobStatus,
)
from app.generation.prompt_builder import build_prompt

logger = logging.getLogger(__name__)


def _get_generator():
    """Resolve generator adapter from config (lazy import)."""
    if settings.ADAPTER__IMAGE_GENERATION_ADAPTER == "falai":
        from app.generation.adapters.falai import FalAiAdapter
        return FalAiAdapter()
    from app.generation.adapters.mock import MockGeneratorAdapter
    return MockGeneratorAdapter()


async def process_generation_job(ctx: dict, job_id: str) -> None:
    """Full generation lifecycle.

    1. Fetch job + source image
    2. Build prompt from analysis
    3. Call generator (GlowUpGeneratorPort)
    4. NSFW screen output
    5. ArcFace identity check
    6. Wow score + optional second candidate
    7. Write to storage
    8. Commit credit, update job → COMPLETED
    """
    supabase: Client = ctx["supabase"]
    redis = ctx["redis"]
    cost_tracker = CostTracker(redis)
    generator = _get_generator()

    # Update job → processing
    now_utc = datetime.now(tz=timezone.utc).isoformat()
    supabase.table("glow_up_jobs").update({
        "status": JobStatus.PROCESSING,
        "updated_at": now_utc,
    }).eq("id", job_id).execute()

    try:
        # Fetch job data
        job = supabase.table("glow_up_jobs").select("*").eq("id", job_id).single().execute()
        if not job.data:
            logger.error("Job %s not found", job_id)
            return

        job_data = job.data
        user_id = job_data["user_id"]

        # Fetch analysis for prompt building
        analysis = None
        if job_data.get("analysis_id"):
            analysis_row = (
                supabase.table("analyses")
                .select("face_shape, symmetry_score, recommendations")
                .eq("id", job_data["analysis_id"])
                .single()
                .execute()
            )
            if analysis_row.data:
                from app.face_analysis.models import AnalysisResult, FaceShape, Suggestion
                recs = analysis_row.data.get("recommendations") or []
                analysis = AnalysisResult(
                    face_shape=FaceShape(analysis_row.data["face_shape"]),
                    symmetry_score=analysis_row.data["symmetry_score"],
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
        source_img = (
            supabase.table("images")
            .select("storage_key, bucket")
            .eq("id", job_data["original_image_id"])
            .single()
            .execute()
        )
        source_url = supabase.storage.from_(source_img.data["bucket"]).create_signed_url(
            source_img.data["storage_key"], 300
        )["signedURL"]

        # Build generation options
        options = GenerationOptions(
            model=settings.FAL_MODEL_PRIMARY,
            prompt=prompt,
            negative_prompt=negative,
            reference_image_url=source_url,
            id_weight=adaptive_params["id_weight"],
            guidance_scale=adaptive_params["guidance_scale"],
            num_inference_steps=adaptive_params["num_inference_steps"],
        )

        # Generate
        gen_result = await generator.generate(source_url, prompt, options)

        # Track cost
        if gen_result.estimated_cost_usd:
            await cost_tracker.record_cost(gen_result.estimated_cost_usd)
            await cost_tracker.increment_user_daily(user_id)

        # NSFW screen output
        if settings.ADAPTER__NSFW_ADAPTER == "rekognition":
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(gen_result.image_url)
                gen_image_bytes = resp.content

            from app.image_pipeline.nsfw_screener import RekognitionAdapter
            screener = RekognitionAdapter()
            nsfw_result = await screener.screen(gen_image_bytes)

            if nsfw_result.is_explicit:
                await _fail_job(supabase, job_id, job_data, FAILURE_NSFW)
                return
        else:
            # Download generated image for identity check
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(gen_result.image_url)
                gen_image_bytes = resp.content

        # Download source for identity check
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(source_url)
            source_image_bytes = resp.content

        # Identity check
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

            async with httpx.AsyncClient() as client:
                resp = await client.get(retry_result.image_url)
                retry_image_bytes = resp.content

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
                await _fail_job(supabase, job_id, job_data, FAILURE_IDENTITY,
                                identity_score=retry_identity.similarity_score)
                return

        # Write generated image to storage
        import PIL.Image
        gen_img = PIL.Image.open(io.BytesIO(gen_image_bytes))
        source_img_pil = PIL.Image.open(io.BytesIO(source_image_bytes))

        # Color normalization
        gen_img = normalize_output(source_img_pil, gen_img)

        # Save to buffer
        output_buffer = io.BytesIO()
        gen_img.save(output_buffer, format="JPEG", quality=95)
        output_bytes = output_buffer.getvalue()

        # Upload to generated-images bucket
        storage_key = f"{user_id}/{job_id}.jpg"
        supabase.storage.from_("generated-images").upload(
            path=storage_key,
            file=output_bytes,
            file_options={"content-type": "image/jpeg"},
        )

        # Create images row for generated image
        gen_image_row = supabase.table("images").insert({
            "user_id": user_id,
            "storage_key": storage_key,
            "bucket": "generated-images",
            "image_type": "generated_after",
            "status": "cleared",
        }).execute()

        gen_image_id = gen_image_row.data[0]["id"] if gen_image_row.data else None

        # Commit credit
        if job_data.get("credit_reservation_id"):
            from app.entitlement.ledger import CreditLedger
            ledger = CreditLedger(supabase)
            ledger.commit(UUID(job_data["credit_reservation_id"]))

        # Update job → completed
        supabase.table("glow_up_jobs").update({
            "status": JobStatus.COMPLETED,
            "generated_image_id": gen_image_id,
            "identity_similarity_score": identity_result.similarity_score,
            "identity_preserved": True,
            "estimated_cost_usd": gen_result.estimated_cost_usd,
            "model_used": options.model,
            "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        }).eq("id", job_id).execute()

        logger.info("Job %s completed: identity=%.3f, cost=$%.4f",
                      job_id, identity_result.similarity_score,
                      gen_result.estimated_cost_usd or 0)

    except Exception as exc:
        logger.exception("Job %s failed: %s", job_id, exc)
        await _fail_job(supabase, job_id, job_data if 'job_data' in locals() else {}, FAILURE_PROVIDER)


async def _fail_job(
    supabase: Client,
    job_id: str,
    job_data: dict,
    failure_reason: str,
    identity_score: float | None = None,
) -> None:
    """Fail a job: release credit, update status."""
    # Release credit reservation
    if job_data.get("credit_reservation_id"):
        try:
            from app.entitlement.ledger import CreditLedger
            ledger = CreditLedger(supabase)
            ledger.release(UUID(job_data["credit_reservation_id"]))
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

    supabase.table("glow_up_jobs").update(update).eq("id", job_id).execute()
    logger.info("Job %s failed: %s", job_id, failure_reason)


# ---------------------------------------------------------------------------
# Stuck-job watchdog
# ---------------------------------------------------------------------------


async def watchdog_stuck_jobs(ctx: dict) -> None:
    """Cron: recover jobs stuck in 'processing' beyond timeout."""
    supabase: Client = ctx["supabase"]
    threshold = datetime.now(tz=timezone.utc) - timedelta(
        seconds=settings.GENERATION_TIMEOUT_SECONDS + 30
    )

    stuck = (
        supabase.table("glow_up_jobs")
        .select("id, credit_reservation_id")
        .eq("status", JobStatus.PROCESSING)
        .lt("updated_at", threshold.isoformat())
        .execute()
    )

    for job in stuck.data or []:
        logger.warning("Recovering stuck job %s", job["id"])
        await _fail_job(supabase, job["id"], job, FAILURE_TIMEOUT)
