"""Unit tests for :func:`app.utils.db_errors.is_unique_violation`.

This helper consolidates the three historically duplicated detections of
PostgreSQL SQLSTATE ``23505`` (``unique_violation``) that previously lived in
``app/api/posts.py``, ``app/advisor/memory_manager.py``, and
``app/entitlement/trial_grantor.py``. Each call site was slightly different —
one only checked ``.code``, one also string-matched ``"unique_violation"``,
one only string-matched ``"unique" + ("violat" | "duplicat")``.

This suite pins the union behaviour so future drift between Supabase /
PostgREST / psycopg2 / psycopg3 client wrapper versions is caught by a fast
unit test instead of a silent regression at one of the three call sites.

Scenarios covered:

1. Supabase ``APIError``-style object: ``code = "23505"`` → True.
2. psycopg2 ``IntegrityError`` stand-in: ``pgcode = "23505"`` → True.
3. Wrapper drops both attributes but keeps the SQLSTATE in the message →
   True.
4. "unique_violation" phrase in message (no code/pgcode) → True.
5. "duplicate key value violates unique constraint …" in message → True.
6. ``code = "23503"`` (foreign_key_violation) → False.
7. Arbitrary ``RuntimeError`` with unrelated message → False.
"""

from __future__ import annotations

import pytest

from app.utils.db_errors import is_unique_violation


# ---------------------------------------------------------------------------
# Exception shape doubles — mirror the three client libraries we call.
# ---------------------------------------------------------------------------


class _FakeSupabaseAPIError(Exception):
    """Stand-in for ``postgrest.exceptions.APIError``.

    The real class exposes ``code`` with the Postgres SQLSTATE.  We import
    no PostgREST modules here because those move between client versions
    (precisely why the production helper is string-based).
    """

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class _FakePsycopgIntegrityError(Exception):
    """Stand-in for ``psycopg2.errors.IntegrityError`` / psycopg3 equivalent.

    These surface the SQLSTATE as ``pgcode``, not ``code``. The production
    helper must check both attribute names.
    """

    def __init__(self, message: str, pgcode: str | None = None) -> None:
        super().__init__(message)
        self.pgcode = pgcode


# ---------------------------------------------------------------------------
# Positive cases — every currently-seen unique_violation surface.
# ---------------------------------------------------------------------------


def test_supabase_api_error_code_23505_is_unique_violation() -> None:
    exc = _FakeSupabaseAPIError(
        'duplicate key value violates unique constraint "idx_posts_live_glow_up_job_id"',
        code="23505",
    )
    assert is_unique_violation(exc) is True


def test_psycopg_integrity_error_pgcode_23505_is_unique_violation() -> None:
    """psycopg2/psycopg3 ``IntegrityError.pgcode``.

    None of the three original sites handled this; the task called it out
    explicitly because a raw ``psycopg2.connect`` path (e.g.
    ``tests/test_delete_glowup_cascade.py::TestDeleteGlowupLiveDB``) would
    otherwise slip through as a False return.
    """
    exc = _FakePsycopgIntegrityError(
        'duplicate key value violates unique constraint "users_email_key"',
        pgcode="23505",
    )
    assert is_unique_violation(exc) is True


def test_message_contains_sqlstate_number() -> None:
    """Wrapper stripped both attributes but left '23505' in the message."""

    class _Bare(Exception):
        pass

    exc = _Bare("PostgrestError: 23505 unique_violation")
    assert is_unique_violation(exc) is True


def test_message_contains_unique_violation_phrase() -> None:
    class _Bare(Exception):
        pass

    exc = _Bare("something went wrong: unique_violation on advisor_memories")
    assert is_unique_violation(exc) is True


def test_message_contains_duplicate_key_phrase() -> None:
    """Match on 'duplicate key ... unique constraint' without the code."""

    class _Bare(Exception):
        pass

    exc = _Bare(
        'duplicate key value violates unique constraint "idx_posts_live_glow_up_job_id"'
    )
    assert is_unique_violation(exc) is True


def test_message_contains_unique_and_violat_tokens() -> None:
    """Less common wording kept for parity with the historic memory_manager
    implementation — 'unique … violat' anywhere in the message."""

    class _Bare(Exception):
        pass

    exc = _Bare("error: unique constraint violation on reservations")
    assert is_unique_violation(exc) is True


# ---------------------------------------------------------------------------
# Negative cases — other PG errors and unrelated exceptions must be False.
# ---------------------------------------------------------------------------


def test_foreign_key_violation_is_not_unique_violation() -> None:
    """SQLSTATE 23503 is foreign_key_violation — must NOT match."""
    exc = _FakeSupabaseAPIError(
        'insert or update on table "posts" violates foreign key constraint',
        code="23503",
    )
    assert is_unique_violation(exc) is False


def test_check_violation_23514_is_not_unique_violation() -> None:
    """SQLSTATE 23514 is check_violation — must NOT match. Defends
    against a future regression widening the code check to ``startswith("235")``.
    """
    exc = _FakePsycopgIntegrityError(
        'new row for relation "users" violates check constraint',
        pgcode="23514",
    )
    assert is_unique_violation(exc) is False


def test_arbitrary_runtime_error_is_not_unique_violation() -> None:
    exc = RuntimeError("database connection refused")
    assert is_unique_violation(exc) is False


def test_empty_exception_is_not_unique_violation() -> None:
    """Guard against an attributeless Exception triggering a false positive."""

    class _Bare(Exception):
        pass

    exc = _Bare()
    assert is_unique_violation(exc) is False


# ---------------------------------------------------------------------------
# Parametrised aggregate — easier to scan than individual cases.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc,expected",
    [
        (_FakeSupabaseAPIError("x", code="23505"), True),
        (_FakePsycopgIntegrityError("x", pgcode="23505"), True),
        (
            _FakeSupabaseAPIError("duplicate key value violates unique constraint"),
            True,
        ),  # message-only — full PG wording
        (_FakeSupabaseAPIError("23505 unique_violation"), True),
        (_FakeSupabaseAPIError("x", code="23503"), False),
        (_FakePsycopgIntegrityError("x", pgcode="23502"), False),
        (RuntimeError("timeout"), False),
    ],
)
def test_matrix_of_exception_shapes(exc: Exception, expected: bool) -> None:
    assert is_unique_violation(exc) is expected
