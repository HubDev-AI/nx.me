"""Tests for the `kind` field on FeedPostResponse / HistoryEntry.

Exercises production code in:
  - app/api/social.py  (FeedPostResponse.kind default)
  - app/api/users.py   (HistoryEntry.source_type default)
"""

from __future__ import annotations

import sys

import pytest


pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="app/api/social.py requires StrEnum (Python 3.11+)",
)


def _make_post(**kwargs):
    from app.api.social import FeedPostResponse

    defaults = dict(
        post_id="p-1",
        user_id="u-1",
        username="alice",
        display_name="Alice",
        avatar_url=None,
        caption=None,
        before_image_url="b",
        after_image_url="a",
        reaction_count=0,
        comment_count=0,
        created_at="2026-04-22T00:00:00+00:00",
        has_reacted=False,
    )
    defaults.update(kwargs)
    return FeedPostResponse(**defaults)


class TestFeedPostKindField:
    def test_default_kind_is_glowup(self):
        post = _make_post()
        assert post.kind == "glowup"

    def test_explicit_kind_makeup(self):
        post = _make_post(kind="makeup")
        assert post.kind == "makeup"

    def test_kind_serialises_in_model_dump(self):
        post = _make_post(kind="makeup")
        data = post.model_dump()
        assert data["kind"] == "makeup"

    def test_glowup_kind_round_trips(self):
        post = _make_post(kind="glowup")
        assert post.model_dump()["kind"] == "glowup"


class TestHistoryEntrySourceType:
    def test_default_source_type_is_glowup_analysis(self):
        from app.api.users import HistoryEntry

        entry = HistoryEntry(
            analysis_id="a-1",
            job_id=None,
            status="completed",
            face_shape=None,
            symmetry_score=None,
            recommendations=[],
            before_image_url=None,
            after_image_url=None,
            created_at="2026-04-22T00:00:00+00:00",
            saved_at=None,
        )
        assert entry.source_type == "glowup_analysis"

    def test_explicit_source_type_makeup_session(self):
        from app.api.users import HistoryEntry

        entry = HistoryEntry(
            analysis_id="a-2",
            job_id="j-2",
            status="completed",
            face_shape=None,
            symmetry_score=None,
            recommendations=[],
            before_image_url=None,
            after_image_url=None,
            created_at="2026-04-22T00:00:00+00:00",
            saved_at=None,
            source_type="makeup_session",
        )
        assert entry.source_type == "makeup_session"
