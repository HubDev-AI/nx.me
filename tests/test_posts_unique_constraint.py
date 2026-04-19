"""Live-DB tests for migration 0046.

Exercises the new partial UNIQUE index on ``posts.glow_up_job_id`` and
the end-to-end FK cascade from ``jobs → posts → reactions/comments/
reports``. Uses psycopg2 against the local Supabase Postgres at
``127.0.0.1:54322`` because FK + partial-index behavior is schema-level
and cannot be proved with Python mocks.

Each test wraps its writes in a single transaction that is rolled back
at teardown, so fixtures never leak across runs. The migration itself
(the index) is a precondition — it stays applied between runs, which
is fine.

Tests skip cleanly if the DB isn't reachable (CI without Supabase).
"""

from __future__ import annotations

import os
import uuid
from typing import Iterator

import pytest

try:
    import psycopg2
    from psycopg2 import errors as pg_errors
    from psycopg2.extensions import connection as _PgConnection

    _PSYCOPG_AVAILABLE = True
except ImportError:
    _PSYCOPG_AVAILABLE = False


# ---------------------------------------------------------------------------
# Constants — no magic strings
# ---------------------------------------------------------------------------

# Local-Supabase default DSN. Matches `scripts/local-env.sh` and the DSN the
# migration runner reads from DATABASE_URL. Falls back to the env var when
# set (e.g. for CI pointing at a throwaway Postgres).
_DEFAULT_LOCAL_DSN = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"

_JOB_SOURCE_TYPE_GLOWUP = "glowup_analysis"
_JOB_STATUS_COMPLETED = "completed"
_USER_TIER_TRIAL = "TRIAL"
_IMAGE_TYPE_BEFORE = "generated_before"
_IMAGE_TYPE_AFTER = "generated_after"
_IMAGE_STATUS_CLEARED = "cleared"
_REPORT_STATUS_PENDING = "pending"

_UNIQUE_VIOLATION_SQLSTATE = "23505"
_PARTIAL_UNIQUE_INDEX_NAME = "idx_posts_live_glow_up_job_id"

_BEFORE_IMAGE_URL = "post-images/before.jpg"
_AFTER_IMAGE_URL = "post-images/after.jpg"
_COMMENT_CONTENT = "looks great"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _get_dsn() -> str:
    """Resolve the DSN the same way the migration runner does."""
    return os.environ.get("DATABASE_URL", _DEFAULT_LOCAL_DSN)


def _db_reachable() -> bool:
    """Return True iff a Postgres connection at the DSN succeeds quickly."""
    if not _PSYCOPG_AVAILABLE:
        return False
    try:
        conn = psycopg2.connect(_get_dsn(), connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


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


@pytest.fixture
def db_conn() -> Iterator[_PgConnection]:
    """Yield a transactional connection; roll back all writes at teardown."""
    conn = psycopg2.connect(_get_dsn())
    conn.autocommit = False
    try:
        yield conn
    finally:
        # Roll back regardless of test outcome so the DB stays clean.
        try:
            conn.rollback()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Helpers — minimum-shape row inserts.
#
# These touch only the NOT NULL columns required by the live schema (see
# migrations 0001, 0027, 0034, 0039, 0045). They return the inserted id so
# each test can string them together without SQL bookkeeping.
# ---------------------------------------------------------------------------


def _insert_user(cur) -> str:
    """Insert a user with a unique username; return id."""
    suffix = uuid.uuid4().hex[:12]
    cur.execute(
        """
        INSERT INTO users (username, display_name, email_verified)
        VALUES (%s, %s, FALSE)
        RETURNING id
        """,
        (f"testuser_{suffix}", f"Test {suffix}"),
    )
    return cur.fetchone()[0]


def _insert_job(cur, user_id: str) -> str:
    """Insert a completed glow-up job; return job id."""
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
            _JOB_SOURCE_TYPE_GLOWUP,
            str(uuid.uuid4()),
            _JOB_STATUS_COMPLETED,
            _USER_TIER_TRIAL,
        ),
    )
    return cur.fetchone()[0]


def _insert_image(cur, user_id: str, image_type: str) -> str:
    """Insert a cleared image; return image id."""
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
) -> str:
    """Insert a post; return post id. Caller picks is_deleted / is_hidden."""
    cur.execute(
        """
        INSERT INTO posts (
            user_id, glow_up_job_id, before_image_id, after_image_id,
            before_image_url, after_image_url, is_deleted, is_hidden
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
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
    return cur.fetchone()[0]


def _insert_reaction(cur, *, post_id: str, user_id: str) -> str:
    """Insert a user-attributed reaction; return reaction id."""
    cur.execute(
        """
        INSERT INTO reactions (post_id, user_id)
        VALUES (%s, %s)
        RETURNING id
        """,
        (post_id, user_id),
    )
    return cur.fetchone()[0]


def _insert_comment(cur, *, post_id: str, user_id: str) -> str:
    """Insert a comment; return comment id."""
    cur.execute(
        """
        INSERT INTO comments (post_id, user_id, content)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (post_id, user_id, _COMMENT_CONTENT),
    )
    return cur.fetchone()[0]


def _insert_report(cur, *, post_id: str, reporter_user_id: str) -> str:
    """Insert a pending report; return report id."""
    cur.execute(
        """
        INSERT INTO reports (post_id, reporter_user_id, reason, status)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (post_id, reporter_user_id, "spam", _REPORT_STATUS_PENDING),
    )
    return cur.fetchone()[0]


def _row_exists(cur, table: str, row_id: str) -> bool:
    cur.execute(f"SELECT 1 FROM {table} WHERE id = %s", (row_id,))
    return cur.fetchone() is not None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPartialUniquePostPerJob:
    """Migration 0046 — partial UNIQUE(glow_up_job_id) WHERE live."""

    def test_second_live_post_for_same_job_raises_unique_violation(
        self, db_conn
    ) -> None:
        """A second live post for the same glow_up_job_id must 23505."""
        cur = db_conn.cursor()
        user_id = _insert_user(cur)
        job_id = _insert_job(cur, user_id)
        before_id = _insert_image(cur, user_id, _IMAGE_TYPE_BEFORE)
        after_id = _insert_image(cur, user_id, _IMAGE_TYPE_AFTER)

        # First live post — must succeed.
        _insert_post(
            cur,
            user_id=user_id,
            job_id=job_id,
            before_image_id=before_id,
            after_image_id=after_id,
        )

        # Second live post with the same glow_up_job_id — must raise.
        with pytest.raises(pg_errors.UniqueViolation) as exc_info:
            _insert_post(
                cur,
                user_id=user_id,
                job_id=job_id,
                before_image_id=before_id,
                after_image_id=after_id,
            )
        assert exc_info.value.pgcode == _UNIQUE_VIOLATION_SQLSTATE
        assert exc_info.value.diag.constraint_name == _PARTIAL_UNIQUE_INDEX_NAME, (
            "unique_violation must come from the partial index created by "
            "0046, not some other constraint"
        )

    def test_partial_index_permits_replace_after_soft_delete(self, db_conn) -> None:
        """Soft-deleting the first post must free the slot for a new one."""
        cur = db_conn.cursor()
        user_id = _insert_user(cur)
        job_id = _insert_job(cur, user_id)
        before_id = _insert_image(cur, user_id, _IMAGE_TYPE_BEFORE)
        after_id = _insert_image(cur, user_id, _IMAGE_TYPE_AFTER)

        # First live post.
        first_post_id = _insert_post(
            cur,
            user_id=user_id,
            job_id=job_id,
            before_image_id=before_id,
            after_image_id=after_id,
        )

        # Soft-delete it — exits the partial predicate.
        cur.execute(
            "UPDATE posts SET is_deleted = TRUE WHERE id = %s",
            (first_post_id,),
        )

        # Second live post for the same job — must succeed now.
        second_post_id = _insert_post(
            cur,
            user_id=user_id,
            job_id=job_id,
            before_image_id=before_id,
            after_image_id=after_id,
        )
        assert second_post_id != first_post_id


class TestJobCascadeWipesAllChildren:
    """End-to-end FK cascade: DELETE FROM jobs wipes posts and its children.

    Verified live rather than re-declared by 0046 so future schema drift
    (e.g. someone flipping a FK back to NO ACTION) is caught by this
    test, not by a customer discovering orphaned reactions.
    """

    def test_delete_job_cascades_to_post_and_all_children(self, db_conn) -> None:
        cur = db_conn.cursor()

        user_id = _insert_user(cur)
        job_id = _insert_job(cur, user_id)
        before_id = _insert_image(cur, user_id, _IMAGE_TYPE_BEFORE)
        after_id = _insert_image(cur, user_id, _IMAGE_TYPE_AFTER)

        post_id = _insert_post(
            cur,
            user_id=user_id,
            job_id=job_id,
            before_image_id=before_id,
            after_image_id=after_id,
        )
        reaction_id = _insert_reaction(cur, post_id=post_id, user_id=user_id)
        comment_id = _insert_comment(cur, post_id=post_id, user_id=user_id)
        report_id = _insert_report(cur, post_id=post_id, reporter_user_id=user_id)

        # Precondition: all five rows present.
        assert _row_exists(cur, "posts", post_id)
        assert _row_exists(cur, "reactions", reaction_id)
        assert _row_exists(cur, "comments", comment_id)
        assert _row_exists(cur, "reports", report_id)

        # Act — delete the job. Postgres must cascade posts, and posts
        # must cascade reactions/comments/reports.
        cur.execute("DELETE FROM jobs WHERE id = %s", (job_id,))

        # All four child rows must be gone.
        assert not _row_exists(cur, "posts", post_id), (
            "posts row survived — FK posts_glow_up_job_id_fkey is not CASCADE"
        )
        assert not _row_exists(cur, "reactions", reaction_id), (
            "reactions row survived — FK reactions_post_id_fkey is not CASCADE"
        )
        assert not _row_exists(cur, "comments", comment_id), (
            "comments row survived — FK comments_post_id_fkey is not CASCADE"
        )
        assert not _row_exists(cur, "reports", report_id), (
            "reports row survived — FK reports_post_id_fkey is not CASCADE"
        )
