"""Glowup API — feature-namespaced routes under /uploads/{id}/glowup/.

Phase 2:
  POST /uploads/{upload_id}/glowup/analyze  — face analysis, 428 without consent.
  POST /uploads/{upload_id}/glowup/generate — enqueue generation job.

Thin wiring layer: GlowupService + existing generation logic handle business logic.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel

from app.analytics import events
from app.api.deps import (
    get_user_or_guest,
    get_credit_ledger,
    get_entitlement_service,
    get_glowup_service,
    get_job_repo,
    get_redis,
)
from app.api.middleware.auth import UserClaims
from app.config import settings
from app.constants.tiers import SLUG_TO_DB_TIER, SLUG_TO_TIER_NAME
from app.db.async_helpers import run_sync
from app.entitlement.ledger import CreditLedger
from app.entitlement.models import (
    ENTITLEMENT_ERROR_MESSAGES,
    PAYMENT_REQUIRED_CODES,
    TIER_CONCURRENT_LIMIT,
)
from app.entitlement.service import EntitlementService
from app.generation.cost_tracker import CostTracker
from app.generation.models import (
    JobStatus,
    LANE_CREDIT,
    LANE_PREMIUM,
    LANE_TRIAL,
)
from app.repositories.job_repo import SOURCE_TYPE_GLOWUP, JobRepository
from app.services.glowup_service import GlowupService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["glowup"])

# Maps tier slug → queue lane
_SLUG_TO_LANE: dict[str, str] = {
    "free": LANE_TRIAL,
    "credits": LANE_CREDIT,
    "premium": LANE_PREMIUM,
}

# Maps tier slug → public display name (for API responses)
_SLUG_TO_TIER_NAME = SLUG_TO_TIER_NAME

# Maps tier slug → DB enum value (for user_tier_at_enqueue column)
_SLUG_TO_DB_TIER = SLUG_TO_DB_TIER

# Error messages for entitlement failures
_ERROR_MESSAGES = ENTITLEMENT_ERROR_MESSAGES


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class SuggestionResponse(BaseModel):
    rank: int
    category: str
    suggestion: str  # maps from suggestion_text


class AnalyzeResponse(BaseModel):
    glowup_analysis_id: str
    face_shape: str
    symmetry_score: float
    recommendations: list[SuggestionResponse]


class GenerateRequest(BaseModel):
    idempotency_key: str | None = None


class GenerateResponse(BaseModel):
    job_id: str
    status: str
    estimated_wait_seconds: int
    queue_position: int


# ---------------------------------------------------------------------------
# Shared helpers (mirrored from generation.py — both used until old file gone)
# ---------------------------------------------------------------------------


async def _check_entitlement(
    ent_svc: EntitlementService,
    user_id: UUID,
) -> None:
    """Verify the user is allowed to generate.

    Raises HTTPException 409 for concurrent limit, 402 for payment required.
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

    http_status_code = 402 if ent_result.error_code in PAYMENT_REQUIRED_CODES else 429
    raise HTTPException(
        status_code=http_status_code,
        detail={
            "error": {
                "code": ent_result.error_code,
                "message": _ERROR_MESSAGES.get(
                    ent_result.error_code or "", "Entitlement check failed"
                ),
                "detail": {
                    "limit": ent_result.limit,
                    "used": ent_result.used,
                    "retry_after": ent_result.retry_after.isoformat()
                    if ent_result.retry_after
                    else None,
                    "reset_in_seconds": ent_result.reset_in_seconds,
                    "upgrade_available": ent_result.upgrade_available,
                },
            }
        },
    )


async def _preflight_checks(
    cost_tracker: CostTracker,
    ent_svc: EntitlementService,
    user_id: UUID,
    user_id_str: str,
):
    """Run cost-tracker pre-flight gates and return the user's tier."""
    _service_unavailable = {
        "error": {
            "code": "SERVICE_UNAVAILABLE",
            "message": "Generation service temporarily unavailable. Please try again.",
        }
    }

    if await cost_tracker.is_emergency_stopped():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_service_unavailable
        )

    if not await cost_tracker.check_queue_depth(settings.MAX_QUEUE_DEPTH):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_service_unavailable
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

    tier = await ent_svc.get_tier(user_id)

    if tier.slug == "free" and await cost_tracker.should_throttle_trial():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_service_unavailable
        )

    return tier


async def _check_idempotency(
    job_repo: JobRepository,
    idempotency_key: str,
    user_id_str: str,
) -> GenerateResponse | None:
    """Return an existing GenerateResponse if this key was already processed."""
    existing = await run_sync(
        job_repo.get_by_idempotency_key, idempotency_key, user_id_str
    )
    if existing:
        return GenerateResponse(
            job_id=existing["id"],
            status=existing["status"],
            estimated_wait_seconds=0,
            queue_position=0,
        )
    return None


# ---------------------------------------------------------------------------
# POST /uploads/{upload_id}/glowup/analyze
# ---------------------------------------------------------------------------


@router.post(
    "/uploads/{upload_id}/glowup/analyze",
    response_model=AnalyzeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def analyze_glowup(
    upload_id: UUID,
    claims: UserClaims = Depends(get_user_or_guest),
    glowup_svc: GlowupService = Depends(get_glowup_service),
) -> AnalyzeResponse:
    """Run face analysis on an existing upload.

    Timing: ~3s.

    Errors:
      404 UPLOAD_NOT_FOUND    — upload does not exist or belongs to another user.
      422 FACE_NOT_DETECTED   — no face detected in the uploaded image.
      428 FACE_MOD_CONSENT_REQUIRED — user has not granted consent.
    """
    user_id: str = claims["sub"]
    upload_id_str = str(upload_id)
    _t0 = time.monotonic()

    try:
        result = await glowup_svc.create_analysis(upload_id_str, user_id)
    except HTTPException as exc:
        failure_code = "UNKNOWN"
        detail = exc.detail
        if isinstance(detail, dict):
            error_block = detail.get("error", {})
            if isinstance(error_block, dict):
                failure_code = error_block.get("code", "UNKNOWN")
        try:
            events.glowup_analyze_failed(
                upload_id=upload_id_str,
                user_id=user_id,
                failure_code=failure_code,
            )
        except Exception:
            logger.warning(
                "Analytics emit failed for glowup_analyze_failed", exc_info=True
            )
        raise

    duration_ms = int((time.monotonic() - _t0) * 1000)

    try:
        events.glowup_analyze_completed(
            glowup_analysis_id=str(result.glowup_analysis_id),
            upload_id=upload_id_str,
            user_id=user_id,
            face_shape=result.face_shape,
            symmetry_score=result.symmetry_score,
            duration_ms=duration_ms,
        )
    except Exception:
        logger.warning(
            "Analytics emit failed for glowup_analyze_completed", exc_info=True
        )

    return AnalyzeResponse(
        glowup_analysis_id=str(result.glowup_analysis_id),
        face_shape=result.face_shape,
        symmetry_score=result.symmetry_score,
        recommendations=[
            SuggestionResponse(
                rank=r["rank"],
                category=r["category"],
                suggestion=r["suggestion_text"],
            )
            for r in result.recommendations
        ],
    )


# ---------------------------------------------------------------------------
# POST /uploads/{upload_id}/glowup/generate
# ---------------------------------------------------------------------------


@router.post(
    "/uploads/{upload_id}/glowup/generate",
    response_model=GenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_glowup(
    upload_id: UUID,
    body: GenerateRequest,
    request: Request,
    idempotency_key_header: str | None = Header(None, alias="idempotency-key"),
    claims: UserClaims = Depends(get_user_or_guest),
    redis_client: aioredis.Redis = Depends(get_redis),
    ent_svc: EntitlementService = Depends(get_entitlement_service),
    job_repo: JobRepository = Depends(get_job_repo),
    ledger: CreditLedger = Depends(get_credit_ledger),
) -> GenerateResponse:
    """Enqueue a glow-up generation job for the given upload.

    Requires a completed glowup_analysis for the upload (resolved server-side).
    Idempotency: second call with the same key within 5 min returns the cached job_id.

    Timing: ~200ms (enqueue only).

    Errors:
      404 ANALYSIS_NOT_FOUND     — no completed analysis for this upload.
      402 PAYMENT_REQUIRED       — insufficient credits.
      409 CONCURRENT_LIMIT       — another job is in progress.
      428 FACE_MOD_CONSENT_REQUIRED — consent not granted.
      409 IDEMPOTENT_DUPLICATE   — returns cached job_id (not an error per se).
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

    # Check face-mod consent before expensive DB/Redis lookups.
    from app.db.async_helpers import run_sync as _run_sync

    consent_row = await _run_sync(
        lambda: (
            request.app.state.supabase.table("users")
            .select("face_mod_consent_at")
            .eq("id", user_id_str)
            .maybe_single()
            .execute()
        )
    )
    if (
        not consent_row
        or not consent_row.data
        or not consent_row.data.get("face_mod_consent_at")
    ):
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail={
                "error": {
                    "code": "FACE_MOD_CONSENT_REQUIRED",
                    "message": "You must grant face-mod consent before generating.",
                }
            },
        )

    # Resolve the glowup_analysis for this upload (server-side FK lookup).
    from app.repositories.glowup_analysis_repo import GlowupAnalysisRepository

    analysis_repo = GlowupAnalysisRepository(request.app.state.supabase)
    analysis = await _run_sync(analysis_repo.get_by_upload_id, str(upload_id))
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "ANALYSIS_NOT_FOUND",
                    "message": "No face analysis found for this upload. Run /glowup/analyze first.",
                }
            },
        )

    # Verify upload ownership.
    from app.repositories.upload_repo import UploadRepository

    upload_repo = UploadRepository(request.app.state.supabase)
    upload = await _run_sync(
        upload_repo.get_by_id_for_owner_check, str(upload_id), user_id_str
    )
    if not upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found",
        )

    idempotency_response = await _check_idempotency(
        job_repo, idempotency_key, user_id_str
    )
    if idempotency_response:
        return idempotency_response

    # _check_entitlement atomically acquires a concurrent slot on success.
    # Every downstream failure path (preflight, reservation, enqueue) must
    # release the slot; otherwise users can leak slots up to the TTL.
    await _check_entitlement(ent_svc, user_id)

    reservation_id: UUID | None = None
    try:
        cost_tracker = CostTracker(redis_client)
        tier = await _preflight_checks(cost_tracker, ent_svc, user_id, user_id_str)

        queue_lane = _SLUG_TO_LANE.get(tier.slug, LANE_TRIAL)
        tier_name = _SLUG_TO_DB_TIER.get(tier.slug, tier.slug.upper())
        # ARQ stores pending jobs in a sorted set at the queue name
        # (default "arq:queue"); LLEN on a ZSET returns 0, so the previous
        # "arq:queue:{queue_lane}" key always reported 0 depth. Until the
        # multi-queue worker lands, report the actual shared queue depth.
        raw_position = await redis_client.zcard("arq:queue")
        if raw_position <= 5:
            queue_position = raw_position
        elif raw_position <= 50:
            queue_position = (raw_position // 10) * 10
        else:
            queue_position = (raw_position // 50) * 50

        # Reserve credit and enqueue.
        if tier.credits_based:
            reservation_id = ledger.reserve(user_id)

        job_id = uuid4()
        now_utc = datetime.now(tz=timezone.utc).isoformat()
        usage_status = "reserved" if tier.credits_based else "committed"

        await run_sync(
            job_repo.create,
            {
                "id": str(job_id),
                "user_id": user_id_str,
                "source_type": SOURCE_TYPE_GLOWUP,
                "source_id": analysis["id"],
                # before_image_url: the upload's storage key (used by worker + GET /jobs/{id})
                "before_image_url": upload.get("image_url", ""),
                "credit_reservation_id": str(reservation_id)
                if reservation_id
                else None,
                "user_tier_at_enqueue": tier_name,
                "status": JobStatus.QUEUED,
                "idempotency_key": idempotency_key,
                "created_at": now_utc,
                "updated_at": now_utc,
            },
        )

        await run_sync(
            job_repo.insert_usage_event,
            {
                "user_id": user_id_str,
                "action": "generation",
                "status": usage_status,
                "job_id": str(job_id),
            },
        )

        await request.app.state.arq_pool.enqueue_job(
            "process_generation_job",
            str(job_id),
        )
    except Exception:
        await redis_client.decr(f"concurrent:{user_id_str}")
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
        "Generation job %s enqueued for user %s on lane %s (upload=%s, analysis=%s)",
        job_id,
        user_id_str,
        queue_lane,
        upload_id,
        analysis["id"],
    )

    estimated_wait = queue_position * settings.AVG_SECONDS_PER_JOB
    return GenerateResponse(
        job_id=str(job_id),
        status=JobStatus.QUEUED,
        estimated_wait_seconds=estimated_wait,
        queue_position=queue_position,
    )
