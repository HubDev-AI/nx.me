"""Credit refund endpoint for failed or cancelled generation jobs.

POST /v1/analyses/{job_id}/refund

Idempotent: returns 200 {refunded: true, new_balance: N} on first successful
refund of a failed/cancelled job.
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi import status as http_status
from pydantic import BaseModel

from app.api.deps import get_credit_ledger, get_current_user, get_job_repo
from app.api.errors import raise_api_error
from app.api.middleware.auth import UserClaims
from app.db.async_helpers import run_sync
from app.entitlement.ledger import CreditLedger
from app.generation.models import JobStatus
from app.repositories.job_repo import JobRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["refund"])


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class RefundJobResponse(BaseModel):
    refunded: bool
    new_balance: int


# ---------------------------------------------------------------------------
# POST /v1/analyses/{job_id}/refund
# ---------------------------------------------------------------------------


@router.post(
    "/analyses/{job_id}/refund",
    response_model=RefundJobResponse,
    status_code=http_status.HTTP_200_OK,
)
async def refund_analysis_job(
    job_id: UUID,
    claims: UserClaims = Depends(get_current_user),
    job_repo: JobRepository = Depends(get_job_repo),
    ledger: CreditLedger = Depends(get_credit_ledger),
) -> RefundJobResponse:
    """Refund a failed or cancelled generation job.

    Releases the credit reservation if the job had one, returning
    the credit to the user's balance and returning the new balance.

    Only allowed for jobs in failed or cancelled status. Completed jobs
    must be refunded via the existing /v1/jobs/{job_id}/refund endpoint.

    Error codes:
      - job_not_found (404): Job does not exist.
      - forbidden (403): Caller is not the job owner.
      - already_refunded (409): Job was already refunded.
      - refund_not_applicable (409): Job is not in a refundable state.
    """
    user_id_str: str = claims["sub"]

    job = await run_sync(job_repo.get_for_refund, str(job_id))
    if not job:
        raise_api_error(
            http_status.HTTP_404_NOT_FOUND,
            "job_not_found",
            "Job not found.",
        )

    if job["user_id"] != user_id_str:
        raise_api_error(
            http_status.HTTP_403_FORBIDDEN,
            "forbidden",
            "Not authorised to refund this job.",
        )

    # Idempotency guard — reject if already refunded (prevents double-spend)
    usage_status = await run_sync(job_repo.get_usage_event_status, str(job_id))
    if usage_status in ("refunded", "released"):
        raise_api_error(
            http_status.HTTP_409_CONFLICT,
            "already_refunded",
            "This job has already been refunded.",
        )

    # Only failed and cancelled jobs are eligible for this endpoint
    refundable_statuses = {JobStatus.FAILED, JobStatus.CANCELLED}
    if job["status"] not in refundable_statuses:
        raise_api_error(
            http_status.HTTP_409_CONFLICT,
            "refund_not_applicable",
            f"Only failed or cancelled jobs can be refunded. Job is '{job['status']}'.",
        )

    # --- Refund credit reservation if present ---
    if job.get("credit_reservation_id"):
        reservation_id = UUID(job["credit_reservation_id"])
        # Try refund (committed -> released) first, then release (reserved -> released)
        # as a fallback for edge cases where the reservation was never committed.
        try:
            ledger.refund(reservation_id)
        except ValueError:
            try:
                ledger.release(reservation_id)
            except ValueError:
                logger.warning(
                    "Credit refund/release failed for reservation %s (already resolved)",
                    job["credit_reservation_id"],
                )

    # --- Mark usage_event as refunded ---
    await run_sync(job_repo.update_usage_event, str(job_id), {"status": "refunded"})

    # --- Fetch updated balance ---
    new_balance = await run_sync(ledger.balance, UUID(user_id_str))

    logger.info(
        "Job %s refunded by user %s (new_balance=%s)", job_id, user_id_str, new_balance
    )

    return RefundJobResponse(refunded=True, new_balance=new_balance)
