"""User consent API — face modification consent endpoint.

Phase 2 / Q17:
  POST /users/me/face-mod-consent — set face_mod_consent_at = NOW(). Idempotent.

DB-backed: stores the timestamp in users.face_mod_consent_at so the server
can gate POST /uploads/{id}/glowup/analyze and POST /uploads/{id}/glowup/generate.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi import status as http_status
from pydantic import BaseModel

from app.analytics import events
from app.api.deps import get_user_or_guest
from app.api.middleware.auth import UserClaims
from app.db.async_helpers import run_sync

logger = logging.getLogger(__name__)

router = APIRouter(tags=["users"])


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class FaceModConsentResponse(BaseModel):
    consented_at: str


# ---------------------------------------------------------------------------
# POST /users/me/face-mod-consent
# ---------------------------------------------------------------------------


@router.post(
    "/users/me/face-mod-consent",
    response_model=FaceModConsentResponse,
    status_code=http_status.HTTP_200_OK,
)
async def grant_face_mod_consent(
    request: Request,
    claims: UserClaims = Depends(get_user_or_guest),
) -> FaceModConsentResponse:
    """Grant face modification consent for the current user.

    Sets users.face_mod_consent_at to NOW() if not already set.
    Idempotent: already-consented users receive their original consented_at back.
    """
    user_id: str = claims["sub"]
    supabase = request.app.state.supabase

    # Fetch current value first — avoid overwriting an existing timestamp.
    existing_row = await run_sync(
        lambda: (
            supabase.table("users")
            .select("face_mod_consent_at")
            .eq("id", user_id)
            .maybe_single()
            .execute()
        )
    )

    existing_consent = (
        existing_row.data.get("face_mod_consent_at")
        if existing_row and existing_row.data
        else None
    )

    if existing_consent:
        # Already consented — return the original timestamp (idempotent).
        logger.debug(
            "User %s already has face_mod_consent_at=%s", user_id, existing_consent
        )
        return FaceModConsentResponse(consented_at=existing_consent)

    # First consent — set the timestamp.
    now_utc = datetime.now(tz=timezone.utc).isoformat()
    await run_sync(
        lambda: (
            supabase.table("users")
            .update({"face_mod_consent_at": now_utc})
            .eq("id", user_id)
            .execute()
        )
    )

    logger.info("Face-mod consent recorded for user %s at %s", user_id, now_utc)

    try:
        events.glowup_consent_granted(user_id=user_id)
    except Exception:
        logger.warning(
            "Analytics emit failed for glowup_consent_granted", exc_info=True
        )

    return FaceModConsentResponse(consented_at=now_utc)
