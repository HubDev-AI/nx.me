"""Tests for the hard-cascade ``DELETE /v1/jobs/{job_id}`` endpoint.

Validates the invariants of ``app/api/jobs.py::delete_job``:

1. Enumeration of blob storage keys runs **before** the DB DELETE (otherwise
   the join to find post-images keys dies with the cascade).
2. Idempotent 204 on all non-error outcomes: missing row, wrong owner,
   already-deleted — all return 204 (mirrors ``delete_account``; prevents
   ownership enumeration and tolerates client retry across flaky networks).
3. Status gate: only ``completed | failed | cancelled`` delete. Queued /
   processing / finalizing jobs → 409 JOB_NOT_CANCELLABLE.
4. On blob wipe failure, the key lands in ``orphaned_storage_keys`` with
   ``reason="delete_glowup"``; endpoint still returns 204.
5. Analysis is app-layer ref-counted: only deleted when no peer job on
   the same ``source_id`` survives (excluding cancelled peers), AND only
   when ``source_type == "glowup_analysis"``.
6. Rate limiter returns 429 with Retry-After header when caller exceeds
   the per-minute cap.

Scenarios A-L use mocks; scenario M exercises a real-DB cascade against
the local Supabase Postgres so FK drift is caught by the test rather
than a customer's lost post.
"""

from __future__ import annotations

import os
import uuid
from types import SimpleNamespace
from typing import Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest

try:
    from app.api.jobs import delete_job, DELETE_GLOWUP_REASON
    from fastapi import HTTPException, status

    _ROUTES_AVAILABLE = True
except (ImportError, AttributeError):
    _ROUTES_AVAILABLE = False

try:
    import psycopg2

    _PSYCOPG_AVAILABLE = True
except ImportError:
    _PSYCOPG_AVAILABLE = False

from tests.conftest import requires_routers


pytestmark = [
    pytest.mark.skipif(not _ROUTES_AVAILABLE, reason="jobs module unavailable"),
    requires_routers,
]


# ---------------------------------------------------------------------------
# Constants — no magic strings
# ---------------------------------------------------------------------------

_USER_ID = "u-owner"
_OTHER_USER_ID = "u-intruder"
_JOB_ID = "11111111-1111-1111-1111-111111111111"
_ANALYSIS_ID = "22222222-2222-2222-2222-222222222222"
_POST_ID = "33333333-3333-3333-3333-333333333333"

_RAW_SELFIES_BUCKET = "raw-selfies"
_GENERATED_IMAGES_BUCKET = "generated-images"
_POST_IMAGES_BUCKET = "post-images"

_SOURCE_TYPE_GLOWUP = "glowup_analysis"
_SOURCE_TYPE_MAKEUP = "makeup_session"

_STATUS_COMPLETED = "completed"
_STATUS_FAILED = "failed"
_STATUS_CANCELLED = "cancelled"
_STATUS_QUEUED = "queued"
_STATUS_PROCESSING = "processing"
_STATUS_FINALIZING = "finalizing"

_BEFORE_SELFIE_KEY = "raw-selfies/before.jpg"
_AFTER_GENERATED_KEY = "generated-images/after.jpg"
_POST_BEFORE_KEY = "post-images/post-before.jpg"
_POST_AFTER_KEY = "post-images/post-after.jpg"


# ---------------------------------------------------------------------------
# Helpers — mock builders
# ---------------------------------------------------------------------------


def _make_job(
    *,
    status_value: str = _STATUS_COMPLETED,
    user_id: str = _USER_ID,
    source_type: str = _SOURCE_TYPE_GLOWUP,
    source_id: str = _ANALYSIS_ID,
    before_image_url: str | None = _BEFORE_SELFIE_KEY,
    after_image_url: str | None = _AFTER_GENERATED_KEY,
) -> dict:
    return {
        "id": _JOB_ID,
        "user_id": user_id,
        "status": status_value,
        "source_type": source_type,
        "source_id": source_id,
        "before_image_url": before_image_url,
        "after_image_url": after_image_url,
    }


def _make_post(
    *,
    before_image_url: str = _POST_BEFORE_KEY,
    after_image_url: str = _POST_AFTER_KEY,
) -> dict:
    return {
        "id": _POST_ID,
        "user_id": _USER_ID,
        "glow_up_job_id": _JOB_ID,
        "before_image_url": before_image_url,
        "after_image_url": after_image_url,
    }


def _make_job_repo(
    *,
    job: dict | None = None,
    post: dict | None = None,
    peer_count: int = 1,
) -> MagicMock:
    """Build a JobRepository mock with happy-path defaults.

    ``peer_count`` is what ``count_peer_jobs_for_source`` returns — 1 by
    default so analysis stays. Pass 0 to exercise the analysis-delete path.
    """
    repo = MagicMock()
    repo.get_by_id.return_value = job

    # enumerate_blob_keys_for_delete returns list[tuple[bucket, key]].
    # Build it from the job + optional post per the production signature.
    blob_keys: list[tuple[str, str]] = []
    if job is not None:
        if job.get("before_image_url"):
            blob_keys.append((_RAW_SELFIES_BUCKET, job["before_image_url"]))
        if job.get("after_image_url"):
            blob_keys.append((_GENERATED_IMAGES_BUCKET, job["after_image_url"]))
    if post is not None:
        if post.get("before_image_url"):
            blob_keys.append((_POST_IMAGES_BUCKET, post["before_image_url"]))
        if post.get("after_image_url"):
            blob_keys.append((_POST_IMAGES_BUCKET, post["after_image_url"]))
    repo.enumerate_blob_keys_for_delete.return_value = blob_keys

    repo.count_peer_jobs_for_source.return_value = peer_count
    repo.delete_by_id.return_value = None
    repo.delete_analysis_by_id.return_value = None
    return repo


class _FakeRedisPipeline:
    """Async-compatible pipeline stub for rate-limiter tests.

    Returns ``[count, True]`` from execute. ``count`` controls whether the
    limiter allows the call — 1 through _MAX_ATTEMPTS = allow, over = deny.
    """

    def __init__(self, count: int = 1) -> None:
        self._count = count

    def incr(self, key: str) -> "_FakeRedisPipeline":
        return self

    def expire(self, key: str, ttl: int, nx: bool = False) -> "_FakeRedisPipeline":
        return self

    async def execute(self) -> list:
        return [self._count, True]


def _make_redis(*, limiter_count: int = 1, ttl_value: int = 0) -> MagicMock:
    """Redis mock with a configurable rate-limiter count."""
    redis_client = MagicMock()
    redis_client.pipeline = MagicMock(
        side_effect=lambda: _FakeRedisPipeline(count=limiter_count)
    )
    redis_client.ttl = AsyncMock(return_value=ttl_value)
    return redis_client


def _make_deps(
    *,
    job: dict | None,
    post: dict | None = None,
    peer_count: int = 1,
    limiter_count: int = 1,
    limiter_ttl: int = 0,
) -> SimpleNamespace:
    """Build the per-test dependency bundle.

    Note: the endpoint does not take a ``post_repo`` parameter — the
    post lookup is encapsulated inside
    ``JobRepository.enumerate_blob_keys_for_delete`` so the endpoint
    does not need to know about post-images enumeration. ``post`` is
    threaded through the ``job_repo`` mock's enumerate return value.
    """
    job_repo = _make_job_repo(job=job, post=post, peer_count=peer_count)

    image_repo = MagicMock()
    image_repo.remove.return_value = None

    orphan_repo = MagicMock()
    orphan_repo.record.return_value = None

    orphan_analyses_repo = MagicMock()
    orphan_analyses_repo.record.return_value = None

    redis_client = _make_redis(limiter_count=limiter_count, ttl_value=limiter_ttl)

    return SimpleNamespace(
        job_repo=job_repo,
        image_repo=image_repo,
        orphan_repo=orphan_repo,
        orphan_analyses_repo=orphan_analyses_repo,
        redis_client=redis_client,
    )


def _make_claims(user_id: str = _USER_ID) -> dict:
    return {"sub": user_id}


async def _passthrough_run_sync(fn, *args, **kwargs):
    return fn(*args, **kwargs)


# ---------------------------------------------------------------------------
# Scenarios A-L — endpoint-level mock tests
# ---------------------------------------------------------------------------


class TestDeleteGlowupCascade:
    """Endpoint-level tests — call ``delete_job`` directly with mocked deps."""

    @pytest.mark.asyncio
    async def test_happy_path_a_completed_no_post(self, monkeypatch):
        """A: completed job with no post — raw + generated wiped, no post-images
        touched, analysis stays (peers > 0), 204."""
        monkeypatch.setattr("app.api.jobs.run_sync", _passthrough_run_sync)

        job = _make_job()
        deps = _make_deps(job=job, post=None, peer_count=1)

        response = await delete_job(
            job_id=uuid.UUID(_JOB_ID),
            claims=_make_claims(),
            redis_client=deps.redis_client,
            job_repo=deps.job_repo,
            image_repo=deps.image_repo,
            orphan_repo=deps.orphan_repo,
            orphan_analyses_repo=deps.orphan_analyses_repo,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        deps.job_repo.delete_by_id.assert_called_once_with(_JOB_ID)
        deps.job_repo.delete_analysis_by_id.assert_not_called()

        # Exactly 2 remove calls: raw-selfies + generated-images.
        assert deps.image_repo.remove.call_count == 2
        call_args = [
            (c.args[0], c.args[1]) for c in deps.image_repo.remove.call_args_list
        ]
        assert (_RAW_SELFIES_BUCKET, [_BEFORE_SELFIE_KEY]) in call_args
        assert (_GENERATED_IMAGES_BUCKET, [_AFTER_GENERATED_KEY]) in call_args
        # No post-images wipe.
        for bucket, _ in call_args:
            assert bucket != _POST_IMAGES_BUCKET

    @pytest.mark.asyncio
    async def test_happy_path_b_completed_with_post(self, monkeypatch):
        """B: completed job WITH live post — all above + post-images wiped, 204."""
        monkeypatch.setattr("app.api.jobs.run_sync", _passthrough_run_sync)

        job = _make_job()
        post = _make_post()
        deps = _make_deps(job=job, post=post, peer_count=1)

        response = await delete_job(
            job_id=uuid.UUID(_JOB_ID),
            claims=_make_claims(),
            redis_client=deps.redis_client,
            job_repo=deps.job_repo,
            image_repo=deps.image_repo,
            orphan_repo=deps.orphan_repo,
            orphan_analyses_repo=deps.orphan_analyses_repo,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        deps.job_repo.delete_by_id.assert_called_once_with(_JOB_ID)

        # 4 remove calls now: raw + generated + 2× post-images (before, after).
        assert deps.image_repo.remove.call_count == 4
        call_tuples = [
            (c.args[0], c.args[1]) for c in deps.image_repo.remove.call_args_list
        ]
        assert (_RAW_SELFIES_BUCKET, [_BEFORE_SELFIE_KEY]) in call_tuples
        assert (_GENERATED_IMAGES_BUCKET, [_AFTER_GENERATED_KEY]) in call_tuples
        assert (_POST_IMAGES_BUCKET, [_POST_BEFORE_KEY]) in call_tuples
        assert (_POST_IMAGES_BUCKET, [_POST_AFTER_KEY]) in call_tuples

    @pytest.mark.asyncio
    async def test_happy_path_c_peers_zero_deletes_analysis(self, monkeypatch):
        """C: peers=0 + glowup source — analysis row also deleted."""
        monkeypatch.setattr("app.api.jobs.run_sync", _passthrough_run_sync)

        job = _make_job()
        deps = _make_deps(job=job, post=None, peer_count=0)

        response = await delete_job(
            job_id=uuid.UUID(_JOB_ID),
            claims=_make_claims(),
            redis_client=deps.redis_client,
            job_repo=deps.job_repo,
            image_repo=deps.image_repo,
            orphan_repo=deps.orphan_repo,
            orphan_analyses_repo=deps.orphan_analyses_repo,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        deps.job_repo.delete_by_id.assert_called_once_with(_JOB_ID)
        deps.job_repo.delete_analysis_by_id.assert_called_once_with(_ANALYSIS_ID)

    @pytest.mark.asyncio
    async def test_happy_path_d_peers_nonzero_analysis_survives(self, monkeypatch):
        """D: another undeleted job on same source_id — analysis survives."""
        monkeypatch.setattr("app.api.jobs.run_sync", _passthrough_run_sync)

        job = _make_job()
        deps = _make_deps(job=job, post=None, peer_count=2)

        response = await delete_job(
            job_id=uuid.UUID(_JOB_ID),
            claims=_make_claims(),
            redis_client=deps.redis_client,
            job_repo=deps.job_repo,
            image_repo=deps.image_repo,
            orphan_repo=deps.orphan_repo,
            orphan_analyses_repo=deps.orphan_analyses_repo,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        deps.job_repo.delete_analysis_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_happy_path_c2_non_glowup_source_skips_analysis_delete(
        self, monkeypatch
    ):
        """source_type != 'glowup_analysis' — never call delete_analysis_by_id.

        Jobs are polymorphic; makeup_sessions own their own lifecycle.
        Guards against a future regression where peers=0 bypasses the type check.
        """
        monkeypatch.setattr("app.api.jobs.run_sync", _passthrough_run_sync)

        job = _make_job(source_type=_SOURCE_TYPE_MAKEUP)
        deps = _make_deps(job=job, post=None, peer_count=0)

        response = await delete_job(
            job_id=uuid.UUID(_JOB_ID),
            claims=_make_claims(),
            redis_client=deps.redis_client,
            job_repo=deps.job_repo,
            image_repo=deps.image_repo,
            orphan_repo=deps.orphan_repo,
            orphan_analyses_repo=deps.orphan_analyses_repo,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        deps.job_repo.delete_analysis_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_edge_e_missing_job_returns_204(self, monkeypatch):
        """E: already-deleted / missing job → 204 idempotent, no side effects."""
        monkeypatch.setattr("app.api.jobs.run_sync", _passthrough_run_sync)

        deps = _make_deps(job=None, post=None)

        response = await delete_job(
            job_id=uuid.UUID(_JOB_ID),
            claims=_make_claims(),
            redis_client=deps.redis_client,
            job_repo=deps.job_repo,
            image_repo=deps.image_repo,
            orphan_repo=deps.orphan_repo,
            orphan_analyses_repo=deps.orphan_analyses_repo,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        deps.job_repo.delete_by_id.assert_not_called()
        deps.image_repo.remove.assert_not_called()
        deps.job_repo.delete_analysis_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_edge_f_wrong_owner_returns_204_no_leak(self, monkeypatch):
        """F: wrong owner → 204 (no enumeration leak).

        Divergence from GET/cancel/refund/save (which 404). Matches
        delete_account idempotent-204 posture — prevents retry confusion.
        """
        monkeypatch.setattr("app.api.jobs.run_sync", _passthrough_run_sync)

        # Job belongs to _USER_ID; claims say caller is _OTHER_USER_ID.
        job = _make_job(user_id=_USER_ID)
        deps = _make_deps(job=job, post=None)

        response = await delete_job(
            job_id=uuid.UUID(_JOB_ID),
            claims=_make_claims(user_id=_OTHER_USER_ID),
            redis_client=deps.redis_client,
            job_repo=deps.job_repo,
            image_repo=deps.image_repo,
            orphan_repo=deps.orphan_repo,
            orphan_analyses_repo=deps.orphan_analyses_repo,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        deps.job_repo.delete_by_id.assert_not_called()
        # Enumeration must not leak for a wrong owner — no image_repo.remove.
        deps.image_repo.remove.assert_not_called()

    @pytest.mark.asyncio
    async def test_edge_g_owner_still_authorized(self, monkeypatch):
        """G: authenticated owner with arbitrary uuid — handler cascade works."""
        monkeypatch.setattr("app.api.jobs.run_sync", _passthrough_run_sync)

        owner_id = "owner-uuid-1"
        job = _make_job(user_id=owner_id)
        deps = _make_deps(job=job, post=None)

        response = await delete_job(
            job_id=uuid.UUID(_JOB_ID),
            claims=_make_claims(user_id=owner_id),
            redis_client=deps.redis_client,
            job_repo=deps.job_repo,
            image_repo=deps.image_repo,
            orphan_repo=deps.orphan_repo,
            orphan_analyses_repo=deps.orphan_analyses_repo,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        deps.job_repo.delete_by_id.assert_called_once_with(_JOB_ID)

    @pytest.mark.asyncio
    async def test_edge_h_failed_job_cascades_same_as_completed(self, monkeypatch):
        """H: failed job — cascades same as completed (status is allowed)."""
        monkeypatch.setattr("app.api.jobs.run_sync", _passthrough_run_sync)

        job = _make_job(status_value=_STATUS_FAILED)
        deps = _make_deps(job=job, post=None)

        response = await delete_job(
            job_id=uuid.UUID(_JOB_ID),
            claims=_make_claims(),
            redis_client=deps.redis_client,
            job_repo=deps.job_repo,
            image_repo=deps.image_repo,
            orphan_repo=deps.orphan_repo,
            orphan_analyses_repo=deps.orphan_analyses_repo,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        deps.job_repo.delete_by_id.assert_called_once_with(_JOB_ID)

    @pytest.mark.asyncio
    async def test_edge_h2_cancelled_job_cascades(self, monkeypatch):
        """Cancelled jobs are explicitly in the allowed-delete set."""
        monkeypatch.setattr("app.api.jobs.run_sync", _passthrough_run_sync)

        job = _make_job(status_value=_STATUS_CANCELLED)
        deps = _make_deps(job=job, post=None)

        response = await delete_job(
            job_id=uuid.UUID(_JOB_ID),
            claims=_make_claims(),
            redis_client=deps.redis_client,
            job_repo=deps.job_repo,
            image_repo=deps.image_repo,
            orphan_repo=deps.orphan_repo,
            orphan_analyses_repo=deps.orphan_analyses_repo,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        deps.job_repo.delete_by_id.assert_called_once_with(_JOB_ID)

    @pytest.mark.asyncio
    async def test_error_i_processing_job_409_not_cancellable(self, monkeypatch):
        """I: processing job → 409 JOB_NOT_CANCELLABLE."""
        monkeypatch.setattr("app.api.jobs.run_sync", _passthrough_run_sync)

        job = _make_job(status_value=_STATUS_PROCESSING)
        deps = _make_deps(job=job, post=None)

        with pytest.raises(HTTPException) as exc_info:
            await delete_job(
                job_id=uuid.UUID(_JOB_ID),
                claims=_make_claims(),
                redis_client=deps.redis_client,
                job_repo=deps.job_repo,
                image_repo=deps.image_repo,
                orphan_repo=deps.orphan_repo,
                orphan_analyses_repo=deps.orphan_analyses_repo,
            )

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        detail = exc_info.value.detail
        # detail shape: {"error": {"code": "JOB_NOT_CANCELLABLE", "message": ...}}
        assert isinstance(detail, dict)
        assert detail["error"]["code"] == "JOB_NOT_CANCELLABLE"
        deps.job_repo.delete_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_error_j_queued_job_409_not_cancellable(self, monkeypatch):
        """J: queued job → 409 JOB_NOT_CANCELLABLE."""
        monkeypatch.setattr("app.api.jobs.run_sync", _passthrough_run_sync)

        job = _make_job(status_value=_STATUS_QUEUED)
        deps = _make_deps(job=job, post=None)

        with pytest.raises(HTTPException) as exc_info:
            await delete_job(
                job_id=uuid.UUID(_JOB_ID),
                claims=_make_claims(),
                redis_client=deps.redis_client,
                job_repo=deps.job_repo,
                image_repo=deps.image_repo,
                orphan_repo=deps.orphan_repo,
                orphan_analyses_repo=deps.orphan_analyses_repo,
            )

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        deps.job_repo.delete_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_error_j2_finalizing_job_409(self, monkeypatch):
        """Finalizing = in-flight ARQ. Must 409, not 204.

        Guards against a future regression that treats any non-terminal
        status as deletable and races the worker.
        """
        monkeypatch.setattr("app.api.jobs.run_sync", _passthrough_run_sync)

        job = _make_job(status_value=_STATUS_FINALIZING)
        deps = _make_deps(job=job, post=None)

        with pytest.raises(HTTPException) as exc_info:
            await delete_job(
                job_id=uuid.UUID(_JOB_ID),
                claims=_make_claims(),
                redis_client=deps.redis_client,
                job_repo=deps.job_repo,
                image_repo=deps.image_repo,
                orphan_repo=deps.orphan_repo,
                orphan_analyses_repo=deps.orphan_analyses_repo,
            )

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.asyncio
    async def test_error_k_blob_wipe_failure_dlqs_key_still_204(self, monkeypatch):
        """K: image_repo.remove raises for one key → that key lands in DLQ
        with reason="delete_glowup"; endpoint still returns 204; DB row gone."""
        monkeypatch.setattr("app.api.jobs.run_sync", _passthrough_run_sync)

        job = _make_job()
        post = _make_post()
        deps = _make_deps(job=job, post=post)

        # Fail only on the post-images before key; others succeed.
        def _remove_side_effect(bucket, keys):
            if bucket == _POST_IMAGES_BUCKET and keys == [_POST_BEFORE_KEY]:
                raise RuntimeError("storage 503")
            return None

        deps.image_repo.remove.side_effect = _remove_side_effect

        response = await delete_job(
            job_id=uuid.UUID(_JOB_ID),
            claims=_make_claims(),
            redis_client=deps.redis_client,
            job_repo=deps.job_repo,
            image_repo=deps.image_repo,
            orphan_repo=deps.orphan_repo,
            orphan_analyses_repo=deps.orphan_analyses_repo,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        # DB delete still fires.
        deps.job_repo.delete_by_id.assert_called_once_with(_JOB_ID)

        # DLQ records the failed key with reason="delete_glowup".
        recorded = {
            (c.args[0], c.args[1], c.args[2])
            for c in deps.orphan_repo.record.call_args_list
        }
        assert (_POST_IMAGES_BUCKET, _POST_BEFORE_KEY, DELETE_GLOWUP_REASON) in recorded

        # Only the failed key is in the DLQ — the others succeeded.
        assert len(recorded) == 1

    @pytest.mark.asyncio
    async def test_error_l_rate_limit_exceeded_429_with_retry_after(self, monkeypatch):
        """L: rate-limit exceeded → 429 with Retry-After header.

        P3a semantic: the limiter runs AFTER the fetch + owner check so a
        looping stale-ID sweep doesn't burn the real owner's budget. So
        ``get_by_id`` *is* called here (we need the job to decide if this
        is real destructive work); the load-bearing invariants are that
        the 429 fires, Retry-After is set, and no cascade/DB work runs.
        """
        monkeypatch.setattr("app.api.jobs.run_sync", _passthrough_run_sync)

        job = _make_job()
        # limiter_count above the max (10) = deny.
        deps = _make_deps(job=job, post=None, limiter_count=11, limiter_ttl=42)

        with pytest.raises(HTTPException) as exc_info:
            await delete_job(
                job_id=uuid.UUID(_JOB_ID),
                claims=_make_claims(),
                redis_client=deps.redis_client,
                job_repo=deps.job_repo,
                image_repo=deps.image_repo,
                orphan_repo=deps.orphan_repo,
                orphan_analyses_repo=deps.orphan_analyses_repo,
            )

        assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        headers = exc_info.value.headers or {}
        assert "Retry-After" in headers

        # Rate limit must short-circuit before cascade / blob wipe work.
        # ``get_by_id`` is now allowed (P3a moved the limiter below it);
        # the important invariants are no DB delete and no blob wipes.
        deps.job_repo.delete_by_id.assert_not_called()
        deps.image_repo.remove.assert_not_called()
        deps.job_repo.enumerate_blob_keys_for_delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_p3a_wrong_owner_does_not_consume_rate_limit(self, monkeypatch):
        """P3a: wrong-owner 204 bypasses the limiter entirely.

        A stolen-token sweep hammering someone else's stale job IDs must
        not grind the real owner's 10/min budget to zero. The limiter is
        checked only when we're about to do real destructive work.
        """
        monkeypatch.setattr("app.api.jobs.run_sync", _passthrough_run_sync)

        job = _make_job(user_id=_USER_ID)
        deps = _make_deps(job=job, post=None)

        response = await delete_job(
            job_id=uuid.UUID(_JOB_ID),
            claims=_make_claims(user_id=_OTHER_USER_ID),
            redis_client=deps.redis_client,
            job_repo=deps.job_repo,
            image_repo=deps.image_repo,
            orphan_repo=deps.orphan_repo,
            orphan_analyses_repo=deps.orphan_analyses_repo,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        # Limiter INCRements every call, so the cleanest proof of "no
        # budget consumed" is "the limiter was never invoked at all".
        deps.redis_client.pipeline.assert_not_called()

    @pytest.mark.asyncio
    async def test_p3a_missing_job_does_not_consume_rate_limit(self, monkeypatch):
        """P3a: missing-job 204 bypasses the limiter entirely.

        Matches the wrong-owner case — idempotent no-op 204 must not
        charge the caller's budget. Otherwise a client retrying after a
        flaky network could silently exhaust itself on already-deleted
        IDs and 429 on the next real delete.
        """
        monkeypatch.setattr("app.api.jobs.run_sync", _passthrough_run_sync)

        deps = _make_deps(job=None, post=None)

        response = await delete_job(
            job_id=uuid.UUID(_JOB_ID),
            claims=_make_claims(),
            redis_client=deps.redis_client,
            job_repo=deps.job_repo,
            image_repo=deps.image_repo,
            orphan_repo=deps.orphan_repo,
            orphan_analyses_repo=deps.orphan_analyses_repo,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        deps.redis_client.pipeline.assert_not_called()

    @pytest.mark.asyncio
    async def test_p3a_real_owned_delete_still_consumes_rate_limit(self, monkeypatch):
        """P3a: a real owned delete DOES hit the limiter.

        Complement to the two no-op tests above — proves the limiter
        isn't accidentally bypassed on the destructive path. Equivalent
        to the 11th-real-delete-429 scenario at the unit level.
        """
        monkeypatch.setattr("app.api.jobs.run_sync", _passthrough_run_sync)

        job = _make_job()
        deps = _make_deps(job=job, post=None)

        response = await delete_job(
            job_id=uuid.UUID(_JOB_ID),
            claims=_make_claims(),
            redis_client=deps.redis_client,
            job_repo=deps.job_repo,
            image_repo=deps.image_repo,
            orphan_repo=deps.orphan_repo,
            orphan_analyses_repo=deps.orphan_analyses_repo,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        # Real destructive work → the limiter pipeline ran exactly once.
        assert deps.redis_client.pipeline.call_count == 1

    @pytest.mark.asyncio
    async def test_enumeration_runs_before_db_delete(self, monkeypatch):
        """ORDER MATTERS — enumerate blob keys BEFORE DELETE FROM jobs.

        If reversed, the post-images join vanishes with the cascade and
        those blobs would orphan silently.
        """
        monkeypatch.setattr("app.api.jobs.run_sync", _passthrough_run_sync)

        job = _make_job()
        post = _make_post()
        deps = _make_deps(job=job, post=post)

        call_order: list[str] = []
        deps.job_repo.enumerate_blob_keys_for_delete.side_effect = lambda *_a, **_k: (
            call_order.append("enumerate"),
            [
                (_RAW_SELFIES_BUCKET, _BEFORE_SELFIE_KEY),
                (_GENERATED_IMAGES_BUCKET, _AFTER_GENERATED_KEY),
                (_POST_IMAGES_BUCKET, _POST_BEFORE_KEY),
                (_POST_IMAGES_BUCKET, _POST_AFTER_KEY),
            ],
        )[-1]
        deps.job_repo.delete_by_id.side_effect = lambda *_a, **_k: call_order.append(
            "delete_job"
        )
        deps.image_repo.remove.side_effect = lambda *_a, **_k: call_order.append(
            "blob_wipe"
        )

        response = await delete_job(
            job_id=uuid.UUID(_JOB_ID),
            claims=_make_claims(),
            redis_client=deps.redis_client,
            job_repo=deps.job_repo,
            image_repo=deps.image_repo,
            orphan_repo=deps.orphan_repo,
            orphan_analyses_repo=deps.orphan_analyses_repo,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        # Enumeration must happen before the cascade — otherwise the
        # denormalized post-images keys on posts.before/after_image_url
        # are gone and cannot be recovered for blob wipe.
        assert call_order.index("enumerate") < call_order.index("delete_job")

    @pytest.mark.asyncio
    async def test_analytics_emit_failure_does_not_break_request(self, monkeypatch):
        """Analytics exception must not fail the request (mirrors glowup_save)."""
        monkeypatch.setattr("app.api.jobs.run_sync", _passthrough_run_sync)

        def _boom(**_k):
            raise RuntimeError("analytics sink down")

        monkeypatch.setattr("app.api.jobs.events.glowup_delete", _boom)

        job = _make_job()
        deps = _make_deps(job=job, post=None)

        response = await delete_job(
            job_id=uuid.UUID(_JOB_ID),
            claims=_make_claims(),
            redis_client=deps.redis_client,
            job_repo=deps.job_repo,
            image_repo=deps.image_repo,
            orphan_repo=deps.orphan_repo,
            orphan_analyses_repo=deps.orphan_analyses_repo,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        deps.job_repo.delete_by_id.assert_called_once_with(_JOB_ID)


# ---------------------------------------------------------------------------
# Scenario M — live-DB integration test
# ---------------------------------------------------------------------------


_DEFAULT_LOCAL_DSN = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
_USER_TIER_TRIAL = "TRIAL"
_IMAGE_TYPE_BEFORE = "generated_before"
_IMAGE_TYPE_AFTER = "generated_after"
_IMAGE_STATUS_CLEARED = "cleared"


def _get_dsn() -> str:
    return os.environ.get("DATABASE_URL", _DEFAULT_LOCAL_DSN)


def _db_reachable() -> bool:
    if not _PSYCOPG_AVAILABLE:
        return False
    try:
        conn = psycopg2.connect(_get_dsn(), connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


@pytest.fixture
def db_conn() -> Iterator[object]:
    """Transactional connection; roll back writes at teardown."""
    if not _PSYCOPG_AVAILABLE:
        pytest.skip("psycopg2 not installed")
    conn = psycopg2.connect(_get_dsn())
    conn.autocommit = False
    try:
        yield conn
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()


class TestDeleteGlowupLiveDB:
    """Scenario M — real-DB cascade of jobs → posts → reactions/comments/reports."""

    pytestmark = [
        pytest.mark.skipif(
            not _PSYCOPG_AVAILABLE,
            reason="psycopg2 not installed — install backend deps",
        ),
        pytest.mark.skipif(
            not _db_reachable(),
            reason=f"local Postgres not reachable at {_get_dsn()}",
        ),
    ]

    def test_delete_job_cascades_all_children_on_live_schema(self, db_conn) -> None:
        """DELETE FROM jobs cascades posts + reactions + comments + reports.

        Also proves the ``share_hash`` lookup yields no row after the
        cascade — that's precisely what
        ``GET /v1/public/cards/{username}/{share_hash}`` relies on to 404
        (see ``post_repo.get_by_share_hash`` — filters ``is_deleted=FALSE``,
        which a cascaded/deleted post can never satisfy).

        Same FK coverage as test_posts_unique_constraint::test_delete_
        job_cascades_to_post_and_all_children, but kept here too so
        someone running only the cascade test file sees the integration
        fail immediately when an FK drifts away from ON DELETE CASCADE.
        Uses psycopg2 directly (matches the precedent in
        test_posts_unique_constraint.py) — a full TestClient + real-app
        HTTP integration would need a running Supabase + Redis + seeded
        auth JWT, which is out of scope for this unit. The mock-based
        endpoint tests A-L prove the handler's full control flow.
        """
        cur = db_conn.cursor()

        # Insert minimum-shape rows.
        suffix = uuid.uuid4().hex[:12]
        cur.execute(
            """
            INSERT INTO users (username, display_name, email_verified)
            VALUES (%s, %s, FALSE)
            RETURNING id
            """,
            (f"testuser_{suffix}", f"Test {suffix}"),
        )
        user_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO jobs (
                user_id, source_type, source_id, status, user_tier_at_enqueue
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                user_id,
                _SOURCE_TYPE_GLOWUP,
                str(uuid.uuid4()),
                _STATUS_COMPLETED,
                _USER_TIER_TRIAL,
            ),
        )
        job_id = cur.fetchone()[0]

        # Insert images — required by posts before/after FKs.
        def _insert_image(image_type: str) -> str:
            cur.execute(
                """
                INSERT INTO images (user_id, storage_key, bucket, image_type, status)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    user_id,
                    f"post-images/{uuid.uuid4().hex}.jpg",
                    "post-images",
                    image_type,
                    _IMAGE_STATUS_CLEARED,
                ),
            )
            return cur.fetchone()[0]

        before_id = _insert_image(_IMAGE_TYPE_BEFORE)
        after_id = _insert_image(_IMAGE_TYPE_AFTER)

        cur.execute(
            """
            INSERT INTO posts (
                user_id, glow_up_job_id, before_image_id, after_image_id,
                before_image_url, after_image_url, is_deleted, is_hidden
            )
            VALUES (%s, %s, %s, %s, %s, %s, FALSE, FALSE)
            RETURNING id, share_hash
            """,
            (
                user_id,
                job_id,
                before_id,
                after_id,
                "post-images/before.jpg",
                "post-images/after.jpg",
            ),
        )
        post_row = cur.fetchone()
        post_id = post_row[0]
        share_hash = post_row[1]

        cur.execute(
            "INSERT INTO reactions (post_id, user_id) VALUES (%s, %s) RETURNING id",
            (post_id, user_id),
        )
        reaction_id = cur.fetchone()[0]

        cur.execute(
            "INSERT INTO comments (post_id, user_id, content) VALUES (%s, %s, %s) RETURNING id",
            (post_id, user_id, "looks great"),
        )
        comment_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO reports (post_id, reporter_user_id, reason, status)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (post_id, user_id, "spam", "pending"),
        )
        report_id = cur.fetchone()[0]

        # Precondition: everything exists.
        def _exists(table: str, row_id: str) -> bool:
            cur.execute(f"SELECT 1 FROM {table} WHERE id = %s", (row_id,))
            return cur.fetchone() is not None

        assert _exists("posts", post_id)
        assert _exists("reactions", reaction_id)
        assert _exists("comments", comment_id)
        assert _exists("reports", report_id)

        # Act — DELETE FROM jobs. FK cascade wipes the rest.
        cur.execute("DELETE FROM jobs WHERE id = %s", (job_id,))

        # Post-condition: all children gone by cascade.
        assert not _exists("posts", post_id), (
            "posts cascade broken — FK posts_glow_up_job_id_fkey is not CASCADE"
        )
        assert not _exists("reactions", reaction_id), (
            "reactions cascade broken — FK reactions_post_id_fkey is not CASCADE"
        )
        assert not _exists("comments", comment_id), (
            "comments cascade broken — FK comments_post_id_fkey is not CASCADE"
        )
        assert not _exists("reports", report_id), (
            "reports cascade broken — FK reports_post_id_fkey is not CASCADE"
        )

        # R5 invariant — the share_hash contract must be unreachable after
        # cascade. ``get_by_share_hash`` filters ``is_deleted = FALSE``,
        # which a cascaded/deleted post can never satisfy, so
        # ``GET /v1/public/cards/{username}/{share_hash}`` 404s.
        cur.execute(
            "SELECT 1 FROM posts WHERE share_hash = %s AND is_deleted = FALSE",
            (share_hash,),
        )
        assert cur.fetchone() is None, (
            "share_hash still resolves after cascade — /v1/public/cards/"
            "{username}/{share_hash} would NOT return 404"
        )
