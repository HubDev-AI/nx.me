"""Tests for user profile and history API.

Exercises production code in:
  - app/api/users.py (_lookup_user, models, constants)
  - app/api/deps.py (get_current_user)

Note: We import models and helpers carefully to avoid triggering FastAPI
route registration which can fail on FastAPI 0.104 / Python 3.10.
"""
from __future__ import annotations

import sys
import time
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.deps import get_current_user
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
            recommendations=[{"rank": 1, "category": "hairstyle", "suggestion_text": "Try bangs"}],
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
    """Tests for the get_current_user dependency — exercises app/api/deps.py."""

    def test_missing_authorization_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(authorization=None)
        assert exc_info.value.status_code == 401

    def test_malformed_authorization_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(authorization="Basic dXNlcjpwYXNz")
        assert exc_info.value.status_code == 401

    def test_valid_bearer_token_returns_claims(self):
        uid = str(uuid4())
        token = make_jwt(user_id=uid)
        claims = get_current_user(authorization=f"Bearer {token}")
        assert claims["sub"] == uid

    def test_expired_bearer_token_raises_401(self):
        token = make_jwt(expired=True)
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(authorization=f"Bearer {token}")
        assert exc_info.value.status_code == 401
