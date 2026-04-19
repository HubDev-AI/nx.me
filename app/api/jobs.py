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
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.analytics import events
from app.api.deps import (
    get_user_or_guest,
    get_credit_ledger,
    get_current_user,
    get_image_repo,
    get_job_repo,
    get_orphaned_analyses_repo,
    get_orphaned_storage_repo,
    get_post_repo,
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
from app.repositories.image_repo import ImageRepository
from app.repositories.job_repo import JobRepository, SOURCE_TYPE_GLOWUP
from app.repositories.orphaned_analyses_repo import OrphanedAnalysesRepository
from app.repositories.orphaned_storage_repo import OrphanedStorageKeyRepository
from app.repositories.post_repo import PostRepository
from app.services.blob_cleanup import wipe_blob_or_record_orphan
from app.services.rate_limiter import check_delete_glowup_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jobs"])


# Reason string recorded in ``orphaned_storage_keys`` when a blob wipe
# fails during DELETE /v1/jobs/{job_id}. Mirrors ``"delete_account"`` from
# ``delete_account`` — purely server-side; never derived from user input.
DELETE_GLOWUP_REASON = "delete_glowup"

# Statuses from which a glow-up can be hard-deleted. In-flight statuses
# (queued/processing/finalizing) must be cancelled first so we do not
# race the ARQ worker. Diverges from ``cancel_job`` (which flips
# non-terminal jobs to cancelled); here we refuse them entirely.
_DELETABLE_JOB_STATUSES: frozenset[str] = frozenset(
    {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
)

# Peer statuses that should *NOT* keep a shared ``glowup_analyses`` row
# alive. A cancelled peer already released its reservation and is, for
# ref-counting purposes, gone. Other non-terminal + completed + failed
# peers DO keep the analysis so re-generation off the same analysis
# stays possible (see plan §Key Technical Decisions, "peers" paragraph).
_CANCELLED_PEER_STATUSES: frozenset[str] = frozenset({JobStatus.CANCELLED})


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
    # Populated only when ``status == COMPLETED`` AND a live post
    # (``is_deleted = FALSE AND is_hidden = FALSE``) exists for this
    # job. Mobile uses them to (a) hide the Publish row when already
    # published, (b) decide whether to append the card-web URL in
    # Share, (c) build the hash-URL for result-card Share.
    post_id: str | None = None
    share_hash: str | None = None


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
    post_repo: PostRepository = Depends(get_post_repo),
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

    # Dev repro harness — simulate read-after-write replica lag so the mobile
    # waiting view's grace + hard-timeout branches can be deterministically
    # exercised. Default 0 (off) in production.
    if settings.DEV_GLOWUP_FORCE_404_FOR_NEW_JOBS_SECONDS > 0:
        created_at_raw = job.get("created_at")
        if created_at_raw:
            created_at = datetime.fromisoformat(created_at_raw)
            elapsed = (datetime.now(tz=timezone.utc) - created_at).total_seconds()
            if elapsed < settings.DEV_GLOWUP_FORCE_404_FOR_NEW_JOBS_SECONDS:
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
    # R4/R5/R9 — attached only when a live post exists for this job so the
    # client can gate Publish and build a non-broken share URL.
    post_id: str | None = None
    share_hash: str | None = None

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

        active_post = await run_sync(
            post_repo.get_active_by_glow_up_job_id, str(job_id)
        )
        if active_post:
            post_id = active_post.get("id")
            share_hash = active_post.get("share_hash")

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
        post_id=post_id,
        share_hash=share_hash,
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


# ---------------------------------------------------------------------------
# DELETE /jobs/{job_id} — hard-cascade the glow-up and everything it produced.
# ---------------------------------------------------------------------------


# ORDER MATTERS: enumerate blob keys BEFORE DELETE FROM jobs — the FK cascade
# drops posts/images rows, and the join to find storage keys dies with them.
@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: UUID,
    claims: UserClaims = Depends(get_user_or_guest),
    redis_client: aioredis.Redis = Depends(get_redis),
    job_repo: JobRepository = Depends(get_job_repo),
    image_repo: ImageRepository = Depends(get_image_repo),
    orphan_repo: OrphanedStorageKeyRepository = Depends(get_orphaned_storage_repo),
    orphan_analyses_repo: OrphanedAnalysesRepository = Depends(
        get_orphaned_analyses_repo
    ),
) -> Response:
    """Hard-delete a glow-up, its post (if any), and every owned blob.

    ORDER MATTERS: enumerate blob keys BEFORE DELETE FROM jobs — the FK
    cascade drops posts/images rows, and the join to find storage keys
    dies with them.

    Cascade chain (reverse-chronological in effect):
      1. Rate-limit gate (per-caller, 10/min).
      2. Status gate: ``completed | failed | cancelled`` only. In-flight
         jobs must be cancelled first via ``POST /jobs/{id}/cancel``.
      3. Enumerate ``(bucket, key)`` for every blob this job owns —
         raw-selfies, generated-images, and (if a live post exists)
         post-images. ``JobRepository.enumerate_blob_keys_for_delete``
         does the post lookup internally to keep this handler tidy.
      4. Ref-count the shared ``glowup_analyses`` row via peer jobs.
         Cancelled peers do not count; any other peer keeps the analysis
         alive for re-generation. Only glow-up sources are considered —
         future ``makeup_session`` source_types route elsewhere.
      5. Issue the single ``DELETE FROM jobs`` — FK cascade wipes posts,
         reactions, comments, reports, credit_reservations,
         prompt_experiments.
      6. If peers=0 and source is a glowup, delete the analysis row.
      7. Inline blob wipe per key — on exception, record to
         ``orphaned_storage_keys`` with ``reason=DELETE_GLOWUP_REASON``
         (nightly reclaim worker drains it).
      8. Emit ``events.glowup_delete`` (swallow-wrapped like glowup_save).

    Response posture — **intentional divergence from sibling /jobs
    endpoints**: missing job + wrong-owner + already-deleted all return
    204. This mirrors ``delete_account`` and satisfies the idempotency
    invariant from ``docs/solutions/best-practices/account-delete-hard-
    reset-invariant-2026-04-18.md`` — destructive ops that are retried
    must not surface 404 on the second call, or clients cannot tell
    success from "never existed". GET/cancel/refund/save return 404 on
    wrong-owner; DELETE here deliberately does not.
    """
    user_id_str: str = claims["sub"]

    # 1. Rate-limit gate (before any DB work so a sweep can't wedge DLQ).
    allowed, retry_after = await check_delete_glowup_rate_limit(
        user_id_str, redis_client
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many glow-up deletions. Try again in a moment.",
            headers={"Retry-After": str(retry_after)},
        )

    job_id_str = str(job_id)

    # 2a. Fetch job. Missing → idempotent 204 (mirrors delete_account).
    job = await run_sync(job_repo.get_by_id, job_id_str)
    if not job:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # 2b. Wrong owner → 204 (see docstring for the divergence rationale).
    if job.get("user_id") != user_id_str:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # 2c. Status gate. Non-terminal statuses must be cancelled first so
    # the DB DELETE does not race the ARQ worker writing back results.
    job_status = job.get("status")
    if job_status not in _DELETABLE_JOB_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "JOB_NOT_CANCELLABLE",
                    "message": (
                        "This glow-up is still in progress. Cancel it first, "
                        "then try again."
                    ),
                }
            },
        )

    # 3. Enumerate blob keys BEFORE cascade. If this step is skipped or
    # reordered after the DELETE, the post-images keys (denormalized on
    # ``posts.before_image_url``/``after_image_url``) vanish with the
    # cascaded row and the blobs orphan silently.
    blob_keys = await run_sync(job_repo.enumerate_blob_keys_for_delete, job_id_str)

    # 4. Ref-count peer jobs sharing this source_id. Only relevant for
    # ``glowup_analysis`` source_type — other polymorphic sources own
    # their own lifecycle and must not be touched by this endpoint.
    source_type = job.get("source_type")
    source_id = job.get("source_id")
    delete_analysis = False
    if source_type == SOURCE_TYPE_GLOWUP and source_id:
        peer_count = await run_sync(
            job_repo.count_peer_jobs_for_source,
            source_id,
            exclude_id=job_id_str,
            exclude_statuses=set(_CANCELLED_PEER_STATUSES),
        )
        if peer_count == 0:
            delete_analysis = True

    # 5. DB cascade. Single DELETE fans out via FK cascade.
    await run_sync(job_repo.delete_by_id, job_id_str)

    # 6. Analysis row — no FK cascade, explicit delete after we know the
    # jobs row is gone.
    if delete_analysis:
        try:
            await run_sync(job_repo.delete_analysis_by_id, source_id)
        except Exception as exc:  # noqa: BLE001
            # Don't fail the request — analysis orphan is recoverable
            # (plan §Risks acknowledges; a future reclaim worker drains
            # the DLQ). Record the orphan so the sweeper has a durable
            # handle; ``record`` is itself defensive and never raises.
            logger.warning(
                "delete_glowup: analysis row delete failed for %s: %s — "
                "recording to DLQ",
                source_id,
                exc,
            )
            await run_sync(orphan_analyses_repo.record, source_id, DELETE_GLOWUP_REASON)

    # 7. Inline blob wipe. Per-key so a single failing key lands in the
    # DLQ alone — batching the whole list would force us to DLQ every
    # key on a single storage blip. Shared helper keeps retention +
    # delete_job in lock-step on the wipe-or-DLQ contract.
    for bucket, key in blob_keys:
        await wipe_blob_or_record_orphan(
            image_repo, orphan_repo, bucket, key, DELETE_GLOWUP_REASON
        )

    # 8. Emit analytics (swallow-wrapped — analytics failure must not fail
    # a destructive path that already committed).
    try:
        events.glowup_delete(job_id=job_id_str, user_id=user_id_str)
    except Exception:
        logger.warning("Analytics emit failed for glowup_delete", exc_info=True)

    logger.info("Glow-up %s hard-deleted by user %s", job_id_str, user_id_str)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
