"""Generation API — trigger, poll, cancel, and refund glow-up jobs.

Story 4-3:
  POST /analyses/{analysis_id}/generate — entitlement check, credit reserve, enqueue ARQ job
  GET  /jobs/{job_id}                   — poll job status with estimated wait
  POST /jobs/{job_id}/cancel            — cancel in-flight job, release credit
  POST /jobs/{job_id}/refund            — refund completed/failed job, return credit
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
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
from app.constants.tiers import SLUG_TO_TIER_NAME
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

# M-3: Average seconds per generation job moved to app/config/__init__.py

# Error messages for entitlement failures
_ERROR_MESSAGES = ENTITLEMENT_ERROR_MESSAGES


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class GenerateRequest(BaseModel):
    idempotency_key: str | None = None


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


class RefundResponse(BaseModel):
    job_id: str
    status: str
    credit_refunded: bool


# ---------------------------------------------------------------------------
# POST /analyses/{analysis_id}/generate
# ---------------------------------------------------------------------------


async def _check_entitlement(
    ent_svc: EntitlementService,
    user_id: UUID,
) -> None:
    """Verify the user is allowed to generate.

    Raises HTTPException with 409 for concurrent limit (AC-2), 402 for payment
    required, or 429 for other rate limits.
    """
    ent_result = await ent_svc.check(user_id, "generation")
    if ent_result.allowed:
        return

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

    http_status = 402 if ent_result.error_code in PAYMENT_REQUIRED_CODES else 429
    raise HTTPException(
        status_code=http_status,
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


async def _validate_analysis(
    analysis_repo: AnalysisRepository,
    analysis_id: UUID,
    user_id_str: str,
) -> dict:
    """Fetch the analysis and verify ownership and completion status.

    Returns the analysis row dict.
    Raises HTTPException 404 if not found or not owned, 422 if not completed.
    """
    analysis_data = await run_sync(analysis_repo.get_for_generation, str(analysis_id))
    if not analysis_data or analysis_data["user_id"] != user_id_str:
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
    return analysis_data


async def _preflight_checks(
    cost_tracker: CostTracker,
    ent_svc: EntitlementService,
    user_id: UUID,
    user_id_str: str,
):
    """Run cost-tracker pre-flight gates and return the user's tier.

    Checks: emergency stop, queue depth, daily cap, trial throttle.
    Raises HTTPException 503 or 429 on failure.
    Returns the tier object from EntitlementService.
    """
    _service_unavailable = {
        "error": {
            "code": "SERVICE_UNAVAILABLE",
            "message": "Generation service temporarily unavailable. Please try again.",
        }
    }

    if await cost_tracker.is_emergency_stopped():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_service_unavailable)

    if not await cost_tracker.check_queue_depth(settings.MAX_QUEUE_DEPTH):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_service_unavailable)

    if not await cost_tracker.check_user_daily_cap(user_id_str, settings.MAX_GENERATIONS_PER_USER_PER_DAY):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": {
                    "code": "TIER_LIMIT_DAILY",
                    "message": "Daily generation limit reached",
                }
            },
        )

    tier = await ent_svc.get_tier(user_id)

    if tier.slug == "free" and await cost_tracker.should_throttle_trial():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_service_unavailable)

    return tier


async def _check_idempotency(
    job_repo: JobRepository,
    idempotency_key: str,
    user_id_str: str,
) -> GenerateResponse | None:
    """Return an existing GenerateResponse if this key was already processed, else None."""
    existing = await run_sync(job_repo.get_by_idempotency_key, idempotency_key, user_id_str)
    if existing:
        return GenerateResponse(
            job_id=existing["id"],
            status=existing["status"],
            estimated_wait_seconds=0,
            queue_position=0,
        )
    return None


async def _enqueue_job(
    job_repo: JobRepository,
    arq_pool,
    ledger: CreditLedger,
    user_id: UUID,
    user_id_str: str,
    analysis_id: UUID,
    analysis_data: dict,
    tier,
    queue_lane: str,
    tier_name: str,
    idempotency_key: str,
    queue_position: int,
) -> GenerateResponse:
    """Reserve credit (if applicable), create the job row, log usage, and enqueue to ARQ.

    Releases the credit reservation if any subsequent step fails.
    Returns the GenerateResponse for the newly created job.
    """
    reservation_id: UUID | None = None
    if tier.credits_based:
        reservation_id = ledger.reserve(user_id)

    job_id = uuid4()
    now_utc = datetime.now(tz=timezone.utc).isoformat()
    usage_status = "reserved" if tier.credits_based else "committed"

    try:
        await run_sync(job_repo.create, {
            "id": str(job_id),
            "user_id": user_id_str,
            "analysis_id": str(analysis_id),
            "original_image_id": analysis_data["original_image_id"],
            "credit_reservation_id": str(reservation_id) if reservation_id else None,
            "user_tier_at_enqueue": tier_name,
            "status": JobStatus.QUEUED,
            "queue_lane": queue_lane,
            "idempotency_key": idempotency_key,
            "created_at": now_utc,
            "updated_at": now_utc,
        })

        await run_sync(job_repo.insert_usage_event, {
            "user_id": user_id_str,
            "action": "generation",
            "status": usage_status,
            "job_id": str(job_id),
        })

        await arq_pool.enqueue_job(
            "process_generation_job",
            str(job_id),
            _queue_name=queue_lane,
        )
    except Exception:
        if reservation_id:
            try:
                ledger.release(reservation_id)
            except Exception:
                logger.error(
                    "Failed to release credit reservation %s after enqueue failure",
                    reservation_id,
                )
        raise

    logger.info("Generation job %s enqueued for user %s on lane %s", job_id, user_id_str, queue_lane)

    estimated_wait = queue_position * settings.AVG_SECONDS_PER_JOB
    return GenerateResponse(
        job_id=str(job_id),
        status=JobStatus.QUEUED,
        estimated_wait_seconds=estimated_wait,
        queue_position=queue_position,
    )


@router.post(
    "/analyses/{analysis_id}/generate",
    response_model=GenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_generation(
    analysis_id: UUID,
    body: GenerateRequest,
    request: Request,
    idempotency_key_header: str | None = Header(None, alias="idempotency-key"),
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

    idempotency_key = idempotency_key_header or body.idempotency_key
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "MISSING_IDEMPOTENCY_KEY",
                    "message": "Idempotency-Key header or body.idempotency_key is required",
                }
            },
        )

    await _check_entitlement(ent_svc, user_id)
    analysis_data = await _validate_analysis(analysis_repo, analysis_id, user_id_str)

    cost_tracker = CostTracker(redis_client)
    tier = await _preflight_checks(cost_tracker, ent_svc, user_id, user_id_str)

    idempotency_response = await _check_idempotency(job_repo, idempotency_key, user_id_str)
    if idempotency_response:
        return idempotency_response

    queue_lane = _SLUG_TO_LANE.get(tier.slug, LANE_TRIAL)
    tier_name = _SLUG_TO_TIER_NAME.get(tier.slug, tier.slug.upper())
    raw_position = await redis_client.llen(f"arq:queue:{queue_lane}")
    if raw_position <= 5:
        queue_position = raw_position
    elif raw_position <= 50:
        queue_position = (raw_position // 10) * 10
    else:
        queue_position = (raw_position // 50) * 50

    return await _enqueue_job(
        job_repo=job_repo,
        arq_pool=request.app.state.arq_pool,
        ledger=ledger,
        user_id=user_id,
        user_id_str=user_id_str,
        analysis_id=analysis_id,
        analysis_data=analysis_data,
        tier=tier,
        queue_lane=queue_lane,
        tier_name=tier_name,
        idempotency_key=idempotency_key,
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
            estimated_wait = queued_ahead * settings.AVG_SECONDS_PER_JOB
        else:
            updated_at = datetime.fromisoformat(job["updated_at"])
            elapsed = max(0, int((datetime.now(tz=timezone.utc) - updated_at).total_seconds()))
            estimated_wait = max(0, settings.AVG_SECONDS_PER_JOB - elapsed)

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


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=CancelResponse,
    status_code=status.HTTP_200_OK,
    deprecated=True,
)
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


# ---------------------------------------------------------------------------
# POST /jobs/{job_id}/refund
# ---------------------------------------------------------------------------


@router.post(
    "/jobs/{job_id}/refund",
    response_model=RefundResponse,
    status_code=status.HTTP_200_OK,
)
async def refund_job(
    job_id: UUID,
    claims: UserClaims = Depends(get_current_user),
    job_repo: JobRepository = Depends(get_job_repo),
    ledger: CreditLedger = Depends(get_credit_ledger),
) -> RefundResponse:
    """Refund a completed or failed generation job.

    Releases the credit reservation if the job had one, returning
    the credit to the user's balance.

    Only allowed for jobs in completed or failed status. Cancelled jobs
    already have their credits released at cancellation time. Pending
    and processing jobs should be cancelled instead.
    """
    user_id_str: str = claims["sub"]

    job = await run_sync(job_repo.get_for_refund, str(job_id))
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    if job["user_id"] != user_id_str:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorised to refund this job",
        )

    # Idempotency guard: reject if this job was already refunded (prevents double-spend)
    usage_status = await run_sync(job_repo.get_usage_event_status, str(job_id))
    if usage_status in ("refunded", "released"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "ALREADY_REFUNDED",
                    "message": "This job has already been refunded.",
                }
            },
        )

    refundable_statuses = {JobStatus.COMPLETED, JobStatus.FAILED}

    if job["status"] not in refundable_statuses:
        if job["status"] == JobStatus.CANCELLED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "ALREADY_REFUNDED",
                        "message": "Cancelled jobs are automatically refunded.",
                    }
                },
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "JOB_NOT_REFUNDABLE",
                    "message": f"Job in '{job['status']}' status cannot be refunded. Cancel it instead.",
                }
            },
        )

    # --- Refund credit reservation ---
    credit_refunded = False
    if job.get("credit_reservation_id"):
        reservation_id = UUID(job["credit_reservation_id"])

        # Try refund (committed -> released) first, then release (reserved -> released)
        # as a fallback for edge cases where the reservation was never committed.
        try:
            ledger.refund(reservation_id)
            credit_refunded = True
        except ValueError:
            # Reservation not in committed state — try release in case it's
            # still reserved (e.g. worker failed before committing).
            try:
                ledger.release(reservation_id)
                credit_refunded = True
            except ValueError:
                logger.warning(
                    "Credit refund/release failed for reservation %s (already resolved)",
                    job["credit_reservation_id"],
                )

    # --- Update usage_events ---
    await run_sync(job_repo.update_usage_event, str(job_id), {"status": "refunded"})

    logger.info("Job %s refunded by user %s (credit_refunded=%s)", job_id, user_id_str, credit_refunded)

    return RefundResponse(
        job_id=str(job_id),
        status=job["status"],
        credit_refunded=credit_refunded,
    )
