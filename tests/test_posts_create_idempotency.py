"""Tests for ``POST /v1/posts`` caller-idempotency on migration 0046.

Covers the unique_violation → return-existing-live-post path added in
Unit 2 of the Save/Share/Publish/Delete plan. The partial UNIQUE index
from migration 0046 (``idx_posts_live_glow_up_job_id``) surfaces a
double-publish as a 23505 PostgREST error; ``create_post`` catches that,
looks up the live peer, re-checks ownership, and returns 200 with the
existing row instead of 500.

Why mock-based and not live-DB:

  - ``publish_post_images`` performs real storage downloads/uploads on
    every request. A live-DB test would require seeding real image blobs
    and a running Supabase Storage — excess scaffolding for a logic test.
  - ``job_repo.get_jobs_for_post`` returns a dict whose ``select`` list
    omits ``original_image_id``/``generated_image_id``, but the endpoint
    reads them. A live-DB happy-path would die on that pre-existing gap
    (outside this unit's Files list) before reaching the idempotency
    branch. Mock-override sidesteps the gap without touching unrelated
    code.

DB-level partial-uniqueness behaviour is covered in
``tests/test_posts_unique_constraint.py`` (Unit 1) against a real
Postgres. This file covers the endpoint-layer handling of that
constraint's exception.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

try:
    from fastapi import HTTPException, status
    from fastapi.responses import JSONResponse

    from app.api.posts import _PG_UNIQUE_VIOLATION_SQLSTATE, create_post
    from app.services.public_url import PublishedImageURLs

    _POSTS_AVAILABLE = True
except (ImportError, AttributeError):
    _POSTS_AVAILABLE = False

from tests.conftest import requires_routers

pytestmark = [
    pytest.mark.skipif(not _POSTS_AVAILABLE, reason="posts module unavailable"),
    requires_routers,
]


# ---------------------------------------------------------------------------
# Constants — no magic strings
# ---------------------------------------------------------------------------

_USER_A_ID = "aaaaaaaa-0000-0000-0000-000000000001"
_USER_B_ID = "bbbbbbbb-0000-0000-0000-000000000002"
_JOB_ID = "11111111-2222-3333-4444-555555555555"
_POST_ID_1 = "post-id-1111"
_POST_ID_2 = "post-id-2222"
_SHARE_HASH_1 = "hash-abcdef"
_SHARE_HASH_2 = "hash-beefed"
_BEFORE_IMG_ID = "img-before-0001"
_AFTER_IMG_ID = "img-after-0002"
_BEFORE_URL = "https://cdn.example/post-images/before/user-a/a.jpg"
_AFTER_URL = "https://cdn.example/post-images/after/user-a/b.jpg"
_PRIOR_CAPTION = "look-at-me"
_NEW_CAPTION = "different"
_JOB_STATUS_COMPLETED = "completed"
_RAW_SELFIES_BUCKET = "raw-selfies"
_GENERATED_IMAGES_BUCKET = "generated-images"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeAPIError(Exception):
    """Mimic ``postgrest.exceptions.APIError`` surface used in prod.

    Real APIError instances have a ``.code`` attribute carrying the
    Postgres SQLSTATE. We only need that shape — not the full PostgREST
    message envelope — to drive ``_is_unique_violation``.
    """

    def __init__(self, code: str, message: str = "duplicate key value") -> None:
        super().__init__(message)
        self.code = code


async def _passthrough_run_sync(fn, *args, **kwargs):
    """Replace ``app.db.async_helpers.run_sync`` with an awaitable passthrough.

    Lets synchronous repo mocks be driven by the async endpoint code.
    """
    return fn(*args, **kwargs)


def _build_job_row(user_id: str = _USER_A_ID) -> dict:
    """Return the job dict as the endpoint expects it from get_jobs_for_post.

    Extended with ``original_image_id`` / ``generated_image_id`` so the
    code path under test doesn't KeyError on the pre-existing select-list
    gap in ``job_repo.get_jobs_for_post``. See module docstring.
    """
    return {
        "id": _JOB_ID,
        "user_id": user_id,
        "status": _JOB_STATUS_COMPLETED,
        "before_image_url": f"{_RAW_SELFIES_BUCKET}/before.jpg",
        "after_image_url": f"{_GENERATED_IMAGES_BUCKET}/after.jpg",
        "original_image_id": _BEFORE_IMG_ID,
        "generated_image_id": _AFTER_IMG_ID,
    }


def _build_live_post_row(
    *, post_id: str, user_id: str, share_hash: str, caption: str | None = _PRIOR_CAPTION
) -> dict:
    """Return what ``post_repo.get_by_glow_up_job_id`` would return for a live peer."""
    return {
        "id": post_id,
        "user_id": user_id,
        "glow_up_job_id": _JOB_ID,
        "caption": caption,
        "before_image_url": _BEFORE_URL,
        "after_image_url": _AFTER_URL,
        "created_at": "2026-04-18T00:00:00+00:00",
        "share_hash": share_hash,
    }


def _build_mocks(*, job_row: dict | None = None) -> SimpleNamespace:
    """Assemble the mock dependency graph for one ``create_post`` call."""
    job_repo = MagicMock()
    if job_row is None:
        job_row = _build_job_row()
    # First call (ownership/status gate) and second call (M-5 re-verify) both
    # hit get_jobs_for_post — return the same row both times by default.
    job_repo.get_jobs_for_post.return_value = job_row

    image_repo = MagicMock()
    image_repo.get_by_id_with_fields.side_effect = lambda img_id, _fields: {
        "storage_key": f"{_RAW_SELFIES_BUCKET}/x-{img_id}.jpg",
        "bucket": _RAW_SELFIES_BUCKET,
    }

    post_repo = MagicMock()

    supabase = MagicMock()

    return SimpleNamespace(
        job_repo=job_repo,
        image_repo=image_repo,
        post_repo=post_repo,
        supabase=supabase,
    )


def _make_claims(user_id: str = _USER_A_ID) -> dict:
    return {"sub": user_id}


def _patch_publish(monkeypatch) -> None:
    """Replace ``app.api.posts.publish_post_images`` with a no-op that returns URLs."""
    monkeypatch.setattr(
        "app.api.posts.publish_post_images",
        lambda *_args, **_kwargs: PublishedImageURLs(
            before_url=_BEFORE_URL, after_url=_AFTER_URL
        ),
    )


def _patch_run_sync(monkeypatch) -> None:
    monkeypatch.setattr("app.api.posts.run_sync", _passthrough_run_sync)


async def _call_create_post(
    *,
    deps: SimpleNamespace,
    caption: str | None = _NEW_CAPTION,
    user_id: str = _USER_A_ID,
):
    """Invoke ``create_post`` with the provided mocks — returns the response."""
    from app.api.posts import CreatePostRequest

    body = CreatePostRequest(glow_up_job_id=_JOB_ID, caption=caption)
    return await create_post(
        body=body,
        claims=_make_claims(user_id=user_id),
        supabase=deps.supabase,
        post_repo=deps.post_repo,
        job_repo=deps.job_repo,
        image_repo=deps.image_repo,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCreatePostHappyPath:
    """Baseline: the 201 path still works and sets Location correctly."""

    @pytest.mark.asyncio
    async def test_first_insert_returns_201_with_location(self, monkeypatch):
        _patch_run_sync(monkeypatch)
        _patch_publish(monkeypatch)

        deps = _build_mocks()
        deps.post_repo.insert_post.return_value = {
            "id": _POST_ID_1,
            "share_hash": _SHARE_HASH_1,
        }

        response = await _call_create_post(deps=deps)

        assert isinstance(response, JSONResponse)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.headers["Location"] == f"/v1/posts/{_POST_ID_1}"
        # Exactly one INSERT on the happy path — no retry path taken.
        assert deps.post_repo.insert_post.call_count == 1
        # get_by_glow_up_job_id is only consulted on the 23505 branch.
        deps.post_repo.get_by_glow_up_job_id.assert_not_called()


class TestCreatePostIdempotencyOnUniqueViolation:
    """The heart of Unit 2 — caller idempotency on the 0046 partial unique."""

    @pytest.mark.asyncio
    async def test_second_call_returns_200_with_existing_post_id(self, monkeypatch):
        """Second POST from the same user → 200 + identical post_id + same share_hash."""
        _patch_run_sync(monkeypatch)
        _patch_publish(monkeypatch)

        deps = _build_mocks()
        # Insert raises the partial-index unique_violation …
        deps.post_repo.insert_post.side_effect = _FakeAPIError(
            _PG_UNIQUE_VIOLATION_SQLSTATE
        )
        # … and the live peer lookup resolves to the caller's existing post.
        existing = _build_live_post_row(
            post_id=_POST_ID_1, user_id=_USER_A_ID, share_hash=_SHARE_HASH_1
        )
        deps.post_repo.get_by_glow_up_job_id.return_value = existing

        response = await _call_create_post(deps=deps)

        assert isinstance(response, JSONResponse)
        assert response.status_code == status.HTTP_200_OK
        # Location still points at the (now existing) post — clients rely
        # on this for redirect / fetch.
        assert response.headers["Location"] == f"/v1/posts/{_POST_ID_1}"
        assert deps.post_repo.insert_post.call_count == 1  # no retry
        # The endpoint must look up by glow_up_job_id — not by post id,
        # which the caller does not know.
        deps.post_repo.get_by_glow_up_job_id.assert_called_once_with(_JOB_ID)

    @pytest.mark.asyncio
    async def test_200_body_matches_existing_row_not_request_caption(self, monkeypatch):
        """200 body must reflect the live row, not the retry's caption.

        A second POST with a different caption must not mask the caption
        stored on the first call — otherwise the client may conclude a
        mutation occurred when it didn't.
        """
        import json

        _patch_run_sync(monkeypatch)
        _patch_publish(monkeypatch)

        deps = _build_mocks()
        deps.post_repo.insert_post.side_effect = _FakeAPIError(
            _PG_UNIQUE_VIOLATION_SQLSTATE
        )
        deps.post_repo.get_by_glow_up_job_id.return_value = _build_live_post_row(
            post_id=_POST_ID_1,
            user_id=_USER_A_ID,
            share_hash=_SHARE_HASH_1,
            caption=_PRIOR_CAPTION,
        )

        response = await _call_create_post(deps=deps, caption=_NEW_CAPTION)

        assert response.status_code == status.HTTP_200_OK
        payload = json.loads(bytes(response.body).decode())
        assert payload["post_id"] == _POST_ID_1
        assert payload["share_hash"] == _SHARE_HASH_1
        assert payload["caption"] == _PRIOR_CAPTION  # not _NEW_CAPTION

    @pytest.mark.asyncio
    async def test_ownership_mismatch_returns_404_not_leak(self, monkeypatch):
        """Existing live post owned by user B → 404, not 200 with B's post_id.

        Defence in depth — jobs should be user-scoped, but if a job_id
        were ever reassigned the idempotency path must not leak another
        user's post_id. Matches the create-path's ``"Job not found"``
        posture for ownership-mismatch rather than returning 403 or the
        peer row.
        """
        _patch_run_sync(monkeypatch)
        _patch_publish(monkeypatch)

        deps = _build_mocks()
        deps.post_repo.insert_post.side_effect = _FakeAPIError(
            _PG_UNIQUE_VIOLATION_SQLSTATE
        )
        deps.post_repo.get_by_glow_up_job_id.return_value = _build_live_post_row(
            post_id=_POST_ID_1, user_id=_USER_B_ID, share_hash=_SHARE_HASH_1
        )

        with pytest.raises(HTTPException) as exc_info:
            await _call_create_post(deps=deps, user_id=_USER_A_ID)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        # Must not have attempted another INSERT.
        assert deps.post_repo.insert_post.call_count == 1

    @pytest.mark.asyncio
    async def test_unique_fired_but_lookup_empty_retries_once(self, monkeypatch):
        """23505 + get_by_glow_up_job_id None → retry INSERT; second succeeds."""
        _patch_run_sync(monkeypatch)
        _patch_publish(monkeypatch)

        deps = _build_mocks()
        # First INSERT raises unique_violation; second INSERT succeeds
        # (peer was soft-deleted between the first INSERT and the lookup,
        # freeing the partial-predicate slot).
        deps.post_repo.insert_post.side_effect = [
            _FakeAPIError(_PG_UNIQUE_VIOLATION_SQLSTATE),
            {"id": _POST_ID_2, "share_hash": _SHARE_HASH_2},
        ]
        deps.post_repo.get_by_glow_up_job_id.return_value = None

        response = await _call_create_post(deps=deps)

        assert isinstance(response, JSONResponse)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.headers["Location"] == f"/v1/posts/{_POST_ID_2}"
        assert deps.post_repo.insert_post.call_count == 2
        deps.post_repo.get_by_glow_up_job_id.assert_called_once_with(_JOB_ID)

    @pytest.mark.asyncio
    async def test_second_unique_violation_on_retry_escalates(self, monkeypatch):
        """Retry that also hits 23505 must not be swallowed — escalate unchanged."""
        _patch_run_sync(monkeypatch)
        _patch_publish(monkeypatch)

        deps = _build_mocks()
        deps.post_repo.insert_post.side_effect = [
            _FakeAPIError(_PG_UNIQUE_VIOLATION_SQLSTATE),
            _FakeAPIError(_PG_UNIQUE_VIOLATION_SQLSTATE),
        ]
        deps.post_repo.get_by_glow_up_job_id.return_value = None

        with pytest.raises(_FakeAPIError):
            await _call_create_post(deps=deps)

        assert deps.post_repo.insert_post.call_count == 2


class TestCreatePostNonUniqueErrorsPropagate:
    """Only 23505 enters the idempotency branch. Any other IntegrityError 500s."""

    @pytest.mark.asyncio
    async def test_non_unique_integrity_error_not_caught(self, monkeypatch):
        _patch_run_sync(monkeypatch)
        _patch_publish(monkeypatch)

        deps = _build_mocks()
        # FK violation (23503) must not be absorbed as idempotency.
        other_pg_error = _FakeAPIError("23503", "foreign key violation")
        deps.post_repo.insert_post.side_effect = other_pg_error

        with pytest.raises(_FakeAPIError) as exc_info:
            await _call_create_post(deps=deps)

        assert exc_info.value is other_pg_error
        # Lookup must not run for non-unique errors — keeps semantics tight.
        deps.post_repo.get_by_glow_up_job_id.assert_not_called()
