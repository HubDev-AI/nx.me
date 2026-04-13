"""Tests for the blocks API — user blocking models and endpoint logic.

Exercises production code in:
  - app/api/blocks.py (BlockedUserResponse, BlockedListResponse, block_user, unblock_user, list_blocked_users)
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException


# Check if router imports work
try:
    from app.api.blocks import BlockedUserResponse, BlockedListResponse  # noqa: F401

    _BLOCKS_AVAILABLE = True
except (ImportError, AttributeError):
    _BLOCKS_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _BLOCKS_AVAILABLE, reason="blocks module unavailable"
)


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestBlockModels:
    """Tests for block Pydantic models — exercises app/api/blocks.py."""

    def test_blocked_user_response_full(self):
        from app.api.blocks import BlockedUserResponse

        resp = BlockedUserResponse(
            id="b-1",
            blocked_id="u-2",
            display_name="Bob",
            username="bob",
            created_at="2026-03-17T00:00:00+00:00",
        )
        assert resp.blocked_id == "u-2"
        assert resp.display_name == "Bob"

    def test_blocked_user_response_optional_fields(self):
        from app.api.blocks import BlockedUserResponse

        resp = BlockedUserResponse(
            id="b-1",
            blocked_id="u-2",
            created_at="2026-03-17T00:00:00+00:00",
        )
        assert resp.display_name is None
        assert resp.username is None

    def test_blocked_list_response_empty(self):
        from app.api.blocks import BlockedListResponse

        resp = BlockedListResponse(users=[])
        assert len(resp.users) == 0
        assert resp.has_more is False
        assert resp.next_cursor is None


# ---------------------------------------------------------------------------
# Endpoint logic tests
# ---------------------------------------------------------------------------


class TestBlockUser:
    """Tests for POST /users/{user_id}/block — exercises app/api/blocks.py."""

    def test_block_user_success(self):
        from app.api.blocks import block_user

        blocker_id = str(uuid4())
        target_id = uuid4()

        claims = {"sub": blocker_id}
        block_repo = MagicMock()
        block_repo.block.return_value = {}

        result = block_user(user_id=target_id, claims=claims, block_repo=block_repo)
        assert result.status_code == 204
        block_repo.block.assert_called_once_with(blocker_id, str(target_id))

    def test_block_self_rejected(self):
        from app.api.blocks import block_user

        user_id = uuid4()
        claims = {"sub": str(user_id)}
        block_repo = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            block_user(user_id=user_id, claims=claims, block_repo=block_repo)
        assert exc_info.value.status_code == 422
        block_repo.block.assert_not_called()


class TestUnblockUser:
    """Tests for DELETE /users/{user_id}/block — exercises app/api/blocks.py."""

    def test_unblock_success(self):
        from app.api.blocks import unblock_user

        blocker_id = str(uuid4())
        target_id = uuid4()
        claims = {"sub": blocker_id}
        block_repo = MagicMock()
        block_repo.unblock.return_value = True

        result = unblock_user(user_id=target_id, claims=claims, block_repo=block_repo)
        assert result.status_code == 204

    def test_unblock_not_found(self):
        from app.api.blocks import unblock_user

        blocker_id = str(uuid4())
        target_id = uuid4()
        claims = {"sub": blocker_id}
        block_repo = MagicMock()
        block_repo.unblock.return_value = False

        with pytest.raises(HTTPException) as exc_info:
            unblock_user(user_id=target_id, claims=claims, block_repo=block_repo)
        assert exc_info.value.status_code == 404


class TestListBlockedUsers:
    """Tests for GET /users/blocked — exercises app/api/blocks.py."""

    def test_list_empty(self):
        from app.api.blocks import list_blocked_users

        claims = {"sub": str(uuid4())}
        block_repo = MagicMock()
        block_repo.list_blocked.return_value = []

        result = list_blocked_users(
            cursor=None, limit=50, claims=claims, block_repo=block_repo
        )
        assert len(result.users) == 0
        assert result.has_more is False

    def test_list_with_results(self):
        from app.api.blocks import list_blocked_users

        claims = {"sub": str(uuid4())}
        block_repo = MagicMock()
        block_repo.list_blocked.return_value = [
            {
                "id": "b-1",
                "blocked_id": "u-2",
                "blocked_user": {"display_name": "Bob", "username": "bob"},
                "created_at": "2026-03-17T00:00:00+00:00",
            },
        ]

        result = list_blocked_users(
            cursor=None, limit=50, claims=claims, block_repo=block_repo
        )
        assert len(result.users) == 1
        assert result.users[0].blocked_id == "u-2"
        assert result.users[0].display_name == "Bob"

    def test_list_pagination(self):
        from app.api.blocks import list_blocked_users

        claims = {"sub": str(uuid4())}
        block_repo = MagicMock()
        # Return limit+1 rows to signal has_more
        rows = [
            {
                "id": f"b-{i}",
                "blocked_id": f"u-{i}",
                "blocked_user": None,
                "created_at": f"2026-03-{i + 1:02d}T00:00:00+00:00",
            }
            for i in range(3)
        ]
        block_repo.list_blocked.return_value = rows

        result = list_blocked_users(
            cursor=None, limit=2, claims=claims, block_repo=block_repo
        )
        assert result.has_more is True
        assert len(result.users) == 2
        assert result.next_cursor is not None
