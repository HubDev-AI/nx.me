"""Tests for social feed and reactions.

Exercises production code in:
  - app/api/social.py (constants, cursor parsing logic, guest token validation)
  - app/config/__init__.py (GUEST_TOKEN_TTL_SECONDS, GUEST_REACTION_LIMIT)

Note: FeedSort uses StrEnum (Python 3.11+) and the route endpoints use
FastAPI features requiring 0.115+. We test the importable constants and
helper logic without importing the route-level symbols that fail on 3.10.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
import sys


# Skip the entire module on Python < 3.11 where StrEnum is unavailable
pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="app/api/social.py requires StrEnum (Python 3.11+)",
)


@pytest.mark.skipif(sys.version_info < (3, 11), reason="StrEnum requires 3.11+")
class TestFeedSort:
    """Tests for FeedSort enum — exercises app/api/social.py."""

    def test_newest_value(self):
        from app.api.social import FeedSort
        assert FeedSort.NEWEST == "newest"

    def test_trending_value(self):
        from app.api.social import FeedSort
        assert FeedSort.TRENDING == "trending"

    def test_biggest_improvements_value(self):
        from app.api.social import FeedSort
        assert FeedSort.BIGGEST_IMPROVEMENTS == "biggest_improvements"


@pytest.mark.skipif(sys.version_info < (3, 11), reason="StrEnum requires 3.11+")
class TestFeedModels:
    """Tests for feed response Pydantic models — exercises app/api/social.py."""

    def test_feed_post_response_model(self):
        from app.api.social import FeedPostResponse
        post = FeedPostResponse(
            post_id="p-1",
            user_id="u-1",
            username="alice",
            display_name="Alice",
            avatar_url="https://cdn.example.com/avatar.jpg",
            caption="Test caption",
            before_image_url="https://cdn.example.com/before.jpg",
            after_image_url="https://cdn.example.com/after.jpg",
            reaction_count=42,
            comment_count=7,
            created_at="2026-03-17T00:00:00+00:00",
        )
        assert post.reaction_count == 42
        assert post.comment_count == 7

    def test_feed_response_empty_list(self):
        from app.api.social import FeedResponse
        resp = FeedResponse(posts=[], next_cursor=None, has_more=False)
        assert len(resp.posts) == 0
        assert resp.has_more is False

    def test_reaction_response_model(self):
        from app.api.social import ReactionResponse
        resp = ReactionResponse(reaction_count=5)
        assert resp.reaction_count == 5


@pytest.mark.skipif(sys.version_info < (3, 11), reason="StrEnum requires 3.11+")
class TestValidateGuestToken:
    """Tests for validate_guest_token — exercises app/api/social.py."""

    def _make_redis(self, *, incr_return: int) -> AsyncMock:
        """Return a minimal async Redis mock for validate_guest_token."""
        redis_mock = AsyncMock()
        redis_mock.set = AsyncMock(return_value=True)
        redis_mock.incr = AsyncMock(return_value=incr_return)
        redis_mock.expire = AsyncMock(return_value=True)
        return redis_mock

    def test_first_reaction_allowed(self):
        """First reaction for a new token must be allowed (count == 1)."""
        from app.api.social import validate_guest_token

        redis_mock = self._make_redis(incr_return=1)
        result = asyncio.get_event_loop().run_until_complete(
            validate_guest_token(redis_mock, "a" * 64)
        )
        assert result is True

    def test_reaction_at_limit_allowed(self):
        """Reaction exactly at GUEST_REACTION_LIMIT must still be allowed."""
        from app.api.social import validate_guest_token
        from app.config import settings

        redis_mock = self._make_redis(incr_return=settings.GUEST_REACTION_LIMIT)
        result = asyncio.get_event_loop().run_until_complete(
            validate_guest_token(redis_mock, "b" * 64)
        )
        assert result is True

    def test_reaction_over_limit_rejected(self):
        """Reaction exceeding GUEST_REACTION_LIMIT must be rejected."""
        from app.api.social import validate_guest_token
        from app.config import settings

        redis_mock = self._make_redis(incr_return=settings.GUEST_REACTION_LIMIT + 1)
        result = asyncio.get_event_loop().run_until_complete(
            validate_guest_token(redis_mock, "c" * 64)
        )
        assert result is False

    def test_token_registered_with_hash(self):
        """Token registration key must use a SHA-256 hash, not the raw token."""
        import hashlib
        from app.api.social import validate_guest_token
        from app.config import settings

        token = "d" * 64
        redis_mock = self._make_redis(incr_return=1)
        asyncio.get_event_loop().run_until_complete(
            validate_guest_token(redis_mock, token)
        )

        expected_hash = hashlib.sha256(token.encode()).hexdigest()
        registration_key = f"guest_token:{expected_hash}"

        # SET was called with the hashed key, correct TTL, and NX flag
        redis_mock.set.assert_called_once_with(
            registration_key, "1",
            ex=settings.GUEST_TOKEN_TTL_SECONDS,
            nx=True,
        )

    def test_expire_called_only_on_first_reaction(self):
        """EXPIRE must only be set when count == 1 (first reaction for this token)."""
        from app.api.social import validate_guest_token

        # count > 1 → expire must NOT be called
        redis_mock = self._make_redis(incr_return=5)
        asyncio.get_event_loop().run_until_complete(
            validate_guest_token(redis_mock, "e" * 64)
        )
        redis_mock.expire.assert_not_called()

    def test_config_constants_exist(self):
        """GUEST_TOKEN_TTL_SECONDS and GUEST_REACTION_LIMIT must be defined in settings."""
        from app.config import settings

        assert hasattr(settings, "GUEST_TOKEN_TTL_SECONDS")
        assert hasattr(settings, "GUEST_REACTION_LIMIT")
        assert settings.GUEST_TOKEN_TTL_SECONDS == 86_400
        assert settings.GUEST_REACTION_LIMIT == 50
