"""Tests for user profile and history API.

Exercises production code in:
  - app/api/users.py (_lookup_user, models, constants, get_me)
  - app/api/deps.py (get_current_user, get_user_or_guest)

Note: We import models and helpers carefully to avoid triggering FastAPI
route registration which can fail on FastAPI 0.104 / Python 3.10.
"""

from __future__ import annotations

from unittest.mock import MagicMock
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
            face_shape="oval",
            symmetry_score=0.87,
            recommendations=[
                {"rank": 1, "category": "hairstyle", "suggestion": "Try bangs"}
            ],
            before_image_url="https://example.com/before.jpg",
            after_image_url="https://example.com/after.jpg",
            created_at="2026-03-17T00:00:00+00:00",
        )
        assert entry.face_shape == "oval"
        assert len(entry.recommendations) == 1

    def test_history_entry_null_fields(self):
        from app.api.users import HistoryEntry

        entry = HistoryEntry(
            analysis_id="a-2",
            face_shape=None,
            symmetry_score=None,
            recommendations=[],
            before_image_url=None,
            after_image_url=None,
            created_at="2026-03-17T00:00:00+00:00",
        )
        assert entry.face_shape is None
        assert entry.symmetry_score is None

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
        )
        assert resp.username == "alice"
        assert resp.avatar_url == "https://cdn.example.com/a.jpg"

    def test_me_response_without_avatar(self):
        from app.api.users import MeResponse

        resp = MeResponse(username="guest-abc", display_name="Guest", avatar_url=None)
        assert resp.avatar_url is None


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
