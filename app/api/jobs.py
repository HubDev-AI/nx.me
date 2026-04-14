"""Jobs API — poll, save, cancel, and refund generation jobs.

Phase 2:
  GET  /jobs/{job_id}         — poll job status with estimated wait.
  POST /jobs/{job_id}/save    — mark job as saved (indefinite retention, Q12).
  POST /jobs/{job_id}/cancel  — cancel in-flight job, release credit.
  POST /jobs/{job_id}/refund  — refund completed/failed job, return credit.

Replaces the generation.py routes that previously served GET/cancel/refund.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.analytics import events
from app.api.deps import (
    get_user_or_guest,
    get_credit_ledger,
    get_current_user,
    get_job_repo,
    get_redis,
)
from app.api.middleware.auth import UserClaims
from app.config import settings
from app.db.async_helpers import run_sync
from app.entitlement.ledger import CreditLedger
from app.generation.models import (
    FAILURE_CANCELLED,
    FAILURE_IDENTITY,
    JobStatus,
)
from app.repositories.job_repo import JobRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jobs"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


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
    saved_at: str | None = None


class SaveResponse(BaseModel):
    saved_at: str


class CancelResponse(BaseModel):
    job_id: str
    status: str
    credit_refunded: bool


class RefundResponse(BaseModel):
    job_id: str
    status: str
    credit_refunded: bool


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}
# ---------------------------------------------------------------------------


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job(
    job_id: UUID,
    request: Request,
    claims: UserClaims = Depends(get_user_or_guest),
    redis_client: aioredis.Redis = Depends(get_redis),
    job_repo: JobRepository = Depends(get_job_repo),
) -> JobStatusResponse:
    """Poll job status with estimated wait time.

    Polling-safe: always returns 200, never 404 for in-progress jobs that
    exist but the caller doesn't own — returns 404 to prevent enumeration.
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

    # Queued / Processing: compute estimated wait
    estimated_wait: int | None = None
    elapsed: int | None = None

    if job_status in (JobStatus.QUEUED, JobStatus.PROCESSING):
        # ARQ stores pending jobs in a sorted set at the default queue name
        # ("arq:queue"). The previous LLEN on "arq:queue:default" always
        # returned 0 (wrong key + wrong type), so users saw zero estimated
        # wait even under load.
        queued_ahead = await redis_client.zcard("arq:queue")

        if job_status == JobStatus.QUEUED:
            estimated_wait = queued_ahead * settings.AVG_SECONDS_PER_JOB
        else:
            updated_at = datetime.fromisoformat(job["updated_at"])
            elapsed = max(
                0, int((datetime.now(tz=timezone.utc) - updated_at).total_seconds())
            )
            estimated_wait = max(0, settings.AVG_SECONDS_PER_JOB - elapsed)

    # Completed: sign the storage keys stored in before_image_url / after_image_url.
    # The job row stores storage keys (not public URLs); sign them on demand.
    before_url: str | None = None
    after_url: str | None = None
    identity_preserved: bool | None = None

    if job_status == JobStatus.COMPLETED:
        identity_preserved = job.get("identity_preserved")
        from app.db.async_helpers import run_sync as _run_sync
        from app.repositories.image_repo import ImageRepository

        image_repo = ImageRepository(request.app.state.supabase)
        if job.get("before_image_url"):
            before_url = await _run_sync(
                image_repo.create_signed_url,
                "raw-selfies",
                job["before_image_url"],
                settings.SIGNED_URL_EXPIRY_SECONDS,
            )
        if job.get("after_image_url"):
            after_url = await _run_sync(
                image_repo.create_signed_url,
                "generated-images",
                job["after_image_url"],
                settings.SIGNED_URL_EXPIRY_SECONDS,
            )

    # Failed: include refund and retry info
    credit_refunded: bool | None = None
    retry_eligible: bool | None = None
    user_guidance: str | None = None

    if job_status == JobStatus.FAILED:
        credit_refunded = job.get("credit_reservation_id") is not None
        retry_eligible = job.get("failure_reason") in (
            FAILURE_IDENTITY,
            "GENERATION_TIMEOUT",
            "PROVIDER_ERROR",
        )
        if job.get("failure_reason") == FAILURE_IDENTITY:
            user_guidance = "Try a clearer photo or a less dramatic style."

    if job_status == JobStatus.CANCELLED:
        credit_refunded = job.get("credit_reservation_id") is not None

    saved_at_raw = job.get("saved_at")
    saved_at_str: str | None = saved_at_raw if isinstance(saved_at_raw, str) else None

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
        saved_at=saved_at_str,
    )


# ---------------------------------------------------------------------------
# POST /jobs/{job_id}/save
# ---------------------------------------------------------------------------


@router.post(
    "/jobs/{job_id}/save",
    response_model=SaveResponse,
    status_code=status.HTTP_200_OK,
)
async def save_job(
    job_id: UUID,
    claims: UserClaims = Depends(get_user_or_guest),
    job_repo: JobRepository = Depends(get_job_repo),
) -> SaveResponse:
    """Mark a completed generation job as saved (indefinite retention, Q12).

    Idempotent: second call returns the original saved_at timestamp.
    Only completed jobs can be saved.
    """
    user_id_str: str = claims["sub"]

    result = await run_sync(job_repo.save, str(job_id), user_id_str)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    saved_at = result.get("saved_at") or datetime.now(tz=timezone.utc).isoformat()

    try:
        events.glowup_save(job_id=str(job_id), user_id=user_id_str)
    except Exception:
        logger.warning("Analytics emit failed for glowup_save", exc_info=True)

    return SaveResponse(saved_at=saved_at)


# ---------------------------------------------------------------------------
# POST /jobs/{job_id}/cancel
# ---------------------------------------------------------------------------


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=CancelResponse,
    status_code=status.HTTP_200_OK,
)
async def cancel_job(
    job_id: UUID,
    claims: UserClaims = Depends(get_user_or_guest),
    job_repo: JobRepository = Depends(get_job_repo),
    ledger: CreditLedger = Depends(get_credit_ledger),
) -> CancelResponse:
    """Cancel an in-flight generation job.

    Releases credit reservation and transitions the job to cancelled.
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

    now_utc = datetime.now(tz=timezone.utc).isoformat()
    await run_sync(
        job_repo.update,
        str(job_id),
        {
            "status": JobStatus.CANCELLED,
            "failure_reason": FAILURE_CANCELLED,
            "updated_at": now_utc,
        },
    )

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

    Releases the credit reservation, returning the credit to the user's balance.
    Idempotent via usage_event status check.
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

    # Idempotency guard: reject if this job was already refunded
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

    credit_refunded = False
    if job.get("credit_reservation_id"):
        reservation_id = UUID(job["credit_reservation_id"])
        try:
            ledger.refund(reservation_id)
            credit_refunded = True
        except ValueError:
            try:
                ledger.release(reservation_id)
                credit_refunded = True
            except ValueError:
                logger.warning(
                    "Credit refund/release failed for reservation %s (already resolved)",
                    job["credit_reservation_id"],
                )

    await run_sync(job_repo.update_usage_event, str(job_id), {"status": "refunded"})

    logger.info(
        "Job %s refunded by user %s (credit_refunded=%s)",
        job_id,
        user_id_str,
        credit_refunded,
    )

    return RefundResponse(
        job_id=str(job_id),
        status=job["status"],
        credit_refunded=credit_refunded,
    )
