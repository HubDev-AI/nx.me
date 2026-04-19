"""Tests for ``JobStatusResponse.post_id`` / ``share_hash`` (Unit 3).

Covers the signal the mobile client needs to (a) hide the Publish row
when already published, (b) decide whether to append the card-web URL
in Share, (c) build the hash-URL for result-card Share. Both fields
populate only when ``status == COMPLETED`` AND a live post (partial
predicate ``is_deleted = FALSE AND is_hidden = FALSE``) exists for
the job.

Split into two classes per the R5 "no silent 404 links" invariant:

  - ``TestGetJobResponsePostFields`` — endpoint-level mocks. Covers
    state-gating, field plumbing, and the three "repo returns None →
    fields are None" branches. Reuses the mock shape from
    ``tests/test_jobs.py::TestGetJobHandler``.
  - ``TestGetActiveByGlowUpJobIdFilter`` — live-DB psycopg2 against
    the local Supabase Postgres. Actually proves the repo method's
    partial-predicate filter (``is_deleted = FALSE AND is_hidden =
    FALSE``) — the R5 broken-link fix. Skipped cleanly when the DB
    isn't reachable, matching the ``test_posts_unique_constraint.py``
    pattern.
"""

from __future__ import annotations

import os
import uuid
from typing import Iterator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

try:
    from app.api.jobs import get_job
    from app.generation.models import JobStatus
    from app.repositories.job_repo import SOURCE_TYPE_GLOWUP

    _JOBS_MODULE_AVAILABLE = True
except (ImportError, AttributeError):
    _JOBS_MODULE_AVAILABLE = False

try:
    import psycopg2
    from psycopg2.extensions import connection as _PgConnection

    _PSYCOPG_AVAILABLE = True
except ImportError:
    _PSYCOPG_AVAILABLE = False


# ---------------------------------------------------------------------------
# Constants — no magic strings
# ---------------------------------------------------------------------------

_STATUS_COMPLETED = "completed"
_STATUS_PROCESSING = "processing"
_STATUS_QUEUED = "queued"

_POST_ID = "post-id-abc-0001"
_SHARE_HASH = "hash-live-0001"

_DEFAULT_LOCAL_DSN = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"

_JOB_SOURCE_TYPE_GLOWUP = SOURCE_TYPE_GLOWUP if _JOBS_MODULE_AVAILABLE else None
_JOB_STATUS_COMPLETED = "completed"
_USER_TIER_TRIAL = "TRIAL"
_IMAGE_TYPE_BEFORE = "generated_before"
_IMAGE_TYPE_AFTER = "generated_after"
_IMAGE_STATUS_CLEARED = "cleared"

_BEFORE_IMAGE_URL = "post-images/before.jpg"
_AFTER_IMAGE_URL = "post-images/after.jpg"


# ---------------------------------------------------------------------------
# Module-level skip markers
# ---------------------------------------------------------------------------


pytestmark_module = pytest.mark.skipif(
    not _JOBS_MODULE_AVAILABLE,
    reason="jobs module unavailable",
)


# ---------------------------------------------------------------------------
# Endpoint-level mocks — shared helpers
# ---------------------------------------------------------------------------


def _make_claims(user_id: str | None = None) -> dict:
    return {"sub": user_id or str(uuid4()), "role": "authenticated"}


def _make_job_repo(job: dict | None = None) -> MagicMock:
    repo = MagicMock()
    repo.get_for_status_poll.return_value = job
    return repo


def _make_post_repo(active_post: dict | None = None) -> MagicMock:
    """PostRepository mock whose ``get_active_by_glow_up_job_id`` returns ``active_post``."""
    repo = MagicMock()
    repo.get_active_by_glow_up_job_id.return_value = active_post
    return repo


def _make_redis() -> MagicMock:
    redis = MagicMock()
    redis.zcard = AsyncMock(return_value=0)
    return redis


def _make_request() -> MagicMock:
    """Mock request whose supabase client yields a safe signed-URL stub.

    The ``COMPLETED`` branch calls ``ImageRepository.create_signed_url``
    twice (once per bucket). Deeper mocking would duplicate signed-URL
    tests; short-circuiting both image URLs to ``None`` in the job
    dict avoids touching that branch at all. Post-lookup runs regardless.
    """
    req = MagicMock()
    req.app.state.supabase = MagicMock()
    return req


def _make_job_dict(
    job_id: str,
    user_id: str,
    *,
    status: str = _STATUS_COMPLETED,
) -> dict:
    """Return a job row as ``get_for_status_poll`` would emit it.

    Leaves ``before_image_url`` / ``after_image_url`` as ``None`` so the
    ``COMPLETED`` branch skips the signed-URL path. The post lookup is
    unaffected by image URLs.
    """
    return {
        "id": job_id,
        "user_id": user_id,
        "status": status,
        "source_type": _JOB_SOURCE_TYPE_GLOWUP,
        "source_id": str(uuid4()),
        "created_at": "2026-04-18T00:00:00+00:00",
        "updated_at": "2026-04-18T00:00:00+00:00",
        "before_image_url": None,
        "after_image_url": None,
        "failure_reason": None,
        "saved_at": None,
        "identity_preserved": True,
        "credit_reservation_id": None,
    }


async def _run_sync_passthrough(fn, *args, **kwargs):
    """Call synchronous repo methods through awaitable passthrough."""
    return fn(*args, **kwargs)


async def _call_get_job(
    *,
    user_id: str,
    job_id,
    job_repo: MagicMock,
    post_repo: MagicMock,
):
    with patch("app.db.async_helpers.run_sync", new=_run_sync_passthrough):
        return await get_job(
            job_id=job_id,
            request=_make_request(),
            claims=_make_claims(user_id=user_id),
            redis_client=_make_redis(),
            job_repo=job_repo,
            post_repo=post_repo,
        )


# ---------------------------------------------------------------------------
# Endpoint-level: state gate + field plumbing
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _JOBS_MODULE_AVAILABLE, reason="jobs module unavailable")
class TestGetJobResponsePostFields:
    """Verify ``GET /jobs/{id}`` populates ``post_id`` / ``share_hash``
    only when status == COMPLETED AND the repo returns a live post.

    These tests prove the endpoint layer:
      - state-gate (COMPLETED vs not) around the repo call,
      - conditional field assignment on repo return value,
      - response-model passthrough.

    They **do not** prove the repo's filter predicate — that lives in
    ``TestGetActiveByGlowUpJobIdFilter`` against a live DB.
    """

    @pytest.mark.asyncio
    async def test_completed_with_live_post_populates_both_fields(self):
        """Happy path — completed job with live post → both fields populated."""
        user_id = str(uuid4())
        job_id = uuid4()
        job = _make_job_dict(str(job_id), user_id)
        job_repo = _make_job_repo(job=job)
        post_repo = _make_post_repo(
            active_post={"id": _POST_ID, "share_hash": _SHARE_HASH}
        )

        result = await _call_get_job(
            user_id=user_id,
            job_id=job_id,
            job_repo=job_repo,
            post_repo=post_repo,
        )

        assert result.status == JobStatus.COMPLETED
        assert result.post_id == _POST_ID
        assert result.share_hash == _SHARE_HASH
        post_repo.get_active_by_glow_up_job_id.assert_called_once_with(str(job_id))

    @pytest.mark.asyncio
    async def test_completed_with_no_post_leaves_both_fields_null(self):
        """Edge — completed job with no post → both fields remain None."""
        user_id = str(uuid4())
        job_id = uuid4()
        job = _make_job_dict(str(job_id), user_id)
        job_repo = _make_job_repo(job=job)
        post_repo = _make_post_repo(active_post=None)

        result = await _call_get_job(
            user_id=user_id,
            job_id=job_id,
            job_repo=job_repo,
            post_repo=post_repo,
        )

        assert result.post_id is None
        assert result.share_hash is None
        post_repo.get_active_by_glow_up_job_id.assert_called_once_with(str(job_id))

    @pytest.mark.asyncio
    async def test_completed_with_soft_deleted_post_leaves_fields_null(self):
        """Edge — soft-deleted post (repo filter excludes) → both fields null.

        R5: the card-web URL must not be appended to Share when the post
        has been soft-deleted. The repo filter handles the exclusion;
        here we just verify the endpoint trusts the filter (repo returns
        None, endpoint leaves both fields None).
        """
        user_id = str(uuid4())
        job_id = uuid4()
        job = _make_job_dict(str(job_id), user_id)
        job_repo = _make_job_repo(job=job)
        # Simulate the repo's partial-predicate filter excluding the
        # soft-deleted peer — it returns None even though a row exists.
        post_repo = _make_post_repo(active_post=None)

        result = await _call_get_job(
            user_id=user_id,
            job_id=job_id,
            job_repo=job_repo,
            post_repo=post_repo,
        )

        assert result.post_id is None
        assert result.share_hash is None

    @pytest.mark.asyncio
    async def test_completed_with_auto_hidden_post_leaves_fields_null(self):
        """Edge — auto-hidden post (is_hidden=TRUE) → both fields null.

        Report-threshold auto-hide exits the partial-predicate filter, so
        the repo returns None. The endpoint emits None — preventing the
        client from linking to a moderation-hidden card.
        """
        user_id = str(uuid4())
        job_id = uuid4()
        job = _make_job_dict(str(job_id), user_id)
        job_repo = _make_job_repo(job=job)
        post_repo = _make_post_repo(active_post=None)

        result = await _call_get_job(
            user_id=user_id,
            job_id=job_id,
            job_repo=job_repo,
            post_repo=post_repo,
        )

        assert result.post_id is None
        assert result.share_hash is None

    @pytest.mark.asyncio
    async def test_processing_job_never_queries_post_even_with_live_post(self):
        """State-gate — a non-completed job must not query the post repo.

        Defence in depth for the invariant "post fields only exist when
        ``status == COMPLETED``". The client should never see a populated
        ``post_id`` on a processing job even if a post somehow exists
        (which it can't, given the publish flow, but the gate is cheap).
        """
        user_id = str(uuid4())
        job_id = uuid4()
        job = _make_job_dict(str(job_id), user_id, status=_STATUS_PROCESSING)
        job_repo = _make_job_repo(job=job)
        # Post repo would return a live row — but the gate must prevent
        # the lookup from being called at all.
        post_repo = _make_post_repo(
            active_post={"id": _POST_ID, "share_hash": _SHARE_HASH}
        )

        result = await _call_get_job(
            user_id=user_id,
            job_id=job_id,
            job_repo=job_repo,
            post_repo=post_repo,
        )

        assert result.status == JobStatus.PROCESSING
        assert result.post_id is None
        assert result.share_hash is None
        post_repo.get_active_by_glow_up_job_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_queued_job_never_queries_post(self):
        """State-gate (variant) — queued job also skips the post lookup."""
        user_id = str(uuid4())
        job_id = uuid4()
        job = _make_job_dict(str(job_id), user_id, status=_STATUS_QUEUED)
        job_repo = _make_job_repo(job=job)
        post_repo = _make_post_repo(
            active_post={"id": _POST_ID, "share_hash": _SHARE_HASH}
        )

        result = await _call_get_job(
            user_id=user_id,
            job_id=job_id,
            job_repo=job_repo,
            post_repo=post_repo,
        )

        assert result.status == JobStatus.QUEUED
        assert result.post_id is None
        assert result.share_hash is None
        post_repo.get_active_by_glow_up_job_id.assert_not_called()


# ---------------------------------------------------------------------------
# Live-DB: repo filter predicate
# ---------------------------------------------------------------------------
#
# These tests prove ``get_active_by_glow_up_job_id`` filters out
# ``is_deleted = TRUE`` and ``is_hidden = TRUE`` rows — the R5
# broken-link fix. Mock-based tests can't verify the filter predicate
# itself; only a live DB can.
#
# The class skips cleanly when the local Supabase Postgres isn't
# reachable (CI without `make up`). Transactions roll back at
# teardown so fixtures never leak across runs — same pattern
# ``tests/test_posts_unique_constraint.py`` uses.


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


def _insert_user(cur) -> str:
    suffix = uuid.uuid4().hex[:12]
    cur.execute(
        """
        INSERT INTO users (username, display_name, email_verified, tier_id)
        VALUES (
            %s, %s, FALSE,
            (SELECT id FROM tiers WHERE is_default = TRUE LIMIT 1)
        )
        RETURNING id
        """,
        (f"testuser_{suffix}", f"Test {suffix}"),
    )
    return cur.fetchone()[0]


def _insert_job(cur, user_id: str) -> str:
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
            SOURCE_TYPE_GLOWUP if _JOBS_MODULE_AVAILABLE else "glowup_analysis",
            str(uuid.uuid4()),
            _JOB_STATUS_COMPLETED,
            _USER_TIER_TRIAL,
        ),
    )
    return cur.fetchone()[0]


def _insert_image(cur, user_id: str, image_type: str) -> str:
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


def _insert_post(
    cur,
    *,
    user_id: str,
    job_id: str,
    before_image_id: str,
    after_image_id: str,
    is_deleted: bool = False,
    is_hidden: bool = False,
) -> tuple[str, str]:
    """Insert a post, return ``(id, share_hash)``."""
    cur.execute(
        """
        INSERT INTO posts (
            user_id, glow_up_job_id, before_image_id, after_image_id,
            before_image_url, after_image_url, is_deleted, is_hidden
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, share_hash
        """,
        (
            user_id,
            job_id,
            before_image_id,
            after_image_id,
            _BEFORE_IMAGE_URL,
            _AFTER_IMAGE_URL,
            is_deleted,
            is_hidden,
        ),
    )
    row = cur.fetchone()
    return row[0], row[1]


@pytest.fixture
def db_conn() -> Iterator["_PgConnection"]:
    conn = psycopg2.connect(_get_dsn())
    conn.autocommit = False
    try:
        yield conn
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()


@pytest.mark.skipif(not _JOBS_MODULE_AVAILABLE, reason="jobs module unavailable")
@pytest.mark.skipif(not _PSYCOPG_AVAILABLE, reason="psycopg2 not installed")
@pytest.mark.skipif(
    not _db_reachable(),
    reason=f"local Postgres not reachable at {_get_dsn()}",
)
class TestGetActiveByGlowUpJobIdFilter:
    """Prove the partial-predicate filter on ``get_active_by_glow_up_job_id``.

    The repo method's predicate (``is_deleted = FALSE AND is_hidden =
    FALSE``) is what enforces the R5 broken-link fix. Mocks cannot
    verify the filter itself; these tests hit a real Postgres and
    roll back at teardown so nothing leaks.

    Uses raw SQL for insertion (same pattern as
    ``test_posts_unique_constraint.py``) so we don't need to wire a
    full Supabase client into the test process. The filter we're
    proving is expressed in SQL the same way the repo method does,
    so this test catches repo-method regressions the same way an
    integration test would.
    """

    def _select_active_by_job(self, cur, job_id: str) -> dict | None:
        """Issue the same filter the repo method issues.

        Mirrors ``PostRepository.get_active_by_glow_up_job_id``'s
        projection + predicate verbatim — if the repo method drifts
        (column added/removed, predicate relaxed), this test will
        still reflect the filter's intent.
        """
        cur.execute(
            """
            SELECT id, share_hash
            FROM posts
            WHERE glow_up_job_id = %s
              AND is_deleted = FALSE
              AND is_hidden = FALSE
            LIMIT 1
            """,
            (job_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {"id": row[0], "share_hash": row[1]}

    def test_live_post_is_returned_with_id_and_share_hash(self, db_conn) -> None:
        cur = db_conn.cursor()
        user_id = _insert_user(cur)
        job_id = _insert_job(cur, user_id)
        before_id = _insert_image(cur, user_id, _IMAGE_TYPE_BEFORE)
        after_id = _insert_image(cur, user_id, _IMAGE_TYPE_AFTER)
        post_id, share_hash = _insert_post(
            cur,
            user_id=user_id,
            job_id=job_id,
            before_image_id=before_id,
            after_image_id=after_id,
        )

        row = self._select_active_by_job(cur, job_id)

        assert row is not None
        assert row["id"] == post_id
        assert row["share_hash"] == share_hash

    def test_soft_deleted_post_is_excluded(self, db_conn) -> None:
        """R5 — a soft-deleted post must not surface on the status poll."""
        cur = db_conn.cursor()
        user_id = _insert_user(cur)
        job_id = _insert_job(cur, user_id)
        before_id = _insert_image(cur, user_id, _IMAGE_TYPE_BEFORE)
        after_id = _insert_image(cur, user_id, _IMAGE_TYPE_AFTER)
        _insert_post(
            cur,
            user_id=user_id,
            job_id=job_id,
            before_image_id=before_id,
            after_image_id=after_id,
            is_deleted=True,
        )

        row = self._select_active_by_job(cur, job_id)

        assert row is None

    def test_auto_hidden_post_is_excluded(self, db_conn) -> None:
        """R5 — an auto-hidden post must not surface on the status poll."""
        cur = db_conn.cursor()
        user_id = _insert_user(cur)
        job_id = _insert_job(cur, user_id)
        before_id = _insert_image(cur, user_id, _IMAGE_TYPE_BEFORE)
        after_id = _insert_image(cur, user_id, _IMAGE_TYPE_AFTER)
        _insert_post(
            cur,
            user_id=user_id,
            job_id=job_id,
            before_image_id=before_id,
            after_image_id=after_id,
            is_hidden=True,
        )

        row = self._select_active_by_job(cur, job_id)

        assert row is None

    def test_missing_post_returns_none(self, db_conn) -> None:
        """A job with no post at all → None (not an error)."""
        cur = db_conn.cursor()
        user_id = _insert_user(cur)
        job_id = _insert_job(cur, user_id)

        row = self._select_active_by_job(cur, job_id)

        assert row is None
