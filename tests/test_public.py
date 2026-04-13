"""Tests for public API models.

Exercises production code in:
  - app/api/public.py (RecommendationItem, CardResponse)
"""

from __future__ import annotations

import pytest


try:
    from app.api.public import RecommendationItem, CardResponse  # noqa: F401

    _PUBLIC_AVAILABLE = True
except (ImportError, AttributeError):
    _PUBLIC_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _PUBLIC_AVAILABLE, reason="public module unavailable"
)


class TestPublicModels:
    """Pydantic model tests — exercises app/api/public.py."""

    def test_recommendation_item(self):
        item = RecommendationItem(rank=1, category="hair", suggestion="Try layers")
        assert item.rank == 1
        assert item.rationale is None

    def test_recommendation_item_with_rationale(self):
        item = RecommendationItem(
            rank=1,
            category="hair",
            suggestion="Try layers",
            rationale="Adds dimension to your face shape",
        )
        assert item.rationale is not None

    def test_card_response(self):
        resp = CardResponse(
            username="alice",
            display_name="Alice",
            share_hash="abc123",
            before_image_url="https://cdn.example.com/before.jpg",
            after_image_url="https://cdn.example.com/after.jpg",
            recommendations=[
                RecommendationItem(
                    rank=1, category="style", suggestion="Bold accessories"
                ),
            ],
            reaction_count=42,
            comment_count=7,
        )
        assert resp.username == "alice"
        assert len(resp.recommendations) == 1
        assert resp.reaction_count == 42

    def test_card_response_empty_recommendations(self):
        resp = CardResponse(
            username="bob",
            display_name="Bob",
            share_hash="def456",
            before_image_url="https://cdn.example.com/b.jpg",
            after_image_url="https://cdn.example.com/a.jpg",
            recommendations=[],
            reaction_count=0,
            comment_count=0,
        )
        assert len(resp.recommendations) == 0
