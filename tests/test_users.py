"""Tests for user profile and history API.

Exercises production code in:
  - app/api/users.py (_lookup_user, models, constants, get_me)
  - app/api/deps.py (get_current_user, get_user_or_guest)

Note: We import models and helpers carefully to avoid triggering FastAPI
route registration which can fail on FastAPI 0.104 / Python 3.10.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.repositories.user_repo import UserRepository
from tests.conftest import MockSupabase, make_jwt, requires_routers


# ===========================================================================
# _lookup_user tests
# ===========================================================================


@requires_routers
class TestLookupUser:
    """Tests for _lookup_user helper — exercises app/api/users.py."""

    def test_returns_user_data_when_found(self):
        from app.api.users import _lookup_user

        sb = MockSupabase()
        user_data = {
            "id": str(uuid4()),
            "username": "alice",
            "display_name": "Alice",
            "avatar_storage_key": None,
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        sb.set_table_data("users", [user_data])
        user_repo = UserRepository(sb)
        result = _lookup_user(user_repo, "alice")
        assert result["username"] == "alice"

    def test_raises_404_when_not_found(self):
        from app.api.users import _lookup_user

        sb = MockSupabase()
        sb.set_table_data("users", [])
        user_repo = UserRepository(sb)
        with pytest.raises(HTTPException) as exc_info:
            _lookup_user(user_repo, "nonexistent")
        assert exc_info.value.status_code == 404

    def test_raises_404_when_table_returns_none(self):
        from app.api.users import _lookup_user

        sb = MockSupabase()
        sb.set_table_data("users", None)
        user_repo = UserRepository(sb)
        with pytest.raises(HTTPException) as exc_info:
            _lookup_user(user_repo, "ghost")
        assert exc_info.value.status_code == 404


# ===========================================================================
# User model tests
# ===========================================================================


@requires_routers
class TestUserModels:
    """Tests for user request/response models — exercises app/api/users.py."""

    def test_profile_response_model(self):
        from app.api.users import ProfileResponse

        resp = ProfileResponse(
            username="alice",
            display_name="Alice Wonderland",
            avatar_url="https://cdn.example.com/avatar.jpg",
            post_count=15,
            total_reactions=142,
            member_since="2026-01-01T00:00:00+00:00",
        )
        assert resp.post_count == 15
        assert resp.total_reactions == 142

    def test_profile_response_no_avatar(self):
        from app.api.users import ProfileResponse

        resp = ProfileResponse(
            username="bob",
            display_name="Bob",
            avatar_url=None,
            post_count=0,
            total_reactions=0,
            member_since="2026-03-17T00:00:00+00:00",
        )
        assert resp.avatar_url is None

    def test_history_entry_model(self):
        from app.api.users import HistoryEntry

        entry = HistoryEntry(
            analysis_id="a-1",
            job_id="j-1",
            status="completed",
            face_shape="oval",
            symmetry_score=0.87,
            recommendations=[
                {"rank": 1, "category": "hairstyle", "suggestion": "Try bangs"}
            ],
            before_image_url="https://example.com/before.jpg",
            after_image_url="https://example.com/after.jpg",
            created_at="2026-03-17T00:00:00+00:00",
        )
        assert entry.job_id == "j-1"
        assert entry.status == "completed"
        assert entry.face_shape == "oval"
        assert len(entry.recommendations) == 1

    def test_history_entry_null_fields(self):
        from app.api.users import HistoryEntry

        entry = HistoryEntry(
            analysis_id="a-2",
            job_id=None,
            status="",
            face_shape=None,
            symmetry_score=None,
            recommendations=[],
            before_image_url=None,
            after_image_url=None,
            created_at="2026-03-17T00:00:00+00:00",
        )
        assert entry.job_id is None
        assert entry.status == ""
        assert entry.face_shape is None
        assert entry.symmetry_score is None

    def test_history_entry_pending_status(self):
        from app.api.users import HistoryEntry

        entry = HistoryEntry(
            analysis_id="a-3",
            job_id="j-3",
            status="processing",
            face_shape="oval",
            symmetry_score=0.5,
            recommendations=[],
            before_image_url="https://example.com/before.jpg",
            after_image_url=None,
            created_at="2026-03-17T00:00:00+00:00",
        )
        assert entry.status == "processing"
        assert entry.after_image_url is None

    def test_history_response_no_entries(self):
        from app.api.users import HistoryResponse

        resp = HistoryResponse(entries=[], next_cursor=None, has_more=False)
        assert len(resp.entries) == 0
        assert resp.has_more is False

    def test_update_profile_request_both_fields(self):
        from app.api.users import UpdateProfileRequest

        req = UpdateProfileRequest(
            display_name="New Name",
            avatar_storage_key="avatars/new.jpg",
        )
        assert req.display_name == "New Name"
        assert req.avatar_storage_key == "avatars/new.jpg"

    def test_update_profile_request_partial(self):
        from app.api.users import UpdateProfileRequest

        req = UpdateProfileRequest(display_name="Just Name")
        assert req.display_name == "Just Name"
        assert req.avatar_storage_key is None

    def test_update_profile_request_empty(self):
        from app.api.users import UpdateProfileRequest

        req = UpdateProfileRequest()
        assert req.display_name is None
        assert req.avatar_storage_key is None

    def test_update_profile_request_trims_display_name(self):
        from app.api.users import UpdateProfileRequest

        req = UpdateProfileRequest(display_name="  Padded Name   ")
        assert req.display_name == "Padded Name"

    def test_update_profile_request_rejects_whitespace_only_display_name(self):
        """`"   "` strips to `""` and fails min_length=1."""
        from pydantic import ValidationError

        from app.api.users import UpdateProfileRequest

        with pytest.raises(ValidationError):
            UpdateProfileRequest(display_name="   ")

    def test_update_profile_request_rejects_long_display_name(self):
        from pydantic import ValidationError

        from app.api.users import UpdateProfileRequest, _DISPLAY_NAME_MAX_LENGTH

        too_long = "x" * (_DISPLAY_NAME_MAX_LENGTH + 1)
        with pytest.raises(ValidationError):
            UpdateProfileRequest(display_name=too_long)

    def test_update_profile_request_trims_new_username(self):
        from app.api.users import UpdateProfileRequest

        req = UpdateProfileRequest(new_username="  alice  ")
        assert req.new_username == "alice"

    @pytest.mark.parametrize(
        "bad_username",
        [
            "1abc",  # starts with digit
            "_abc",  # starts with underscore
            "my-name",  # hyphen disallowed
            "my name",  # space in middle
            "my!name",  # special char
        ],
    )
    def test_update_profile_request_rejects_invalid_username_pattern(
        self, bad_username: str
    ):
        from pydantic import ValidationError

        from app.api.users import UpdateProfileRequest

        with pytest.raises(ValidationError):
            UpdateProfileRequest(new_username=bad_username)


# ===========================================================================
# Constants tests
# ===========================================================================


@requires_routers
class TestUserConstants:
    """Verify history pagination constants — exercises app/api/users.py."""

    def test_default_history_page_size(self):
        from app.api.users import _DEFAULT_HISTORY_PAGE_SIZE

        assert _DEFAULT_HISTORY_PAGE_SIZE == 20

    def test_max_history_page_size(self):
        from app.api.users import _MAX_HISTORY_PAGE_SIZE

        assert _MAX_HISTORY_PAGE_SIZE == 100

    def test_default_within_max(self):
        from app.api.users import _DEFAULT_HISTORY_PAGE_SIZE, _MAX_HISTORY_PAGE_SIZE

        assert _DEFAULT_HISTORY_PAGE_SIZE <= _MAX_HISTORY_PAGE_SIZE


# ===========================================================================
# get_current_user dependency tests
# ===========================================================================


class TestGetCurrentUser:
    """Tests for the get_current_user dependency — exercises app/api/deps.py.

    Since get_current_user is async (C-1: Redis-cached ban check), these tests
    exercise validate_jwt directly for the JWT-level validation paths.
    """

    def test_missing_authorization_raises_401(self):
        """No token at all → 401 (validate_jwt not reached, but tested via middleware)."""
        from app.api.middleware.auth import validate_jwt

        # validate_jwt expects a valid token; missing auth is handled by the
        # dependency layer.  Verify that a garbage token raises 401.
        with pytest.raises(HTTPException) as exc_info:
            validate_jwt("")
        assert exc_info.value.status_code == 401

    def test_malformed_authorization_raises_401(self):
        from app.api.middleware.auth import validate_jwt

        with pytest.raises(HTTPException) as exc_info:
            validate_jwt("not-a-jwt-token")
        assert exc_info.value.status_code == 401

    def test_valid_bearer_token_returns_claims(self):
        uid = str(uuid4())
        token = make_jwt(user_id=uid)
        from app.api.middleware.auth import validate_jwt

        claims = validate_jwt(token)
        assert claims["sub"] == uid

    def test_expired_bearer_token_raises_401(self):
        from app.api.middleware.auth import validate_jwt

        token = make_jwt(expired=True)
        with pytest.raises(HTTPException) as exc_info:
            validate_jwt(token)
        assert exc_info.value.status_code == 401


# ===========================================================================
# GET /users/me — authenticated identity lookup (works for guests + users)
# ===========================================================================


@requires_routers
class TestMeResponseModel:
    """Response shape for GET /users/me."""

    def test_me_response_with_avatar(self):
        from app.api.users import MeResponse

        resp = MeResponse(
            username="alice",
            display_name="Alice",
            avatar_url="https://cdn.example.com/a.jpg",
            face_mod_consent_at="2026-04-17T00:00:00+00:00",
        )
        assert resp.username == "alice"
        assert resp.avatar_url == "https://cdn.example.com/a.jpg"
        assert resp.face_mod_consent_at == "2026-04-17T00:00:00+00:00"

    def test_me_response_without_avatar(self):
        from app.api.users import MeResponse

        resp = MeResponse(
            username="guest-abc",
            display_name="Guest",
            avatar_url=None,
            face_mod_consent_at=None,
        )
        assert resp.avatar_url is None
        assert resp.face_mod_consent_at is None


@requires_routers
class TestGetMeHandler:
    """Handler-level tests for GET /users/me."""

    @staticmethod
    def _make_claims(user_id: str):
        from app.api.middleware.auth import UserClaims

        return UserClaims(sub=user_id, role="authenticated", exp=9999999999)

    @staticmethod
    def _make_image_repo(avatar_url: str | None = None) -> MagicMock:
        repo = MagicMock()
        repo.build_avatar_signed_url = MagicMock(return_value=avatar_url)
        return repo

    @pytest.mark.asyncio
    async def test_returns_username_for_real_user(self):
        from app.api.users import get_me

        user_id = str(uuid4())
        sb = MockSupabase()
        sb.set_table_data(
            "users",
            [
                {
                    "id": user_id,
                    "username": "alice",
                    "display_name": "Alice",
                    "avatar_storage_key": None,
                }
            ],
        )
        user_repo = UserRepository(sb)

        resp = await get_me(
            claims=self._make_claims(user_id),
            user_repo=user_repo,
            image_repo=self._make_image_repo(),
        )
        assert resp.username == "alice"
        assert resp.display_name == "Alice"
        assert resp.avatar_url is None

    @pytest.mark.asyncio
    async def test_returns_username_for_guest(self):
        from app.api.users import get_me

        guest_id = str(uuid4())
        sb = MockSupabase()
        sb.set_table_data(
            "users",
            [
                {
                    "id": guest_id,
                    "username": "guest-abc123def456",
                    "display_name": "Guest",
                    "avatar_storage_key": None,
                }
            ],
        )
        user_repo = UserRepository(sb)

        resp = await get_me(
            claims=self._make_claims(guest_id),
            user_repo=user_repo,
            image_repo=self._make_image_repo(),
        )
        assert resp.username == "guest-abc123def456"
        assert resp.display_name == "Guest"

    @pytest.mark.asyncio
    async def test_resolves_avatar_url_when_storage_key_present(self):
        from app.api.users import get_me

        user_id = str(uuid4())
        sb = MockSupabase()
        sb.set_table_data(
            "users",
            [
                {
                    "id": user_id,
                    "username": "bob",
                    "display_name": "Bob",
                    "avatar_storage_key": "avatars/bob.jpg",
                }
            ],
        )
        user_repo = UserRepository(sb)
        image_repo = self._make_image_repo(avatar_url="https://signed/bob.jpg")

        resp = await get_me(
            claims=self._make_claims(user_id),
            user_repo=user_repo,
            image_repo=image_repo,
        )
        assert resp.avatar_url == "https://signed/bob.jpg"
        image_repo.build_avatar_signed_url.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_404_when_user_row_missing(self):
        from app.api.users import get_me

        sb = MockSupabase()
        sb.set_table_data("users", None)
        user_repo = UserRepository(sb)

        with pytest.raises(HTTPException) as exc_info:
            await get_me(
                claims=self._make_claims(str(uuid4())),
                user_repo=user_repo,
                image_repo=self._make_image_repo(),
            )
        assert exc_info.value.status_code == 404


# ===========================================================================
# GET /users/{username}/history — handler tests for U1 (job_id + status surface)
# ===========================================================================


@requires_routers
class TestGetUserHistoryHandler:
    """Handler-level tests for GET /users/{username}/history.

    Cover the U1 contract change: history now returns job_id + status, includes
    non-terminal (queued/processing/finalizing) and errored (failed/cancelled)
    rows alongside completed ones, and caps non-terminal rows per page.
    """

    @staticmethod
    def _make_claims(user_id: str):
        from app.api.middleware.auth import UserClaims

        return UserClaims(sub=user_id, role="authenticated", exp=9999999999)

    @staticmethod
    def _make_user_repo(user_id: str, username: str = "alice") -> MagicMock:
        repo = MagicMock()
        repo.get_by_username = MagicMock(
            return_value={
                "id": user_id,
                "username": username,
                "display_name": "Alice",
                "avatar_storage_key": None,
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        )
        return repo

    @staticmethod
    def _make_upload_repo(uploads: list[dict]) -> MagicMock:
        repo = MagicMock()
        repo.list_for_user = MagicMock(return_value=uploads)
        return repo

    @staticmethod
    def _make_glowup_analysis_repo(analyses: list[dict]) -> MagicMock:
        # The handler calls glowup_analysis_repo._sb.table(...).select(...).
        # MockSupabase chain returns table_data verbatim regardless of filters.
        repo = MagicMock()
        sb = MockSupabase()
        sb.set_table_data("glowup_analyses", analyses)
        repo._sb = sb
        return repo

    @staticmethod
    def _make_job_repo(jobs: list[dict]) -> MagicMock:
        repo = MagicMock()
        repo.get_latest_jobs_for_sources = MagicMock(return_value=jobs)
        return repo

    @staticmethod
    def _make_image_repo() -> MagicMock:
        repo = MagicMock()
        repo.create_signed_url = MagicMock(
            side_effect=lambda b, k, _: f"signed://{b}/{k}"
        )
        return repo

    async def _call_handler(
        self,
        *,
        user_id: str,
        claims_sub: str | None = None,
        uploads: list[dict],
        analyses: list[dict],
        jobs: list[dict],
        cursor: str | None = None,
        limit: int = 20,
    ):
        from app.api.users import get_user_history

        return await get_user_history(
            username="alice",
            cursor=cursor,
            limit=limit,
            claims=self._make_claims(claims_sub or user_id),
            user_repo=self._make_user_repo(user_id),
            upload_repo=self._make_upload_repo(uploads),
            job_repo=self._make_job_repo(jobs),
            glowup_analysis_repo=self._make_glowup_analysis_repo(analyses),
            image_repo=self._make_image_repo(),
        )

    @pytest.mark.asyncio
    async def test_returns_completed_entry_with_job_id_and_status(self):
        user_id = str(uuid4())
        upload_id = str(uuid4())
        analysis_id = str(uuid4())
        job_id = str(uuid4())

        resp = await self._call_handler(
            user_id=user_id,
            uploads=[
                {
                    "id": upload_id,
                    "user_id": user_id,
                    "image_url": "raw/key.jpg",
                    "created_at": "2026-04-17T10:00:00+00:00",
                }
            ],
            analyses=[
                {
                    "id": analysis_id,
                    "upload_id": upload_id,
                    "face_shape": "oval",
                    "symmetry_score": 0.9,
                    "recommendations": [],
                }
            ],
            jobs=[
                {
                    "id": job_id,
                    "status": "completed",
                    "source_id": analysis_id,
                    "after_image_url": "gen/key.jpg",
                    "created_at": "2026-04-17T10:01:00+00:00",
                }
            ],
        )

        assert len(resp.entries) == 1
        entry = resp.entries[0]
        assert entry.job_id == job_id
        assert entry.status == "completed"
        assert entry.before_image_url == "signed://raw-selfies/raw/key.jpg"
        assert entry.after_image_url == "signed://generated-images/gen/key.jpg"

    @pytest.mark.asyncio
    async def test_returns_pending_entry_with_null_after_url(self):
        user_id = str(uuid4())
        upload_id = str(uuid4())
        analysis_id = str(uuid4())
        job_id = str(uuid4())

        resp = await self._call_handler(
            user_id=user_id,
            uploads=[
                {
                    "id": upload_id,
                    "user_id": user_id,
                    "image_url": "raw/key.jpg",
                    "created_at": "2026-04-17T10:00:00+00:00",
                }
            ],
            analyses=[
                {
                    "id": analysis_id,
                    "upload_id": upload_id,
                    "face_shape": "oval",
                    "symmetry_score": 0.9,
                    "recommendations": [],
                }
            ],
            jobs=[
                {
                    "id": job_id,
                    "status": "queued",
                    "source_id": analysis_id,
                    "after_image_url": None,
                    "created_at": "2026-04-17T10:01:00+00:00",
                }
            ],
        )

        assert len(resp.entries) == 1
        entry = resp.entries[0]
        assert entry.job_id == job_id
        assert entry.status == "queued"
        assert entry.after_image_url is None
        assert entry.before_image_url == "signed://raw-selfies/raw/key.jpg"

    @pytest.mark.asyncio
    async def test_processing_status_surfaces(self):
        user_id = str(uuid4())
        upload_id = str(uuid4())
        analysis_id = str(uuid4())

        resp = await self._call_handler(
            user_id=user_id,
            uploads=[
                {
                    "id": upload_id,
                    "user_id": user_id,
                    "image_url": "raw/x.jpg",
                    "created_at": "2026-04-17T10:00:00+00:00",
                }
            ],
            analyses=[
                {
                    "id": analysis_id,
                    "upload_id": upload_id,
                    "face_shape": None,
                    "symmetry_score": None,
                    "recommendations": [],
                }
            ],
            jobs=[
                {
                    "id": "j-p",
                    "status": "processing",
                    "source_id": analysis_id,
                    "after_image_url": None,
                    "created_at": "2026-04-17T10:01:00+00:00",
                }
            ],
        )

        assert len(resp.entries) == 1
        assert resp.entries[0].status == "processing"

    @pytest.mark.asyncio
    async def test_finalizing_status_surfaces(self):
        user_id = str(uuid4())
        upload_id = str(uuid4())
        analysis_id = str(uuid4())

        resp = await self._call_handler(
            user_id=user_id,
            uploads=[
                {
                    "id": upload_id,
                    "user_id": user_id,
                    "image_url": "raw/x.jpg",
                    "created_at": "2026-04-17T10:00:00+00:00",
                }
            ],
            analyses=[
                {
                    "id": analysis_id,
                    "upload_id": upload_id,
                    "face_shape": None,
                    "symmetry_score": None,
                    "recommendations": [],
                }
            ],
            jobs=[
                {
                    "id": "j-f",
                    "status": "finalizing",
                    "source_id": analysis_id,
                    "after_image_url": None,
                    "created_at": "2026-04-17T10:01:00+00:00",
                }
            ],
        )

        assert len(resp.entries) == 1
        assert resp.entries[0].status == "finalizing"

    @pytest.mark.asyncio
    async def test_failed_row_included_with_null_after_url(self):
        user_id = str(uuid4())
        upload_id = str(uuid4())
        analysis_id = str(uuid4())

        resp = await self._call_handler(
            user_id=user_id,
            uploads=[
                {
                    "id": upload_id,
                    "user_id": user_id,
                    "image_url": "raw/x.jpg",
                    "created_at": "2026-04-17T10:00:00+00:00",
                }
            ],
            analyses=[
                {
                    "id": analysis_id,
                    "upload_id": upload_id,
                    "face_shape": "oval",
                    "symmetry_score": 0.5,
                    "recommendations": [],
                }
            ],
            jobs=[
                {
                    "id": "j-x",
                    "status": "failed",
                    "source_id": analysis_id,
                    "after_image_url": None,
                    "created_at": "2026-04-17T10:01:00+00:00",
                }
            ],
        )

        assert len(resp.entries) == 1
        entry = resp.entries[0]
        assert entry.status == "failed"
        assert entry.after_image_url is None

    @pytest.mark.asyncio
    async def test_cancelled_row_included(self):
        user_id = str(uuid4())
        upload_id = str(uuid4())
        analysis_id = str(uuid4())

        resp = await self._call_handler(
            user_id=user_id,
            uploads=[
                {
                    "id": upload_id,
                    "user_id": user_id,
                    "image_url": "raw/x.jpg",
                    "created_at": "2026-04-17T10:00:00+00:00",
                }
            ],
            analyses=[
                {
                    "id": analysis_id,
                    "upload_id": upload_id,
                    "face_shape": "oval",
                    "symmetry_score": 0.5,
                    "recommendations": [],
                }
            ],
            jobs=[
                {
                    "id": "j-c",
                    "status": "cancelled",
                    "source_id": analysis_id,
                    "after_image_url": None,
                    "created_at": "2026-04-17T10:01:00+00:00",
                }
            ],
        )

        assert len(resp.entries) == 1
        assert resp.entries[0].status == "cancelled"

    @pytest.mark.asyncio
    async def test_legacy_row_without_job_skipped(self):
        # Analysis with no associated job in the included status set: skipped
        # (matches existing "no usable cell" behavior).
        user_id = str(uuid4())
        upload_id = str(uuid4())
        analysis_id = str(uuid4())

        resp = await self._call_handler(
            user_id=user_id,
            uploads=[
                {
                    "id": upload_id,
                    "user_id": user_id,
                    "image_url": "raw/x.jpg",
                    "created_at": "2026-04-17T10:00:00+00:00",
                }
            ],
            analyses=[
                {
                    "id": analysis_id,
                    "upload_id": upload_id,
                    "face_shape": "oval",
                    "symmetry_score": 0.5,
                    "recommendations": [],
                }
            ],
            jobs=[],
        )

        assert resp.entries == []

    @pytest.mark.asyncio
    async def test_cross_user_returns_404(self):
        # Owner check at handler line ~333: token sub != user_id → 404 (L-1)
        owner_id = str(uuid4())
        attacker_id = str(uuid4())

        with pytest.raises(HTTPException) as exc_info:
            await self._call_handler(
                user_id=owner_id,
                claims_sub=attacker_id,
                uploads=[],
                analyses=[],
                jobs=[],
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_non_terminal_rows_capped(self):
        # Build 15 uploads/analyses/processing-jobs and verify the handler
        # caps non-terminal entries at _MAX_PENDING_ROWS_PER_PAGE (10).
        from app.api.users import _MAX_PENDING_ROWS_PER_PAGE

        user_id = str(uuid4())
        uploads = []
        analyses = []
        jobs = []
        for i in range(15):
            uid = str(uuid4())
            aid = str(uuid4())
            uploads.append(
                {
                    "id": uid,
                    "user_id": user_id,
                    "image_url": f"raw/{i}.jpg",
                    "created_at": f"2026-04-17T10:{i:02d}:00+00:00",
                }
            )
            analyses.append(
                {
                    "id": aid,
                    "upload_id": uid,
                    "face_shape": None,
                    "symmetry_score": None,
                    "recommendations": [],
                }
            )
            jobs.append(
                {
                    "id": f"j-{i}",
                    "status": "processing",
                    "source_id": aid,
                    "after_image_url": None,
                    "created_at": f"2026-04-17T10:{i:02d}:30+00:00",
                }
            )

        resp = await self._call_handler(
            user_id=user_id,
            uploads=uploads,
            analyses=analyses,
            jobs=jobs,
        )

        assert _MAX_PENDING_ROWS_PER_PAGE == 10
        assert len(resp.entries) == _MAX_PENDING_ROWS_PER_PAGE
        for entry in resp.entries:
            assert entry.status == "processing"

    @pytest.mark.asyncio
    async def test_non_terminal_cap_does_not_drop_completed_rows(self):
        # 12 processing + 3 completed → non-terminal capped at 10, all 3
        # completed flow through.
        from app.api.users import _MAX_PENDING_ROWS_PER_PAGE

        user_id = str(uuid4())
        uploads = []
        analyses = []
        jobs = []
        for i in range(15):
            uid = str(uuid4())
            aid = str(uuid4())
            status = "completed" if i < 3 else "processing"
            after_url = f"gen/{i}.jpg" if status == "completed" else None
            uploads.append(
                {
                    "id": uid,
                    "user_id": user_id,
                    "image_url": f"raw/{i}.jpg",
                    "created_at": f"2026-04-17T10:{i:02d}:00+00:00",
                }
            )
            analyses.append(
                {
                    "id": aid,
                    "upload_id": uid,
                    "face_shape": None,
                    "symmetry_score": None,
                    "recommendations": [],
                }
            )
            jobs.append(
                {
                    "id": f"j-{i}",
                    "status": status,
                    "source_id": aid,
                    "after_image_url": after_url,
                    "created_at": f"2026-04-17T10:{i:02d}:30+00:00",
                }
            )

        resp = await self._call_handler(
            user_id=user_id,
            uploads=uploads,
            analyses=analyses,
            jobs=jobs,
        )

        completed = [e for e in resp.entries if e.status == "completed"]
        processing = [e for e in resp.entries if e.status == "processing"]
        assert len(completed) == 3
        assert len(processing) == _MAX_PENDING_ROWS_PER_PAGE


# ===========================================================================
# PATCH /users/{username} — guest-token acceptance regression
# ===========================================================================


@requires_routers
class TestUpdateUserProfileHandler:
    """Handler-level tests for PATCH /users/{username}.

    Covers the dep-swap regression: the handler was previously wired to
    `get_current_user` (JWT only). Guest sessions sending X-Guest-Token hit
    the dep's 401 before reaching the handler, so display-name / username
    edits died for anyone in guest mode. The swap to `get_user_or_guest`
    means the guest's resolved claims reach this handler and the existing
    owner-match (`claims["sub"] == user.id`) still gates cross-user access.
    """

    @staticmethod
    def _make_claims(user_id: str):
        from app.api.middleware.auth import UserClaims

        return UserClaims(sub=user_id, role="authenticated", exp=9999999999)

    @staticmethod
    def _make_image_repo(avatar_url: str | None = None) -> MagicMock:
        repo = MagicMock()
        repo.build_avatar_signed_url = MagicMock(return_value=avatar_url)
        return repo

    @pytest.mark.asyncio
    async def test_accepts_guest_owner_claims_and_updates_display_name(self):
        from app.api.users import UpdateProfileRequest, update_user_profile

        user_id = str(uuid4())
        user_row = {
            "id": user_id,
            "username": "guest-abc123def456",
            "display_name": "Guest",
            "avatar_storage_key": None,
            "username_changed_at": None,
        }
        user_repo = MagicMock(spec=UserRepository)
        user_repo.get_by_username = MagicMock(return_value=user_row)
        user_repo.update_profile = MagicMock()
        user_repo.get_profile_by_id = MagicMock(
            return_value={**user_row, "display_name": "Guest Renamed"}
        )

        resp = await update_user_profile(
            username="guest-abc123def456",
            body=UpdateProfileRequest(display_name="Guest Renamed"),
            claims=self._make_claims(user_id),
            user_repo=user_repo,
            image_repo=self._make_image_repo(),
        )

        assert resp.display_name == "Guest Renamed"
        user_repo.update_profile.assert_called_once()
        update_args = user_repo.update_profile.call_args[0]
        assert update_args[0] == user_id
        assert update_args[1]["display_name"] == "Guest Renamed"
        assert "updated_at" in update_args[1]

    @pytest.mark.asyncio
    async def test_cross_user_returns_404_even_with_valid_auth(self):
        from app.api.users import UpdateProfileRequest, update_user_profile

        owner_id = str(uuid4())
        attacker_id = str(uuid4())
        user_repo = MagicMock(spec=UserRepository)
        user_repo.get_by_username = MagicMock(
            return_value={
                "id": owner_id,
                "username": "alice",
                "display_name": "Alice",
                "avatar_storage_key": None,
            }
        )

        with pytest.raises(HTTPException) as exc:
            await update_user_profile(
                username="alice",
                body=UpdateProfileRequest(display_name="Hacked"),
                claims=self._make_claims(attacker_id),
                user_repo=user_repo,
                image_repo=self._make_image_repo(),
            )
        assert exc.value.status_code == 404
        user_repo.update_profile.assert_not_called()


# ===========================================================================
# POST /users/{username}/avatar
# ===========================================================================


@requires_routers
class TestUploadUserAvatarHandler:
    """Handler-level tests for POST /users/{username}/avatar.

    Validates the new multipart avatar endpoint — content-type gating,
    size cap, empty-payload rejection, owner-only access, and the
    upload-then-swap-then-prune happy path.
    """

    @staticmethod
    def _make_claims(user_id: str):
        from app.api.middleware.auth import UserClaims

        return UserClaims(sub=user_id, role="authenticated", exp=9999999999)

    @staticmethod
    def _make_user_repo(
        user_id: str,
        username: str,
        *,
        previous_key: str | None = None,
        refreshed_key: str | None = None,
    ) -> MagicMock:
        repo = MagicMock(spec=UserRepository)
        repo.get_by_username = MagicMock(
            return_value={
                "id": user_id,
                "username": username,
                "display_name": "Alice",
                "avatar_storage_key": previous_key,
            }
        )
        repo.update_profile = MagicMock()
        repo.get_profile_by_id = MagicMock(
            return_value={
                "id": user_id,
                "username": username,
                "display_name": "Alice",
                "avatar_storage_key": refreshed_key,
                "username_changed_at": None,
            }
        )
        return repo

    @staticmethod
    def _make_upload_file(content: bytes, content_type: str) -> MagicMock:
        f = MagicMock()
        f.read = AsyncMock(return_value=content)
        f.content_type = content_type
        return f

    @pytest.mark.asyncio
    async def test_rejects_unsupported_mime(self):
        from app.api.users import upload_user_avatar

        user_id = str(uuid4())
        user_repo = self._make_user_repo(user_id, "alice")
        image_repo = MagicMock()
        mock_file = self._make_upload_file(b"\xff" * 64, "image/gif")

        with pytest.raises(HTTPException) as exc:
            await upload_user_avatar(
                username="alice",
                file=mock_file,
                claims=self._make_claims(user_id),
                user_repo=user_repo,
                image_repo=image_repo,
            )
        assert exc.value.status_code == 400
        image_repo.upload.assert_not_called()
        user_repo.update_profile.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_empty_file(self):
        from app.api.users import upload_user_avatar

        user_id = str(uuid4())
        user_repo = self._make_user_repo(user_id, "alice")
        image_repo = MagicMock()
        mock_file = self._make_upload_file(b"", "image/jpeg")

        with pytest.raises(HTTPException) as exc:
            await upload_user_avatar(
                username="alice",
                file=mock_file,
                claims=self._make_claims(user_id),
                user_repo=user_repo,
                image_repo=image_repo,
            )
        assert exc.value.status_code == 400
        image_repo.upload.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_oversized_file(self):
        from app.api.users import _AVATAR_MAX_BYTES, upload_user_avatar

        user_id = str(uuid4())
        user_repo = self._make_user_repo(user_id, "alice")
        image_repo = MagicMock()
        mock_file = self._make_upload_file(
            b"\x00" * (_AVATAR_MAX_BYTES + 1), "image/jpeg"
        )

        with pytest.raises(HTTPException) as exc:
            await upload_user_avatar(
                username="alice",
                file=mock_file,
                claims=self._make_claims(user_id),
                user_repo=user_repo,
                image_repo=image_repo,
            )
        assert exc.value.status_code == 413
        image_repo.upload.assert_not_called()

    @pytest.mark.asyncio
    async def test_cross_user_returns_404_without_touching_storage(self):
        from app.api.users import upload_user_avatar

        owner_id = str(uuid4())
        attacker_id = str(uuid4())
        user_repo = self._make_user_repo(owner_id, "alice")
        image_repo = MagicMock()
        mock_file = self._make_upload_file(b"\xff" * 128, "image/jpeg")

        with pytest.raises(HTTPException) as exc:
            await upload_user_avatar(
                username="alice",
                file=mock_file,
                claims=self._make_claims(attacker_id),
                user_repo=user_repo,
                image_repo=image_repo,
            )
        assert exc.value.status_code == 404
        image_repo.upload.assert_not_called()
        user_repo.update_profile.assert_not_called()

    @pytest.mark.asyncio
    async def test_happy_path_uploads_swaps_and_prunes_previous(self):
        from app.api.users import upload_user_avatar

        user_id = str(uuid4())
        previous_key = f"avatars/{user_id}/oldfile.jpg"
        user_repo = self._make_user_repo(
            user_id,
            "alice",
            previous_key=previous_key,
            refreshed_key=f"avatars/{user_id}/refreshed.png",
        )
        image_repo = MagicMock()
        image_repo.upload = MagicMock()
        image_repo.remove = MagicMock()
        image_repo.build_avatar_signed_url = MagicMock(
            return_value="https://signed.example.com/new.png"
        )
        mock_file = self._make_upload_file(b"\xff" * 1024, "image/png")

        resp = await upload_user_avatar(
            username="alice",
            file=mock_file,
            claims=self._make_claims(user_id),
            user_repo=user_repo,
            image_repo=image_repo,
        )

        # Upload called before the DB swap — new key under avatars/{user_id}/.
        image_repo.upload.assert_called_once()
        bucket, new_key, body, content_type = image_repo.upload.call_args[0]
        assert bucket == "avatars"
        assert new_key.startswith(f"avatars/{user_id}/")
        assert new_key.endswith(".png")
        assert body == b"\xff" * 1024
        assert content_type == "image/png"

        # DB row points at the freshly-uploaded key.
        user_repo.update_profile.assert_called_once()
        update_args = user_repo.update_profile.call_args[0]
        assert update_args[0] == user_id
        assert update_args[1]["avatar_storage_key"] == new_key

        # Previous object removed best-effort after the DB pointer moved.
        image_repo.remove.assert_called_once_with("avatars", [previous_key])

        assert resp.avatar_url == "https://signed.example.com/new.png"

    @pytest.mark.asyncio
    async def test_first_avatar_does_not_call_remove(self):
        """No previous avatar → skip the best-effort storage prune."""
        from app.api.users import upload_user_avatar

        user_id = str(uuid4())
        user_repo = self._make_user_repo(
            user_id,
            "alice",
            previous_key=None,
            refreshed_key=f"avatars/{user_id}/first.jpg",
        )
        image_repo = MagicMock()
        image_repo.upload = MagicMock()
        image_repo.remove = MagicMock()
        image_repo.build_avatar_signed_url = MagicMock(return_value="https://signed")
        mock_file = self._make_upload_file(b"\xff" * 64, "image/jpeg")

        await upload_user_avatar(
            username="alice",
            file=mock_file,
            claims=self._make_claims(user_id),
            user_repo=user_repo,
            image_repo=image_repo,
        )

        image_repo.upload.assert_called_once()
        image_repo.remove.assert_not_called()
