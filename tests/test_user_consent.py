"""Tests for the user consent endpoint (POST /users/me/face-mod-consent).

Exercises app/api/user_consent.py.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4


try:
    from app.api.user_consent import FaceModConsentResponse, grant_face_mod_consent

    _AVAILABLE = True
except (ImportError, AttributeError):
    _AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _AVAILABLE, reason="user_consent module unavailable"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_claims(user_id: str | None = None) -> dict:
    return {"sub": user_id or str(uuid4()), "role": "authenticated"}


def _make_request(consent_at: str | None = None) -> MagicMock:
    """Return a mock request with a Supabase client."""
    req = MagicMock()
    supabase = MagicMock()

    # Build a chainable mock for users table
    class _QB:
        def select(self, *a, **k):
            return self

        def eq(self, *a, **k):
            return self

        def update(self, *a, **k):
            return self

        def maybe_single(self):
            return self

        def execute(self):
            res = MagicMock()
            res.data = {"face_mod_consent_at": consent_at}
            return res

    supabase.table.return_value = _QB()
    req.app.state.supabase = supabase
    return req


# ---------------------------------------------------------------------------
# FaceModConsentResponse model tests
# ---------------------------------------------------------------------------


class TestFaceModConsentResponseModel:
    def test_response_fields(self):
        resp = FaceModConsentResponse(consented_at="2026-04-13T10:00:00+00:00")
        assert "2026" in resp.consented_at


# ---------------------------------------------------------------------------
# grant_face_mod_consent handler tests
# ---------------------------------------------------------------------------


class TestGrantFaceModConsentHandler:
    """Tests for POST /users/me/face-mod-consent."""

    @pytest.mark.asyncio
    async def test_first_consent_returns_200_with_timestamp(self):
        """First-time consent: sets face_mod_consent_at and returns it."""
        user_id = str(uuid4())
        claims = _make_claims(user_id)
        # No existing consent
        request = _make_request(consent_at=None)

        with patch("app.db.async_helpers.run_sync", new=_run_sync_passthrough):
            result = await grant_face_mod_consent(
                request=request,
                claims=claims,
            )

        # Result should have consented_at
        assert result.consented_at is not None

    @pytest.mark.asyncio
    async def test_idempotent_on_second_call(self):
        """Already-consented user receives original timestamp back."""
        user_id = str(uuid4())
        claims = _make_claims(user_id)
        existing_ts = "2026-01-01T00:00:00+00:00"
        request = _make_request(consent_at=existing_ts)

        with patch("app.db.async_helpers.run_sync", new=_run_sync_passthrough):
            result = await grant_face_mod_consent(
                request=request,
                claims=claims,
            )

        assert result.consented_at == existing_ts


# ---------------------------------------------------------------------------
# Helpers for async patching
# ---------------------------------------------------------------------------


async def _run_sync_passthrough(fn, *args, **kwargs):
    return fn(*args, **kwargs)
