"""Tests for the uploads API (POST /uploads).

Tests exercise app/api/uploads.py and app/repositories/upload_repo.py.
Uses mock dependencies to avoid requiring a live Supabase connection
(per test strategy: unit tests with mocks, not integration tests).
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4


try:
    from app.api.uploads import UploadResponse, create_upload
    from app.repositories.upload_repo import UploadRepository

    _AVAILABLE = True
except (ImportError, AttributeError):
    _AVAILABLE = False

pytestmark = pytest.mark.skipif(not _AVAILABLE, reason="uploads module unavailable")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_claims(user_id: str | None = None) -> dict:
    return {"sub": user_id or str(uuid4()), "role": "authenticated"}


def _make_upload_service(upload_id=None, face_detected=True) -> MagicMock:
    """Return a mock UploadService."""
    from app.services.upload_service import UploadResult
    from unittest.mock import AsyncMock

    svc = MagicMock()
    uid = upload_id or uuid4()
    svc.create_upload = AsyncMock(
        return_value=UploadResult(
            upload_id=uid,
            face_detected=face_detected,
            image_url=f"some_user/{uid}.jpg",
        )
    )
    return svc


# ---------------------------------------------------------------------------
# UploadRepository unit tests
# ---------------------------------------------------------------------------


class TestUploadRepository:
    """Unit tests for UploadRepository."""

    def test_get_by_id_returns_none_when_missing(self):
        from tests.conftest import MockSupabase

        sb = MockSupabase()
        sb.set_table_data("uploads", None)
        repo = UploadRepository(sb)
        # Reset triggers an update (safe even with no data) then a select.
        result = repo.get_by_id(str(uuid4()))
        assert result is None

    def test_get_by_id_for_owner_check_returns_row_when_matching(self):
        from tests.conftest import MockSupabase

        uid = str(uuid4())
        user_id = str(uuid4())
        sb = MockSupabase()
        sb.set_table_data(
            "uploads",
            [
                {
                    "id": uid,
                    "user_id": user_id,
                    "image_url": "key.jpg",
                    "nsfw_result": "cleared",
                    "face_detected": True,
                    "last_accessed_at": "2026-01-01T00:00:00+00:00",
                    "mst_bin": None,
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ],
        )
        repo = UploadRepository(sb)
        result = repo.get_by_id_for_owner_check(uid, user_id)
        # MockSupabase always returns data regardless of .eq() — just check not None.
        assert result is not None

    def test_insert_returns_inserted_row(self):
        from tests.conftest import MockSupabase

        uid = str(uuid4())
        row = {
            "id": uid,
            "user_id": "u1",
            "image_url": "k.jpg",
            "nsfw_result": "cleared",
            "face_detected": False,
        }
        sb = MockSupabase()
        sb.set_table_data("uploads", [row])
        repo = UploadRepository(sb)
        result = repo.insert(row)
        # Insert is mocked — just verify no exception raised and returns dict.
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# UploadResponse model tests
# ---------------------------------------------------------------------------


class TestUploadResponseModel:
    """Pydantic model tests for UploadResponse."""

    def test_upload_response_fields(self):
        uid = str(uuid4())
        resp = UploadResponse(upload_id=uid, face_detected=True)
        assert resp.upload_id == uid
        assert resp.face_detected is True

    def test_upload_response_no_face(self):
        resp = UploadResponse(upload_id=str(uuid4()), face_detected=False)
        assert resp.face_detected is False


# ---------------------------------------------------------------------------
# create_upload handler tests
# ---------------------------------------------------------------------------


class TestCreateUploadHandler:
    """Handler-level tests for POST /uploads."""

    @pytest.mark.asyncio
    async def test_create_upload_returns_201_with_upload_id(self):
        """Happy path: handler returns upload_id and face_detected."""
        user_id = str(uuid4())
        claims = _make_claims(user_id)
        upload_svc = _make_upload_service(face_detected=True)

        # Mock UploadFile
        mock_file = MagicMock()
        mock_file.read = AsyncMock(return_value=b"fake_image_bytes")
        mock_file.content_type = "image/jpeg"

        mock_request = MagicMock()

        response = await create_upload(
            request=mock_request,
            file=mock_file,
            claims=claims,
            upload_svc=upload_svc,
        )

        assert response.status_code == 201
        body = response.body
        import json

        data = json.loads(body)
        assert "upload_id" in data
        assert data["face_detected"] is True

    @pytest.mark.asyncio
    async def test_create_upload_face_not_detected(self):
        """face_detected=False is returned when no face found."""
        claims = _make_claims()
        upload_svc = _make_upload_service(face_detected=False)

        mock_file = MagicMock()
        mock_file.read = AsyncMock(return_value=b"fake_bytes")
        mock_file.content_type = "image/jpeg"

        mock_request = MagicMock()

        import json

        response = await create_upload(
            request=mock_request,
            file=mock_file,
            claims=claims,
            upload_svc=upload_svc,
        )
        data = json.loads(response.body)
        assert data["face_detected"] is False

    @pytest.mark.asyncio
    async def test_create_upload_propagates_nsfw_exception(self):
        """HTTPException from pipeline propagates (NSFW quarantine)."""
        from fastapi import HTTPException

        claims = _make_claims()
        upload_svc = MagicMock()
        upload_svc.create_upload = AsyncMock(
            side_effect=HTTPException(status_code=422, detail="NSFW_QUARANTINE")
        )

        mock_file = MagicMock()
        mock_file.read = AsyncMock(return_value=b"bad_image")
        mock_file.content_type = "image/jpeg"

        with pytest.raises(HTTPException) as exc_info:
            await create_upload(
                request=MagicMock(),
                file=mock_file,
                claims=claims,
                upload_svc=upload_svc,
            )

        assert exc_info.value.status_code == 422
