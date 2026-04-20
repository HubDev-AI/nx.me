"""Tests for social feed and reactions.

Exercises production code in:
  - app/api/social.py (constants, cursor parsing logic)

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
            has_reacted=True,
        )
        assert post.reaction_count == 42
        assert post.comment_count == 7
        assert post.has_reacted is True

    def test_feed_post_response_has_reacted_defaults_false(self):
        """Clients that deserialize legacy payloads without ``has_reacted``
        should still parse the response — default must be False."""
        from app.api.social import FeedPostResponse

        post = FeedPostResponse(
            post_id="p-1",
            user_id="u-1",
            username=None,
            display_name=None,
            avatar_url=None,
            caption=None,
            before_image_url="b",
            after_image_url="a",
            reaction_count=0,
            comment_count=0,
            created_at="2026-03-17T00:00:00+00:00",
        )
        assert post.has_reacted is False

    def test_feed_response_empty_list(self):
        from app.api.social import FeedResponse

        resp = FeedResponse(posts=[], next_cursor=None, has_more=False)
        assert len(resp.posts) == 0
        assert resp.has_more is False

    def test_reaction_response_model(self):
        from app.api.social import ReactionResponse

        resp = ReactionResponse(reaction_count=5, has_reacted=True)
        assert resp.reaction_count == 5
        assert resp.has_reacted is True


@pytest.mark.skipif(sys.version_info < (3, 11), reason="StrEnum requires 3.11+")
class TestReconcileReactionLock:
    """Redis mutex behaviour in reconcile_reaction_counts — guards against
    racing the 03:30 UTC retention cron when reconcile hangs past its slot."""

    @pytest.fixture(autouse=True)
    def _enable_social(self, monkeypatch):
        """Social is off by default — mutex tests assume the work path runs."""
        from app.config import settings

        monkeypatch.setattr(settings, "FEATURE_SOCIAL_ENABLED", True)

    def _patch_feed_repo(self, monkeypatch, updated_rows=None):
        """Replace FeedRepository + get_supabase_service with stand-ins so
        reconcile_reaction_counts never touches the real DB."""
        rows = updated_rows or []

        monkeypatch.setattr("app.api.social.run_sync", AsyncMock(return_value=rows))

        class _FakeFeedRepo:
            def __init__(self, *_args, **_kwargs):
                pass

            # run_sync(feed_repo.reconcile_reaction_counts, cutoff) evaluates
            # the attribute before awaiting, so the method must exist even
            # though run_sync is mocked.
            def reconcile_reaction_counts(self, *_args, **_kwargs):
                return rows

        # The function re-imports inside the body — patch the package exports.
        import app.db.client
        import app.repositories.feed_repo

        monkeypatch.setattr(app.db.client, "get_supabase_service", lambda: object())
        monkeypatch.setattr(app.repositories.feed_repo, "FeedRepository", _FakeFeedRepo)

    def test_lock_is_acquired_and_released_on_success(self, monkeypatch):
        from app.api.social import RECONCILE_LOCK_KEY, reconcile_reaction_counts
        from app.config import settings

        self._patch_feed_repo(monkeypatch, updated_rows=[])

        redis_mock = AsyncMock()
        redis_mock.set = AsyncMock(return_value=True)
        redis_mock.delete = AsyncMock(return_value=1)

        asyncio.get_event_loop().run_until_complete(
            reconcile_reaction_counts({"redis": redis_mock})
        )

        # Lock acquired exactly once with NX + TTL from config.
        redis_mock.set.assert_called_once_with(
            RECONCILE_LOCK_KEY,
            "1",
            nx=True,
            ex=settings.RECONCILE_LOCK_TTL_SECONDS,
        )
        # Released in finally — so the retention cron can run next tick.
        redis_mock.delete.assert_any_call(RECONCILE_LOCK_KEY)

    def test_skips_when_lock_already_held(self, monkeypatch):
        """SET NX returning False → log warning and return without work."""
        from app.api.social import reconcile_reaction_counts

        # run_sync should not be called at all — but we patch it to detect.
        run_sync_mock = AsyncMock()
        monkeypatch.setattr("app.api.social.run_sync", run_sync_mock)

        redis_mock = AsyncMock()
        redis_mock.set = AsyncMock(return_value=False)  # lock busy
        redis_mock.delete = AsyncMock(return_value=0)

        asyncio.get_event_loop().run_until_complete(
            reconcile_reaction_counts({"redis": redis_mock})
        )

        run_sync_mock.assert_not_awaited()
        # No delete because we never acquired the lock.
        redis_mock.delete.assert_not_called()

    def test_lock_released_even_when_body_raises(self, monkeypatch):
        """An exception inside the try-block must not leak the lock."""
        from app.api.social import RECONCILE_LOCK_KEY, reconcile_reaction_counts

        async def _boom(*_args, **_kwargs):
            raise RuntimeError("feed repo exploded")

        # Acquire succeeds, then run_sync raises.
        monkeypatch.setattr("app.api.social.run_sync", _boom)

        import app.db.client

        monkeypatch.setattr(app.db.client, "get_supabase_service", lambda: object())

        redis_mock = AsyncMock()
        redis_mock.set = AsyncMock(return_value=True)
        redis_mock.delete = AsyncMock(return_value=1)

        with pytest.raises(RuntimeError):
            asyncio.get_event_loop().run_until_complete(
                reconcile_reaction_counts({"redis": redis_mock})
            )

        # Finally ran → lock released.
        redis_mock.delete.assert_any_call(RECONCILE_LOCK_KEY)

    def test_short_circuits_when_social_disabled(self, monkeypatch):
        """FEATURE_SOCIAL_ENABLED=False → skip without touching Redis or DB."""
        from app.api.social import reconcile_reaction_counts
        from app.config import settings

        monkeypatch.setattr(settings, "FEATURE_SOCIAL_ENABLED", False)

        run_sync_mock = AsyncMock()
        monkeypatch.setattr("app.api.social.run_sync", run_sync_mock)

        redis_mock = AsyncMock()

        asyncio.get_event_loop().run_until_complete(
            reconcile_reaction_counts({"redis": redis_mock})
        )

        run_sync_mock.assert_not_awaited()
        redis_mock.set.assert_not_called()
        redis_mock.delete.assert_not_called()


@pytest.mark.skipif(sys.version_info < (3, 11), reason="StrEnum requires 3.11+")
class TestReconcileLockConstants:
    def test_ttl_exposed_on_settings(self):
        from app.config import settings

        assert hasattr(settings, "RECONCILE_LOCK_TTL_SECONDS")
        assert settings.RECONCILE_LOCK_TTL_SECONDS == 1800

    def test_lock_key_is_module_constant(self):
        from app.api.social import RECONCILE_LOCK_KEY

        assert RECONCILE_LOCK_KEY == "cron:reconcile_reactions:lock"
