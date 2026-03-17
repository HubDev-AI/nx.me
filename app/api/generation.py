"""Generation API — trigger, poll, and cancel glow-up jobs.

Story 4-3:
  POST /analyses/{analysis_id}/generate — entitlement check, credit reserve, enqueue ARQ job
  GET  /jobs/{job_id}                   — poll job status with estimated wait
  POST /jobs/{job_id}/cancel            — cancel in-flight job, release credit
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.api.deps import (
    get_analysis_repo,
    get_credit_ledger,
    get_current_user,
    get_entitlement_service,
    get_image_repo,
    get_job_repo,
    get_redis,
)
from app.api.middleware.auth import UserClaims
from app.config import settings
from app.constants.tiers import CREDIT_HOLDER, PREMIUM, SLUG_TO_TIER_NAME, TRIAL
from app.db.async_helpers import run_sync
from app.entitlement.ledger import CreditLedger
from app.entitlement.models import ENTITLEMENT_ERROR_MESSAGES, PAYMENT_REQUIRED_CODES, TIER_CONCURRENT_LIMIT
from app.entitlement.service import EntitlementService
from app.generation.cost_tracker import CostTracker
from app.generation.models import (
    FAILURE_CANCELLED,
    FAILURE_IDENTITY,
    JobStatus,
    LANE_CREDIT,
    LANE_PREMIUM,
    LANE_TRIAL,
)
from app.repositories.analysis_repo import AnalysisRepository
from app.repositories.image_repo import ImageRepository
from app.repositories.job_repo import JobRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["generation"])

# Maps tier slug → queue lane
_SLUG_TO_LANE: dict[str, str] = {
    "free": LANE_TRIAL,
    "credits": LANE_CREDIT,
    "premium": LANE_PREMIUM,
}

# Maps tier slug → public tier name (for user_tier_at_enqueue column)
_SLUG_TO_TIER_NAME = SLUG_TO_TIER_NAME

# Average seconds per generation job (for wait estimation)
_AVG_SECONDS_PER_JOB = 15

# Error messages for entitlement failures
_ERROR_MESSAGES = ENTITLEMENT_ERROR_MESSAGES


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class GenerateRequest(BaseModel):
    idempotency_key: str


class GenerateResponse(BaseModel):
    job_id: str
    status: str
    estimated_wait_seconds: int
    queue_position: int


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    estimated_wait_seconds: int | None = None
    elapsed_seconds: int | None = None
    before_image_url: str | None = None
    after_image_url: str | None = None
    identity_preserved: bool | None = None
    failure_reason: str | None = None
    credit_refunded: bool | None = None
    retry_eligible: bool | None = None
    user_guidance: str | None = None


class CancelResponse(BaseModel):
    job_id: str
    status: str
    credit_refunded: bool


# ---------------------------------------------------------------------------
# POST /analyses/{analysis_id}/generate
# ---------------------------------------------------------------------------


@router.post(
    "/analyses/{analysis_id}/generate",
    response_model=GenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_generation(
    analysis_id: UUID,
    body: GenerateRequest,
    request: Request,
    claims: UserClaims = Depends(get_current_user),
    redis_client: aioredis.Redis = Depends(get_redis),
    ent_svc: EntitlementService = Depends(get_entitlement_service),
    job_repo: JobRepository = Depends(get_job_repo),
    analysis_repo: AnalysisRepository = Depends(get_analysis_repo),
    ledger: CreditLedger = Depends(get_credit_ledger),
) -> GenerateResponse:
    """Trigger a glow-up generation job.

    AC-1: Reserve credit before enqueue. AC-2: 409 on concurrent limit.
    Entitlement checked inline (not via require_entitlement dependency)
    so concurrent limit maps to 409 per AC-2.
    """
    user_id_str: str = claims["sub"]
    user_id = UUID(user_id_str)

    # --- Entitlement check (inline, not dependency — AC-2 needs 409 for concurrent) ---
    ent_result = await ent_svc.check(user_id, "generation")
    if not ent_result.allowed:
        if ent_result.error_code == TIER_CONCURRENT_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "CONCURRENT_LIMIT",
                        "message": "You already have a generation in progress.",
                    }
                },
            )
        status_code = 402 if ent_result.error_code in PAYMENT_REQUIRED_CODES else 429
        raise HTTPException(
            status_code=status_code,
            detail={
                "error": {
                    "code": ent_result.error_code,
                    "message": _ERROR_MESSAGES.get(
                        ent_result.error_code or "", "Entitlement check failed"
                    ),
                    "detail": {
                        "limit": ent_result.limit,
                        "used": ent_result.used,
                        "retry_after": ent_result.retry_after.isoformat() if ent_result.retry_after else None,
                        "reset_in_seconds": ent_result.reset_in_seconds,
                        "upgrade_available": ent_result.upgrade_available,
                    },
                }
            },
        )

    # --- Validate analysis exists, is owned, and is completed ---
    analysis_data = await run_sync(analysis_repo.get_for_generation, str(analysis_id))
    if not analysis_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found",
        )
    if analysis_data["user_id"] != user_id_str:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found",
        )
    if analysis_data["status"] != "completed":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "ANALYSIS_NOT_COMPLETED",
                    "message": "Analysis must be completed before generating.",
                }
            },
        )

    # --- Cost tracker pre-flight checks ---
    cost_tracker = CostTracker(redis_client)

    if await cost_tracker.is_emergency_stopped():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "SERVICE_UNAVAILABLE",
                    "message": "Generation service temporarily unavailable. Please try again.",
                }
            },
        )

    if not await cost_tracker.check_queue_depth(settings.MAX_QUEUE_DEPTH):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "SERVICE_UNAVAILABLE",
                    "message": "Generation service temporarily unavailable. Please try again.",
                }
            },
        )

    if not await cost_tracker.check_user_daily_cap(
        user_id_str, settings.MAX_GENERATIONS_PER_USER_PER_DAY
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": {
                    "code": "TIER_LIMIT_DAILY",
                    "message": "Daily generation limit reached",
                }
            },
        )

    # --- Get tier for queue lane and trial throttle ---
    tier = await ent_svc.get_tier(user_id)

    # Trial throttle
    if tier.slug == "free" and await cost_tracker.should_throttle_trial():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "SERVICE_UNAVAILABLE",
                    "message": "Generation service temporarily unavailable. Please try again.",
                }
            },
        )

    # --- Idempotency check ---
    existing = await run_sync(job_repo.get_by_idempotency_key, body.idempotency_key, user_id_str)
    if existing:
        return GenerateResponse(
            job_id=existing["id"],
            status=existing["status"],
            estimated_wait_seconds=0,
            queue_position=0,
        )

    # --- Determine queue lane ---
    queue_lane = _SLUG_TO_LANE.get(tier.slug, LANE_TRIAL)
    tier_name = _SLUG_TO_TIER_NAME.get(tier.slug, tier.slug.upper())

    # --- Read queue position before enqueue ---
    queue_position = await redis_client.llen(f"arq:queue:{queue_lane}")
    estimated_wait = queue_position * _AVG_SECONDS_PER_JOB

    # --- Credit reserve (for credit-based tiers) ---
    reservation_id: UUID | None = None

    if tier.credits_based:
        reservation_id = ledger.reserve(user_id)

    # --- Insert job + usage event + enqueue (with credit release on failure) ---
    job_id = uuid4()
    now_utc = datetime.now(tz=timezone.utc).isoformat()
    usage_status = "reserved" if tier.credits_based else "committed"

    try:
        # Insert glow_up_jobs first (primary record)
        await run_sync(job_repo.create, {
            "id": str(job_id),
            "user_id": user_id_str,
            "analysis_id": str(analysis_id),
            "original_image_id": analysis_data["original_image_id"],
            "credit_reservation_id": str(reservation_id) if reservation_id else None,
            "user_tier_at_enqueue": tier_name,
            "status": JobStatus.QUEUED,
            "queue_lane": queue_lane,
            "idempotency_key": body.idempotency_key,
            "created_at": now_utc,
            "updated_at": now_utc,
        })

        # Insert usage_events (tracking record)
        await run_sync(job_repo.insert_usage_event, {
            "user_id": user_id_str,
            "action": "generation",
            "status": usage_status,
            "job_id": str(job_id),
        })

        # Enqueue ARQ job
        arq_pool = request.app.state.arq_pool
        await arq_pool.enqueue_job(
            "process_generation_job",
            str(job_id),
            _queue_name=queue_lane,
        )
    except Exception:
        # Release credit reservation if any step after reserve failed
        if reservation_id:
            try:
                ledger.release(reservation_id)
            except Exception:
                logger.error(
                    "Failed to release credit reservation %s after enqueue failure",
                    reservation_id,
                )
        raise

    logger.info(
        "Generation job %s enqueued for user %s on lane %s",
        job_id, user_id_str, queue_lane,
    )

    return GenerateResponse(
        job_id=str(job_id),
        status=JobStatus.QUEUED,
        estimated_wait_seconds=estimated_wait,
        queue_position=queue_position,
    )


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}
# ---------------------------------------------------------------------------


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job(
    job_id: UUID,
    claims: UserClaims = Depends(get_current_user),
    redis_client: aioredis.Redis = Depends(get_redis),
    job_repo: JobRepository = Depends(get_job_repo),
    image_repo: ImageRepository = Depends(get_image_repo),
) -> JobStatusResponse:
    """Poll job status with estimated wait time.

    AC-3: Failure reason reflected. AC-5: estimated_wait_seconds returned.
    """
    user_id_str: str = claims["sub"]

    job = await run_sync(job_repo.get_for_status_poll, str(job_id))
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    if job["user_id"] != user_id_str:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    job_status = job["status"]

    # --- Queued / Processing: compute estimated wait ---
    estimated_wait: int | None = None
    elapsed: int | None = None

    if job_status in (JobStatus.QUEUED, JobStatus.PROCESSING):
        queue_lane = job["queue_lane"]
        queued_ahead = await redis_client.llen(f"arq:queue:{queue_lane}")

        if job_status == JobStatus.QUEUED:
            estimated_wait = queued_ahead * _AVG_SECONDS_PER_JOB
        else:
            updated_at = datetime.fromisoformat(job["updated_at"])
            elapsed = max(0, int((datetime.now(tz=timezone.utc) - updated_at).total_seconds()))
            estimated_wait = max(0, _AVG_SECONDS_PER_JOB - elapsed)

    # --- Completed: generate signed URLs ---
    before_url: str | None = None
    after_url: str | None = None
    identity_preserved: bool | None = None

    if job_status == JobStatus.COMPLETED:
        identity_preserved = job.get("identity_preserved")

        # Get original image storage key
        original_img = await run_sync(
            image_repo.get_by_id_with_fields,
            job["original_image_id"],
            "storage_key",
        )
        if original_img and original_img.get("storage_key"):
            before_url = await run_sync(
                image_repo.create_signed_url,
                "raw-selfies",
                original_img["storage_key"],
                settings.SIGNED_URL_EXPIRY_SECONDS,
            )

        # Get generated image storage key
        if job.get("generated_image_id"):
            gen_img = await run_sync(
                image_repo.get_by_id_with_fields,
                job["generated_image_id"],
                "storage_key",
            )
            if gen_img and gen_img.get("storage_key"):
                after_url = await run_sync(
                    image_repo.create_signed_url,
                    "generated-images",
                    gen_img["storage_key"],
                    settings.SIGNED_URL_EXPIRY_SECONDS,
                )

    # --- Failed: include refund and retry info ---
    credit_refunded: bool | None = None
    retry_eligible: bool | None = None
    user_guidance: str | None = None

    if job_status == JobStatus.FAILED:
        # Only report credit_refunded if the job actually had a credit reservation
        credit_refunded = job.get("credit_reservation_id") is not None
        retry_eligible = job.get("failure_reason") in (
            FAILURE_IDENTITY,
            "GENERATION_TIMEOUT",
            "PROVIDER_ERROR",
        )
        if job.get("failure_reason") == FAILURE_IDENTITY:
            user_guidance = "Try a clearer photo or a less dramatic style."

    # --- Cancelled: include refund info ---
    if job_status == JobStatus.CANCELLED:
        credit_refunded = job.get("credit_reservation_id") is not None

    return JobStatusResponse(
        job_id=str(job_id),
        status=job_status,
        estimated_wait_seconds=estimated_wait,
        elapsed_seconds=elapsed,
        before_image_url=before_url,
        after_image_url=after_url,
        identity_preserved=identity_preserved,
        failure_reason=job.get("failure_reason"),
        credit_refunded=credit_refunded,
        retry_eligible=retry_eligible,
        user_guidance=user_guidance,
    )


# ---------------------------------------------------------------------------
# POST /jobs/{job_id}/cancel
# ---------------------------------------------------------------------------


@router.post("/jobs/{job_id}/cancel", response_model=CancelResponse)
async def cancel_job(
    job_id: UUID,
    claims: UserClaims = Depends(get_current_user),
    job_repo: JobRepository = Depends(get_job_repo),
    ledger: CreditLedger = Depends(get_credit_ledger),
) -> CancelResponse:
    """Cancel an in-flight generation job.

    AC-4: Release credit, transition to cancelled.
    """
    user_id_str: str = claims["sub"]

    job = await run_sync(job_repo.get_for_cancel, str(job_id))
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    if job["user_id"] != user_id_str:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    terminal_statuses = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}

    if job["status"] in terminal_statuses:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "JOB_NOT_CANCELLABLE",
                    "message": "Job is already completed.",
                }
            },
        )

    # --- Update job to cancelled ---
    now_utc = datetime.now(tz=timezone.utc).isoformat()
    await run_sync(job_repo.update, str(job_id), {
        "status": JobStatus.CANCELLED,
        "failure_reason": FAILURE_CANCELLED,
        "updated_at": now_utc,
    })

    # --- Release credit if reserved ---
    credit_refunded = False
    if job.get("credit_reservation_id"):
        try:
            ledger.release(UUID(job["credit_reservation_id"]))
            credit_refunded = True
        except ValueError:
            logger.warning(
                "Credit release failed for reservation %s (already resolved)",
                job["credit_reservation_id"],
            )

    # --- Update usage_events ---
    await run_sync(job_repo.update_usage_event, str(job_id), {"status": "released"})

    logger.info("Job %s cancelled by user %s", job_id, user_id_str)

    return CancelResponse(
        job_id=str(job_id),
        status=JobStatus.CANCELLED,
        credit_refunded=credit_refunded,
    )
