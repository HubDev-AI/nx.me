"""Makeup consent gating.

``has_consent`` checks whether the user has an accepted consent row in
``makeup_analyses`` that meets the minimum version threshold.

``require_consent`` is a FastAPI dep factory; compose it on routes that
must not proceed without explicit user consent:

    @router.post("/uploads/{upload_id}/makeup/generate",
                 dependencies=[Depends(require_consent("makeup_v1"))])
    async def generate(...)

The ``/analyze`` route is intentionally NOT gated — it is the entry point
that creates the first consent row.  Subsequent calls to ``/generate``
can then verify consent is on record.
"""

from __future__ import annotations

import logging
from typing import Callable

from fastapi import Depends, HTTPException, status
from supabase import Client

from app.api.deps import get_current_user, get_supabase
from app.db.async_helpers import run_sync

logger = logging.getLogger(__name__)

# Consent version shipped with the app.  Bump when the consent text changes.
MAKEUP_CONSENT_VERSION = "1.0"

# Internal mapping: consent_key → minimum accepted version tuple.
# Extend here when additional consent types land.
_CONSENT_MIN: dict[str, tuple[int, ...]] = {
    "makeup_v1": (1, 0),
}


def _parse_version(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.split("."))
    except (ValueError, AttributeError):
        return (0,)


def has_consent(
    user_id: str, consent_key: str, min_version: str, *, supabase: Client
) -> bool:
    """Return True if the user has accepted consent_key at >= min_version.

    Reads the most recent ``makeup_analyses`` row for the user and compares
    ``consent_version`` against ``min_version`` as a dot-separated tuple.
    Returns False when no row exists (user has never run the analyzer).
    """
    if consent_key not in _CONSENT_MIN:
        logger.warning("has_consent called with unknown consent_key=%r", consent_key)
        return False

    result = (
        supabase.table("makeup_analyses")
        .select("consent_version")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(1)
        .maybe_single()
        .execute()
    )
    if not result or not result.data:
        return False

    stored = _parse_version(result.data.get("consent_version", "0"))
    required = _parse_version(min_version)
    return stored >= required


def require_consent(consent_key: str) -> Callable:
    """FastAPI dep factory: gate a route behind makeup consent.

    Raises 403 CONSENT_REQUIRED when the user has no accepted consent row
    for *consent_key* at the current minimum version.
    """

    async def _check(
        supabase: Client = Depends(get_supabase),
        claims: dict = Depends(get_current_user),
    ) -> None:
        user_id: str = claims["sub"]
        min_ver = MAKEUP_CONSENT_VERSION
        ok = await run_sync(
            has_consent, user_id, consent_key, min_ver, supabase=supabase
        )
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": {
                        "code": "CONSENT_REQUIRED",
                        "message": "Makeup feature requires explicit consent.",
                        "detail": {"consent_key": consent_key},
                    }
                },
            )

    return _check
