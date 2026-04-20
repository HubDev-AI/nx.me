"""Live-DB tests for migration 0048 (payments Phase A schema additions).

Exercises the schema invariants introduced by `0048_payments_schema_phase_a.sql`:

  * seeded `plan_versions` rows are present with the expected numbers,
  * partial UNIQUE `idx_subscriptions_one_active_per_user` permits one
    active subscription + many cancelled rows for the same user but
    rejects a second active,
  * extended `credit_ledger.type` CHECK accepts the new entry types
    and rejects values outside the union,
  * `users.stripe_customer_id` UNIQUE rejects a duplicate across users.

Each test wraps its writes in a transaction that is rolled back at
teardown, so fixtures never leak across runs. Uses psycopg2 against the
local Supabase Postgres at ``127.0.0.1:54322`` because CHECK + partial
UNIQUE behavior is schema-level and cannot be proved with Python mocks.

Tests skip cleanly if the DB isn't reachable (CI without Supabase).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
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
# Constants — no magic strings.
# ---------------------------------------------------------------------------

_DEFAULT_LOCAL_DSN = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"

_UNIQUE_VIOLATION_SQLSTATE = "23505"
_CHECK_VIOLATION_SQLSTATE = "23514"

_VERSION_FREE = "v1_free_default"
_VERSION_PRO = "v1_pro"

# Plan numbers (plan line 117):
_EXPECTED_FREE = {
    "price_usd_cents": 0,
    "monthly_allotment_milli": 0,
    "glowup_cost_milli": 100,
    "ada_cost_milli": 5,
}
_EXPECTED_PRO = {
    "price_usd_cents": 999,
    "monthly_allotment_milli": 3000,
    "glowup_cost_milli": 100,
    "ada_cost_milli": 5,
}

_SUBSCRIPTION_STATUS_ACTIVE = "active"
_SUBSCRIPTION_STATUS_CANCELLED = "cancelled"
_SUBSCRIPTION_PROVIDER_STRIPE = "stripe"

_PARTIAL_UNIQUE_ACTIVE_SUB_INDEX = "idx_subscriptions_one_active_per_user"
_STRIPE_CUSTOMER_ID_UNIQUE_CONSTRAINT = "users_stripe_customer_id_key"

# Types introduced by 0048; guest_merge_* entries dropped by 0056.
_NEW_LEDGER_TYPES = (
    "signup_grant",
    "signup_grant_suppressed_by_fingerprint",
    "weekly_free_grant",
    "monthly_allotment",
    "credit_pack_purchase",
    "ada_message",
    "dispute_compensation",
)
# Explicitly excluded per the plan (single-entry REPLACE decision).
_REJECTED_LEDGER_TYPE = "retained_preserved"


# ---------------------------------------------------------------------------
# Fixtures.
# ---------------------------------------------------------------------------


def _get_dsn() -> str:
    """Resolve the DSN the same way the migration runner does."""
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
def db_conn() -> Iterator["_PgConnection"]:
    """Yield a transactional connection; roll back all writes at teardown."""
    conn = psycopg2.connect(_get_dsn())
    conn.autocommit = False
    try:
        yield conn
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


def _insert_user(cur, *, stripe_customer_id: str | None = None) -> str:
    """Insert a user; return id."""
    suffix = uuid.uuid4().hex[:12]
    cur.execute(
        """
        INSERT INTO users (
            username, display_name, email_verified, stripe_customer_id
        )
        VALUES (%s, %s, FALSE, %s)
        RETURNING id
        """,
        (f"planver_{suffix}", f"Plan Version {suffix}", stripe_customer_id),
    )
    return cur.fetchone()[0]


def _insert_subscription(
    cur,
    *,
    user_id: str,
    status: str,
    provider_subscription_id: str | None = None,
) -> str:
    """Insert a subscription row; return id.

    `provider_subscription_id` is UNIQUE NOT NULL; when the caller does
    not care we mint a fresh uuid so rows do not collide across helpers.
    `plan_version_id` is left NULL — existing columns are nullable and
    the invariants under test here don't depend on it.
    """
    provider_subscription_id = provider_subscription_id or str(uuid.uuid4())
    now = datetime.now(tz=timezone.utc)
    cur.execute(
        """
        INSERT INTO subscriptions (
            user_id, provider, provider_subscription_id, status,
            billing_period_start, billing_period_end
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            user_id,
            _SUBSCRIPTION_PROVIDER_STRIPE,
            provider_subscription_id,
            status,
            now,
            now + timedelta(days=30),
        ),
    )
    return cur.fetchone()[0]


def _insert_credit_ledger(cur, *, user_id: str, delta: int, entry_type: str) -> str:
    """Insert a credit_ledger row; return id."""
    cur.execute(
        """
        INSERT INTO credit_ledger (user_id, delta, type)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (user_id, delta, entry_type),
    )
    return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Tests.
# ---------------------------------------------------------------------------


class TestPlanVersionsSeeded:
    """Happy path — migration 0048 leaves the two seeded rows in place."""

    def test_free_default_row_has_expected_numbers(self, db_conn) -> None:
        cur = db_conn.cursor()
        cur.execute(
            """
            SELECT price_usd_cents, monthly_allotment_milli,
                   glowup_cost_milli, ada_cost_milli
              FROM plan_versions
             WHERE version_num = %s
            """,
            (_VERSION_FREE,),
        )
        row = cur.fetchone()
        assert row is not None, f"{_VERSION_FREE} seed row missing — 0048 did not apply"
        price, monthly, glowup, ada = row
        assert price == _EXPECTED_FREE["price_usd_cents"]
        assert monthly == _EXPECTED_FREE["monthly_allotment_milli"]
        assert glowup == _EXPECTED_FREE["glowup_cost_milli"]
        assert ada == _EXPECTED_FREE["ada_cost_milli"]

    def test_pro_row_has_expected_numbers(self, db_conn) -> None:
        cur = db_conn.cursor()
        cur.execute(
            """
            SELECT price_usd_cents, monthly_allotment_milli,
                   glowup_cost_milli, ada_cost_milli
              FROM plan_versions
             WHERE version_num = %s
            """,
            (_VERSION_PRO,),
        )
        row = cur.fetchone()
        assert row is not None, f"{_VERSION_PRO} seed row missing — 0048 did not apply"
        price, monthly, glowup, ada = row
        assert price == _EXPECTED_PRO["price_usd_cents"]
        assert monthly == _EXPECTED_PRO["monthly_allotment_milli"]
        assert glowup == _EXPECTED_PRO["glowup_cost_milli"]
        assert ada == _EXPECTED_PRO["ada_cost_milli"]

    def test_version_num_is_unique(self, db_conn) -> None:
        """Second row with the same version_num must 23505."""
        cur = db_conn.cursor()
        with pytest.raises(pg_errors.UniqueViolation) as exc_info:
            cur.execute(
                """
                INSERT INTO plan_versions (
                    version_num, glowup_cost_milli, ada_cost_milli
                ) VALUES (%s, 100, 5)
                """,
                (_VERSION_PRO,),
            )
        assert exc_info.value.pgcode == _UNIQUE_VIOLATION_SQLSTATE


class TestOneActiveSubscriptionPerUser:
    """Partial UNIQUE `idx_subscriptions_one_active_per_user` (R8)."""

    def test_one_active_plus_many_cancelled_is_allowed(self, db_conn) -> None:
        """The predicate filters on status='active'; cancelled rows don't
        count toward the uniqueness check."""
        cur = db_conn.cursor()
        user_id = _insert_user(cur)

        _insert_subscription(cur, user_id=user_id, status=_SUBSCRIPTION_STATUS_ACTIVE)
        for _ in range(5):
            _insert_subscription(
                cur, user_id=user_id, status=_SUBSCRIPTION_STATUS_CANCELLED
            )

        cur.execute(
            "SELECT status, COUNT(*) FROM subscriptions "
            "WHERE user_id = %s GROUP BY status ORDER BY status",
            (user_id,),
        )
        counts = dict(cur.fetchall())
        assert counts == {
            _SUBSCRIPTION_STATUS_ACTIVE: 1,
            _SUBSCRIPTION_STATUS_CANCELLED: 5,
        }

    def test_second_active_for_same_user_raises_unique_violation(self, db_conn) -> None:
        """Second active subscription for the same user must 23505 via
        the partial index created by 0048."""
        cur = db_conn.cursor()
        user_id = _insert_user(cur)

        _insert_subscription(cur, user_id=user_id, status=_SUBSCRIPTION_STATUS_ACTIVE)

        with pytest.raises(pg_errors.UniqueViolation) as exc_info:
            _insert_subscription(
                cur, user_id=user_id, status=_SUBSCRIPTION_STATUS_ACTIVE
            )
        assert exc_info.value.pgcode == _UNIQUE_VIOLATION_SQLSTATE
        assert (
            exc_info.value.diag.constraint_name == _PARTIAL_UNIQUE_ACTIVE_SUB_INDEX
        ), (
            "unique_violation must originate from the partial index 0048 "
            "creates, not some other constraint"
        )

    def test_two_users_can_each_have_one_active(self, db_conn) -> None:
        """The partial index is scoped per-user; two users may both be active."""
        cur = db_conn.cursor()
        user_a = _insert_user(cur)
        user_b = _insert_user(cur)

        _insert_subscription(cur, user_id=user_a, status=_SUBSCRIPTION_STATUS_ACTIVE)
        _insert_subscription(cur, user_id=user_b, status=_SUBSCRIPTION_STATUS_ACTIVE)

        cur.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE status = %s "
            "AND user_id IN (%s, %s)",
            (_SUBSCRIPTION_STATUS_ACTIVE, user_a, user_b),
        )
        assert cur.fetchone()[0] == 2


class TestCreditLedgerTypeCheck:
    """Extended `credit_ledger.type` CHECK constraint accepts the v2 enum
    but still rejects values outside the union."""

    @pytest.mark.parametrize("entry_type", _NEW_LEDGER_TYPES)
    def test_new_type_is_accepted(self, db_conn, entry_type: str) -> None:
        cur = db_conn.cursor()
        user_id = _insert_user(cur)
        row_id = _insert_credit_ledger(
            cur, user_id=user_id, delta=0, entry_type=entry_type
        )
        assert row_id is not None

    def test_retained_preserved_is_rejected(self, db_conn) -> None:
        """Plan line 115: `retained_preserved` removed; single net-delta
        REPLACE uses `metadata.discarded_milli` instead."""
        cur = db_conn.cursor()
        user_id = _insert_user(cur)
        with pytest.raises(pg_errors.CheckViolation) as exc_info:
            _insert_credit_ledger(
                cur,
                user_id=user_id,
                delta=0,
                entry_type=_REJECTED_LEDGER_TYPE,
            )
        assert exc_info.value.pgcode == _CHECK_VIOLATION_SQLSTATE

    def test_unknown_type_is_rejected(self, db_conn) -> None:
        cur = db_conn.cursor()
        user_id = _insert_user(cur)
        with pytest.raises(pg_errors.CheckViolation) as exc_info:
            _insert_credit_ledger(
                cur,
                user_id=user_id,
                delta=0,
                entry_type="definitely_not_a_real_ledger_type",
            )
        assert exc_info.value.pgcode == _CHECK_VIOLATION_SQLSTATE

    def test_preserved_baseline_type_still_accepted(self, db_conn) -> None:
        """Regression guard: DROP/ADD of the CHECK constraint must keep
        the original 0001 baseline entries callable."""
        cur = db_conn.cursor()
        user_id = _insert_user(cur)
        row_id = _insert_credit_ledger(
            cur, user_id=user_id, delta=0, entry_type="reserve"
        )
        assert row_id is not None


class TestStripeCustomerIdUnique:
    """`users.stripe_customer_id` is UNIQUE — two users cannot claim the
    same Stripe customer."""

    def test_duplicate_stripe_customer_id_across_users_rejected(self, db_conn) -> None:
        cur = db_conn.cursor()
        customer_id = f"cus_{uuid.uuid4().hex[:24]}"

        _insert_user(cur, stripe_customer_id=customer_id)

        with pytest.raises(pg_errors.UniqueViolation) as exc_info:
            _insert_user(cur, stripe_customer_id=customer_id)
        assert exc_info.value.pgcode == _UNIQUE_VIOLATION_SQLSTATE
        assert (
            exc_info.value.diag.constraint_name == _STRIPE_CUSTOMER_ID_UNIQUE_CONSTRAINT
        )

    def test_null_stripe_customer_id_does_not_collide(self, db_conn) -> None:
        """UNIQUE in Postgres treats NULLs as distinct; many users may have
        a NULL column before the backfill script runs."""
        cur = db_conn.cursor()
        user_a = _insert_user(cur, stripe_customer_id=None)
        user_b = _insert_user(cur, stripe_customer_id=None)
        assert user_a != user_b
