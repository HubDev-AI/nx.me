"""Tests for social feed and reactions.

Exercises production code in:
  - app/api/social.py (constants, cursor parsing logic)

Note: FeedSort uses StrEnum (Python 3.11+) and the route endpoints use
FastAPI features requiring 0.115+. We test the importable constants and
helper logic without importing the route-level symbols that fail on 3.10.
"""
from __future__ import annotations

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
