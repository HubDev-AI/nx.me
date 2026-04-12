"""Analysis API — upload selfie for face analysis.

Story 3-3:
  POST /analyses     — upload selfie, run image pipeline + face analysis, return result
  GET  /analyses/{id} — retrieve analysis by ID (owner only)

Thin wiring layer: ImagePipeline.process() → FaceAnalysisService.analyze() → DB write.
Errors from pipeline/analysis propagate as HTTPException automatically.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel

from app.api.deps import get_analysis_repo, get_analysis_user, get_current_user
from app.api.middleware.auth import UserClaims
from app.config import settings
from app.db.async_helpers import run_sync
from app.face_analysis.service import FaceAnalysisService
from app.image_pipeline.pipeline import ImagePipeline
from app.repositories.analysis_repo import AnalysisRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analyses"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class SuggestionResponse(BaseModel):
    rank: int
    category: str
    suggestion: str  # maps from Suggestion.suggestion_text


class AnalysisResponse(BaseModel):
    analysis_id: str
    face_shape: str
    symmetry_score: float
    recommendations: list[SuggestionResponse]
    status: str


class AnalysisDetailResponse(AnalysisResponse):
    created_at: str


# ---------------------------------------------------------------------------
# POST /analyses
# ---------------------------------------------------------------------------


@router.post("/analyses", response_model=AnalysisResponse, status_code=status.HTTP_201_CREATED)
async def create_analysis(
    request: Request,
    file: UploadFile,
    claims: UserClaims = Depends(get_analysis_user),
    analysis_repo: AnalysisRepository = Depends(get_analysis_repo),
) -> Response:
    """Upload a selfie for face analysis.

    AC-1: Pipeline runs ImagePipeline.process() (NSFW gate) then
          FaceAnalysisService.analyze(); analyses row created; 201 returned.
    AC-2: Quarantined images raise HTTPException 422 from pipeline — analyze() never called.
    AC-4: Face validation failures raise HTTPException 422 from analysis service.
    """
    supabase = request.app.state.supabase
    user_id: str = claims["sub"]
    file_bytes = await file.read()
    content_type = file.content_type or "application/octet-stream"

    # Step 1: Image pipeline — validate, NSFW screen, strip metadata, store
    # Raises HTTPException 422 on failure (format, size, quarantine)
    pipeline = ImagePipeline(supabase)
    processed = await pipeline.process(file_bytes, content_type, user_id)

    # Step 2: Face analysis — extract landmarks, classify, score, recommend
    # Raises HTTPException 422 on failure (no face, multiple faces, etc.)
    analysis_svc = FaceAnalysisService(supabase)
    result = await analysis_svc.analyze(processed.storage_key)

    # Step 3: Write analyses row
    analysis_id = uuid4()
    now_utc = datetime.now(tz=timezone.utc).isoformat()

    recs_json = [
        {
            "rank": s.rank,
            "category": s.category,
            "suggestion_text": s.suggestion_text,
            "rationale": s.rationale,
        }
        for s in result.recommendations
    ]

    try:
        await run_sync(
            analysis_repo.insert,
            {
                "id": str(analysis_id),
                "user_id": user_id,
                "original_image_id": str(processed.image_id),
                "face_shape": result.face_shape.value,
                "symmetry_score": result.symmetry_score,
                "recommendations": recs_json,
                "status": "completed",
                "created_at": now_utc,
                "updated_at": now_utc,
            },
        )
    except Exception as exc:
        logger.error("analyses INSERT failed for user %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save analysis result. Please retry.",
        ) from exc

    logger.info("Analysis %s created for user %s (shape=%s)", analysis_id, user_id, result.face_shape)

    # Post-analysis nudge hook (spec Section 16: one integration point, guarded by ADVISOR_ENABLED)
    if settings.ADVISOR_ENABLED:
        try:
            arq_pool = getattr(request.app.state, "arq_pool", None)
            if arq_pool is not None:
                await arq_pool.enqueue_job(
                    "schedule_post_analysis_nudge",
                    user_id,
                    _queue_name="default",
                )
                logger.debug("Enqueued post-analysis nudge for user %s", user_id)
        except Exception as _exc:
            # Non-critical — never let nudge scheduling block the response
            logger.warning("Post-analysis nudge hook failed for user %s: %s", user_id, _exc)

    from fastapi.responses import JSONResponse

    payload = AnalysisResponse(
        analysis_id=str(analysis_id),
        face_shape=result.face_shape.value,
        symmetry_score=result.symmetry_score,
        recommendations=[
            SuggestionResponse(
                rank=s.rank,
                category=s.category,
                suggestion=s.suggestion_text,
            )
            for s in result.recommendations
        ],
        status="completed",
    )
    return JSONResponse(
        content=payload.model_dump(),
        status_code=status.HTTP_201_CREATED,
        headers={"Location": f"/v1/analyses/{analysis_id}"},
    )


# ---------------------------------------------------------------------------
# GET /analyses/{id}
# ---------------------------------------------------------------------------


@router.get("/analyses/{analysis_id}", response_model=AnalysisDetailResponse)
async def get_analysis(
    analysis_id: UUID,
    claims: UserClaims = Depends(get_current_user),
    analysis_repo: AnalysisRepository = Depends(get_analysis_repo),
) -> AnalysisDetailResponse:
    """Retrieve an analysis by ID. Owner only (AC-3)."""
    user_id: str = claims["sub"]

    row = await run_sync(analysis_repo.get_by_id, str(analysis_id))

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found",
        )

    if row["user_id"] != user_id:
        # H-3: Return 404 (not 403) to prevent ownership enumeration
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found",
        )

    recs = row.get("recommendations") or []

    return AnalysisDetailResponse(
        analysis_id=row["id"],
        face_shape=row["face_shape"],
        symmetry_score=row["symmetry_score"],
        recommendations=[
            SuggestionResponse(
                rank=r["rank"],
                category=r["category"],
                suggestion=r["suggestion_text"],
            )
            for r in recs
        ],
        status=row["status"],
        created_at=row["created_at"],
    )
