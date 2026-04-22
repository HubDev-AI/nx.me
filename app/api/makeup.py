"""Makeup API — feature-namespaced routes under /uploads/{id}/makeup/.

Phase 2:
  POST /uploads/{upload_id}/makeup/analyze  — MST + undertone analysis, records consent.
  POST /uploads/{upload_id}/makeup/generate — enqueue makeup generation job.

Both routes require makeup_enabled feature flag + Pro tier.
/generate additionally requires consent on record (recorded by /analyze).
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.api.deps import (
    get_current_user,
    get_job_repo,
    get_redis,
    get_upload_repo,
    require_app_feature,
    require_makeup_access,
)
from app.api.middleware.auth import UserClaims
from app.api.rate_limiters.makeup_fair_use import fair_use_incr
from app.db.async_helpers import run_sync
from app.entitlement.consent import MAKEUP_CONSENT_VERSION, require_consent
from app.generation.makeup_analyzer import AnalysisError, analyze, analyzer_stale
from app.generation.models import JobStatus
from app.generation.preset_registry import get_preset
from app.repositories.job_repo import SOURCE_TYPE_MAKEUP, JobRepository
from app.repositories.makeup_analysis_repo import MakeupAnalysisRepository
from app.repositories.upload_repo import UploadRepository
from app.schemas.makeup import (
    MakeupAnalyzeResponse,
    MakeupGenerateRequest,
    MakeupGenerateResponse,
)
from app.services.rate_limiter import check_makeup_analyze_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["makeup"],
    dependencies=[
        Depends(require_app_feature("makeup_enabled")),
        Depends(require_makeup_access()),
    ],
)

_DB_TIER_PRO = "PREMIUM"

_404_UPLOAD = {
    "error": {
        "code": "UPLOAD_NOT_FOUND",
        "message": "Upload not found or does not belong to you.",
    }
}


def _body_hash(preset_slug: str, intensity: str, upload_id: str) -> str:
    payload = json.dumps(
        {"intensity": intensity, "preset_slug": preset_slug, "upload_id": upload_id},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


# ---------------------------------------------------------------------------
# POST /uploads/{upload_id}/makeup/analyze
# ---------------------------------------------------------------------------


@router.post(
    "/uploads/{upload_id}/makeup/analyze",
    response_model=MakeupAnalyzeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def analyze_makeup(
    upload_id: UUID,
    request: Request,
    claims: UserClaims = Depends(get_current_user),
    redis_client: aioredis.Redis = Depends(get_redis),
    upload_repo: UploadRepository = Depends(get_upload_repo),
) -> MakeupAnalyzeResponse:
    """Run makeup analysis on an existing upload.

    Records consent (writes MAKEUP_CONSENT_VERSION to makeup_analyses row).
    Does NOT require prior consent — this is the entry point that creates it.

    Errors:
      404 UPLOAD_NOT_FOUND         — upload missing or belongs to another user.
      422 FACE_NOT_DETECTED        — no face found in the image.
      429 RATE_LIMITED             — > 10 analyze calls per 60s.
    """
    user_id: str = claims["sub"]

    upload = await run_sync(
        upload_repo.get_by_id_for_owner_check, str(upload_id), user_id
    )
    if not upload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_404_UPLOAD)

    allowed, retry_after = await check_makeup_analyze_rate_limit(user_id, redis_client)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(retry_after)},
            detail={
                "error": {
                    "code": "RATE_LIMITED",
                    "message": "Too many analyze requests. Please wait before trying again.",
                    "retry_after": retry_after,
                }
            },
        )

    image_url: str = upload.get("image_url", "")
    try:
        analysis = await run_sync(analyze, image_url, user_id)
    except AnalysisError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "FACE_NOT_DETECTED",
                    "message": "No face detected in the uploaded image.",
                    "detail": {"reason": exc.reason},
                }
            },
        ) from exc

    supabase = request.app.state.supabase
    analysis_repo = MakeupAnalysisRepository(supabase)

    row = await run_sync(
        analysis_repo.insert,
        {
            "user_id": user_id,
            "mst_bin": analysis.mst_bin,
            "undertone": analysis.undertone,
            "region_anchors": analysis.region_anchors,
            "preset_ranking": analysis.recommended_preset_ranking,
            "consent_version": MAKEUP_CONSENT_VERSION,
        },
    )

    return MakeupAnalyzeResponse(
        makeup_analysis_id=str(row["id"]),
        mst_bin=analysis.mst_bin,
        undertone=analysis.undertone,
        recommended_presets=analysis.recommended_preset_ranking,
    )


# ---------------------------------------------------------------------------
# POST /uploads/{upload_id}/makeup/generate
# ---------------------------------------------------------------------------


@router.post(
    "/uploads/{upload_id}/makeup/generate",
    response_model=MakeupGenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_consent("makeup_v1"))],
)
async def generate_makeup(
    upload_id: UUID,
    body: MakeupGenerateRequest,
    request: Request,
    idempotency_key_header: Annotated[
        str | None, Header(alias="idempotency-key")
    ] = None,
    claims: UserClaims = Depends(get_current_user),
    redis_client: aioredis.Redis = Depends(get_redis),
    job_repo: JobRepository = Depends(get_job_repo),
    upload_repo: UploadRepository = Depends(get_upload_repo),
) -> MakeupGenerateResponse:
    """Enqueue a makeup generation job.

    Idempotency: header wins over body field; same key + same body → 202 replay;
    same key + different body → 409 IDEMPOTENCY_KEY_CONFLICT.

    Errors:
      400 MISSING_IDEMPOTENCY_KEY       — key absent from header and body.
      400 PRESET_INVALID / PRESET_BLOCKED_FOR_BIN / PRESET_DEPRECATED
      404 UPLOAD_NOT_FOUND              — ownership check failed.
      404 ANALYSIS_NOT_FOUND            — no analyzer row for this user/upload.
      409 IDEMPOTENCY_KEY_CONFLICT      — same key, different body.
      429 RATE_LIMITED                  — daily cap exceeded.
    """
    user_id: str = claims["sub"]

    # ── 1. Capture idempotency key ──────────────────────────────────────────
    client_key = idempotency_key_header or body.idempotency_key
    if not client_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "MISSING_IDEMPOTENCY_KEY",
                    "message": "Idempotency-Key header or body.idempotency_key is required",
                }
            },
        )

    namespaced_key = f"makeup:{client_key}"
    bhash = _body_hash(body.preset_slug, body.intensity, str(upload_id))

    # ── 2. Upload ownership ─────────────────────────────────────────────────
    upload = await run_sync(
        upload_repo.get_by_id_for_owner_check, str(upload_id), user_id
    )
    if not upload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_404_UPLOAD)

    # ── 3. Load + freshness-check analyzer row ──────────────────────────────
    supabase = request.app.state.supabase
    analysis_repo = MakeupAnalysisRepository(supabase)

    analysis_row = await run_sync(analysis_repo.get_latest_for_user, user_id)
    if analysis_row is None or analyzer_stale(analysis_row):
        image_url: str = upload.get("image_url", "")
        try:
            refreshed = await run_sync(analyze, image_url, user_id)
        except AnalysisError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": {
                        "code": "FACE_NOT_DETECTED",
                        "message": "Face analysis required — no face detected in upload.",
                    }
                },
            )
        analysis_row = await run_sync(
            analysis_repo.insert,
            {
                "user_id": user_id,
                "mst_bin": refreshed.mst_bin,
                "undertone": refreshed.undertone,
                "region_anchors": refreshed.region_anchors,
                "preset_ranking": refreshed.recommended_preset_ranking,
                "consent_version": MAKEUP_CONSENT_VERSION,
            },
        )

    mst_bin: int | None = analysis_row.get("mst_bin")

    # ── 4. Validate preset + intensity ──────────────────────────────────────
    preset = get_preset(body.preset_slug)
    if preset is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "PRESET_INVALID", "message": "Unknown preset."}},
        )
    if preset.deprecated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "PRESET_DEPRECATED",
                    "message": "This preset is no longer available.",
                }
            },
        )
    if mst_bin is not None and mst_bin in preset.mst_bin_blocklist:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "PRESET_BLOCKED_FOR_BIN",
                    "message": "This preset is not available for your skin tone.",
                }
            },
        )
    if body.intensity not in preset.supported_intensities:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "PRESET_INVALID",
                    "message": f"Intensity '{body.intensity}' not supported for this preset.",
                }
            },
        )

    # ── 5. Replay check (SELECT before INCR) ────────────────────────────────
    existing = await run_sync(
        job_repo.get_makeup_job_by_idempotency_key, namespaced_key, user_id
    )
    if existing:
        stored_hash = existing.get("idempotency_key_body_hash")
        if stored_hash != bhash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "IDEMPOTENCY_KEY_CONFLICT",
                        "message": "Idempotency-Key reused with a different request body",
                    }
                },
            )
        poll_url = f"/v1/jobs/{existing['id']}"
        return MakeupGenerateResponse(
            job_id=existing["id"],
            status=existing.get("status", JobStatus.QUEUED),
            poll_url=poll_url,
        )

    # ── 6. Fair-use cap check ───────────────────────────────────────────────
    allowed, _ = await fair_use_incr(redis_client, user_id, namespaced_key)
    if not allowed:
        ttl = await redis_client.ttl(f"makeup:quota:{user_id}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(max(ttl, 1))},
            detail={
                "error": {
                    "code": "RATE_LIMITED",
                    "message": "Daily makeup generation limit reached.",
                    "retry_after": max(ttl, 1),
                }
            },
        )

    # ── 7. Pre-record ──────────────────────────────────────────────────────
    job_id = uuid4()
    now_utc = datetime.now(tz=timezone.utc).isoformat()
    job_data = {
        "id": str(job_id),
        "user_id": user_id,
        "source_type": SOURCE_TYPE_MAKEUP,
        "source_id": str(analysis_row["id"]),
        "before_image_url": upload.get("image_url", ""),
        "user_tier_at_enqueue": _DB_TIER_PRO,
        "status": JobStatus.QUEUED,
        "idempotency_key": namespaced_key,
        "idempotency_key_body_hash": bhash,
        "preset_slug": body.preset_slug,
        "intensity": body.intensity,
        "consent_version_at_enqueue": MAKEUP_CONSENT_VERSION,
        "created_at": now_utc,
        "updated_at": now_utc,
    }

    inserted = await run_sync(job_repo.pre_record_makeup_job, job_data)

    if inserted is None:
        # Concurrent-replay fallback: another identical-key request won the INSERT race.
        # Our fair_use_incr call saw already_charged=1 (txn marker existed) — counter
        # was never touched by us. No decrement needed in any branch below.
        winner = await run_sync(
            job_repo.get_makeup_job_by_idempotency_key, namespaced_key, user_id
        )
        if winner is None:
            # Extremely rare: winner's txn not yet visible (pgbouncer tx pooling).
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                headers={"Retry-After": "1"},
                detail={
                    "error": {
                        "code": "IDEMPOTENT_RACE",
                        "message": "Concurrent submission detected. Please retry.",
                    }
                },
            )

        stored_hash = winner.get("idempotency_key_body_hash")
        if stored_hash != bhash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "IDEMPOTENCY_KEY_CONFLICT",
                        "message": "Idempotency-Key reused with a different request body",
                    }
                },
            )

        poll_url = f"/v1/jobs/{winner['id']}"
        return MakeupGenerateResponse(
            job_id=winner["id"],
            status=winner.get("status", JobStatus.QUEUED),
            poll_url=poll_url,
        )

    # ── 8. Enqueue ─────────────────────────────────────────────────────────
    try:
        await request.app.state.arq_pool.enqueue_job(
            "makeup_generate",
            str(job_id),
        )
    except Exception:
        logger.error(
            "Failed to enqueue makeup_generate for job %s user %s", job_id, user_id
        )
        try:
            from app.api.rate_limiters.makeup_fair_use import fair_use_decr

            await fair_use_decr(redis_client, user_id, namespaced_key)
        except Exception:
            logger.error(
                "Fair-use decr failed after enqueue failure for user=%s", user_id
            )
        # Mark the pre-recorded row as failed so the poller gets a terminal.
        try:
            await run_sync(
                job_repo.update,
                str(job_id),
                {
                    "status": JobStatus.FAILED,
                    "makeup_failure_reason": "non_retryable",
                    "updated_at": datetime.now(tz=timezone.utc).isoformat(),
                },
            )
        except Exception:
            logger.error("Failed to mark orphaned makeup job %s as failed", job_id)
        raise

    logger.info(
        "Makeup job %s enqueued for user %s (upload=%s, preset=%s, intensity=%s)",
        job_id,
        user_id,
        upload_id,
        body.preset_slug,
        body.intensity,
    )

    poll_url = f"/v1/jobs/{job_id}"
    return MakeupGenerateResponse(
        job_id=str(job_id),
        status=JobStatus.QUEUED,
        poll_url=poll_url,
    )
