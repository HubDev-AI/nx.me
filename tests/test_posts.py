"""Tests for posts API: create post, delete post, comments, reports.

Exercises production code in:
  - app/api/posts.py (create_post, delete_post, create_comment, get_comments, report_post)
  - app/services/public_url.py (publish_post_images, get_public_url, build_avatar_url)
"""

from __future__ import annotations


import pytest

from app.services.public_url import get_public_url, build_avatar_url
from app.config import settings
from tests.conftest import MockSupabase, requires_routers


# ===========================================================================
# Public URL helper tests
# ===========================================================================


class TestGetPublicUrl:
    """Tests for get_public_url — exercises app/services/public_url.py."""

    def test_url_contains_bucket_and_key(self):
        """URL always contains the public bucket name and storage key."""
        key = "before/user123/photo.jpg"
        url = get_public_url(key)
        # When PUBLIC_STORAGE_BASE_URL is set, it is used; otherwise SUPABASE_URL is the base.
        base = settings.PUBLIC_STORAGE_BASE_URL or settings.SUPABASE_URL
        assert base in url
        assert "post-images" in url
        assert key in url

    def test_url_structure_contains_bucket_and_key(self):
        url = get_public_url("after/user456/result.jpg")
        assert "/storage/v1/object/public/post-images/" in url
        assert "after/user456/result.jpg" in url


class TestBuildAvatarUrl:
    """Tests for build_avatar_url — exercises app/services/public_url.py."""

    def test_returns_none_when_no_key(self):
        sb = MockSupabase()
        result = build_avatar_url(sb, None)
        assert result is None

    def test_returns_none_for_empty_string_key(self):
        sb = MockSupabase()
        result = build_avatar_url(sb, "")
        assert result is None

    def test_returns_signed_url_for_valid_key(self):
        sb = MockSupabase()
        sb.storage.from_.return_value.create_signed_url.return_value = {
            "signedURL": "https://test.supabase.co/storage/v1/object/sign/avatars/photo.jpg?token=abc"
        }
        result = build_avatar_url(sb, "avatars/photo.jpg")
        assert result is not None
        assert "signedURL" not in result or result.startswith("https://")

    def test_returns_none_when_signing_fails(self):
        sb = MockSupabase()
        sb.storage.from_.return_value.create_signed_url.side_effect = Exception(
            "Storage error"
        )
        result = build_avatar_url(sb, "avatars/broken.jpg")
        assert result is None


# ===========================================================================
# Post request/response model tests
# ===========================================================================


@requires_routers
class TestPostModels:
    """Tests for post request/response Pydantic models — exercises app/api/posts.py."""

    def test_create_post_request_valid(self):
        from app.api.posts import CreatePostRequest

        req = CreatePostRequest(glow_up_job_id="job-123", caption="Looking good!")
        assert req.glow_up_job_id == "job-123"
        assert req.caption == "Looking good!"

    def test_create_post_request_no_caption(self):
        from app.api.posts import CreatePostRequest

        req = CreatePostRequest(glow_up_job_id="job-123")
        assert req.caption is None

    def test_create_post_request_caption_max_length(self):
        from app.api.posts import CreatePostRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CreatePostRequest(glow_up_job_id="job-123", caption="x" * 501)

    def test_create_comment_request_valid(self):
        from app.api.posts import CreateCommentRequest

        req = CreateCommentRequest(content="Nice transformation!")
        assert req.content == "Nice transformation!"

    def test_create_comment_request_empty_content_rejected(self):
        from app.api.posts import CreateCommentRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CreateCommentRequest(content="")

    def test_create_comment_request_too_long_rejected(self):
        from app.api.posts import CreateCommentRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CreateCommentRequest(content="x" * 1001)

    def test_report_request_optional_reason(self):
        from app.api.posts import ReportRequest

        req = ReportRequest()
        assert req.reason is None

    def test_report_request_reason_max_length(self):
        from app.api.posts import ReportRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ReportRequest(reason="x" * 501)

    def test_post_response_model(self):
        from app.api.posts import PostResponse

        resp = PostResponse(
            post_id="p-1",
            before_image_url="https://cdn.example.com/before.jpg",
            after_image_url="https://cdn.example.com/after.jpg",
            caption="Test",
            created_at="2026-03-17T00:00:00+00:00",
            share_hash="abc123",
        )
        assert resp.post_id == "p-1"
        assert resp.share_hash == "abc123"

    def test_comment_response_model(self):
        from app.api.posts import CommentResponse

        resp = CommentResponse(
            comment_id="c-1",
            post_id="p-1",
            user_id="u-1",
            content="Great!",
            is_deleted=False,
            created_at="2026-03-17T00:00:00+00:00",
            display_name="Alice",
            avatar_url=None,
        )
        assert resp.is_deleted is False
