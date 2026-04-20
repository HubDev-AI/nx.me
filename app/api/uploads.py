"""Uploads API — POST /uploads (shared upload primitive).

Story R4 / Phase 2:
  POST /uploads — upload image, run NSFW gate, return upload_id + face_detected.

Thin wiring layer: UploadService handles all business logic.
Errors from pipeline propagate as HTTPException automatically.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.analytics import events
from app.api.deps import get_current_user, get_upload_service
from app.api.middleware.auth import UserClaims
from app.services.upload_service import UploadService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["uploads"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class UploadResponse(BaseModel):
    upload_id: str
    face_detected: bool


# ---------------------------------------------------------------------------
# POST /uploads
# ---------------------------------------------------------------------------


@router.post(
    "/uploads",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_upload(
    request: Request,
    file: UploadFile,
    claims: UserClaims = Depends(get_current_user),
    upload_svc: UploadService = Depends(get_upload_service),
) -> JSONResponse:
    """Upload a selfie image.

    Runs the ImagePipeline (NSFW gate, format validation, metadata strip,
    storage write) and returns the upload_id + face_detected flag.

    AC-1: NSFW-quarantined images raise HTTPException 422 — analyze() never called.
    AC-2: face_detected reflects whether MediaPipe found a face during upload.

    Timing: ~500ms.
    """
    user_id: str = claims["sub"]
    file_bytes = await file.read()
    content_type = file.content_type or "application/octet-stream"

    result = await upload_svc.create_upload(file_bytes, content_type, user_id)

    try:
        events.glowup_upload_created(
            upload_id=str(result.upload_id),
            user_id=user_id,
            face_detected=result.face_detected,
        )
    except Exception:
        logger.warning("Analytics emit failed for glowup_upload_created", exc_info=True)

    payload = UploadResponse(
        upload_id=str(result.upload_id),
        face_detected=result.face_detected,
    )
    return JSONResponse(
        content=payload.model_dump(),
        status_code=status.HTTP_201_CREATED,
        headers={"Location": f"/v1/uploads/{result.upload_id}"},
    )
