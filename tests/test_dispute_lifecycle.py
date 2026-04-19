"""Live-DB tests for migration 0051 — dispute state machine CAS RPC.

Exercises the `apply_dispute_event(p_user_id, p_event_id, p_event_at,
p_new_status)` RPC introduced in 0051 plus its interaction with:

  - `credit_reserve` (migration 0049, Unit 2): must reject
    `AccountLocked` when `users.locked_at IS NOT NULL`.
  - `credit_dispute_compensate` (migration 0050, Unit 3): caller-side
    compensating ledger write on `closed_lost`.

Uses psycopg2 against the local Supabase Postgres at ``127.0.0.1:54322``
because the RPC's CAS semantics and advisory-lock domain are schema-level
and cannot be proved with Python mocks.

Each test wraps its writes in a single transaction that is rolled back at
teardown so fixtures never leak across runs. The migrations themselves
(0048–0051) stay applied between runs — that's the runner contract.

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
    from psycopg2.extensions import connection as _PgConnection

    _PSYCOPG_AVAILABLE = True
except ImportError:
    _PSYCOPG_AVAILABLE = False


# ---------------------------------------------------------------------------
# Constants — no magic strings
# ---------------------------------------------------------------------------

_DEFAULT_LOCAL_DSN = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"

# Dispute statuses — must stay in lockstep with 0051 CHECK.
_STATUS_CREATED = "created"
_STATUS_CLOSED_WON = "closed_won"
_STATUS_CLOSED_LOST = "closed_lost"
_STATUS_FUNDS_WITHDRAWN = "funds_withdrawn"

# Reserve action types — must stay in lockstep with 0049.
_ACTION_GLOWUP = "glowup"

# Plan-version seed UUIDs (migration 0048 seeds two rows).
_PLAN_VERSION_V1_PRO_GLOWUP_COST_MILLI = 100
_PLAN_VERSION_V1_PRO_MONTHLY_ALLOTMENT_MILLI = 3000

# Ledger types — must stay in lockstep with the extended CHECK in 0048.
_LEDGER_TYPE_DISPUTE_COMPENSATION = "dispute_compensation"
_LEDGER_TYPE_PURCHASE = "purchase"

# SQLSTATE for `apply_dispute_event` invalid-status RAISE.
_INVALID_DISPUTE_STATUS_SQLSTATE = "P0001"

# SQLSTATE for `credit_reserve` account-locked RAISE (per Unit 2 spec).
_ACCOUNT_LOCKED_SQLSTATE = "P0001"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


def _rpc_available(rpc_name: str) -> bool:
    """True iff the given RPC is already loaded in the target DB.

    Unit 4 lands the CAS RPC; Units 2/3 land the credit RPCs used by
    the integration tests. When Unit 4 is tested in isolation (Units 2/3
    not yet merged), the dependent tests skip instead of failing.
    """
    if not _PSYCOPG_AVAILABLE:
        return False
    try:
        conn = psycopg2.connect(_get_dsn(), connect_timeout=2)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1
                      FROM pg_proc p
                      JOIN pg_namespace n ON n.oid = p.pronamespace
                     WHERE n.nspname = 'public'
                       AND p.proname = %s
                     LIMIT 1
                    """,
                    (rpc_name,),
                )
                return cur.fetchone() is not None
        finally:
            conn.close()
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
    pytest.mark.skipif(
        not _rpc_available("apply_dispute_event"),
        reason="migration 0051 not applied — `apply_dispute_event` RPC missing",
    ),
]

_requires_reserve = pytest.mark.skipif(
    not _rpc_available("credit_reserve"),
    reason="migration 0049 not applied — `credit_reserve` (action-typed) RPC missing",
)

_requires_dispute_compensate = pytest.mark.skipif(
    not _rpc_available("credit_dispute_compensate"),
    reason="migration 0050 not applied — `credit_dispute_compensate` RPC missing",
)


@pytest.fixture
def db_conn() -> Iterator[_PgConnection]:
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
# Helpers — minimum-shape row inserts.
# ---------------------------------------------------------------------------


def _insert_user(cur) -> str:
    """Insert a user on the default tier; return id.

    Matches `_insert_user` from `test_posts_unique_constraint.py` — resolves
    the default tier from the tiers table so this test never hardcodes it.
    """
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


def _grant_credits(
    cur, user_id: str, amount_milli: int, ledger_type: str = _LEDGER_TYPE_PURCHASE
) -> None:
    """Credit the user directly via a ledger row.

    Bypasses the v2 grant RPCs so this test stays self-contained: the
    point here is the dispute state machine, not grant semantics.
    """
    cur.execute(
        """
        INSERT INTO credit_ledger (user_id, delta, type, reference_id)
        VALUES (%s, %s, %s, %s)
        """,
        (user_id, amount_milli, ledger_type, str(uuid.uuid4())),
    )


def _call_apply_dispute_event(
    cur,
    *,
    user_id: str,
    event_id: str,
    event_at: datetime,
    new_status: str,
) -> dict:
    """Invoke the CAS RPC; return the jsonb result as a Python dict."""
    cur.execute(
        """
        SELECT apply_dispute_event(
            %s::uuid, %s::text, %s::timestamptz, %s::text
        )
        """,
        (user_id, event_id, event_at, new_status),
    )
    return cur.fetchone()[0]


def _read_user(cur, user_id: str) -> dict:
    cur.execute(
        """
        SELECT locked_at, dispute_last_event_id, dispute_last_event_at,
               dispute_last_status
          FROM users
         WHERE id = %s
        """,
        (user_id,),
    )
    row = cur.fetchone()
    return {
        "locked_at": row[0],
        "dispute_last_event_id": row[1],
        "dispute_last_event_at": row[2],
        "dispute_last_status": row[3],
    }


def _balance(cur, user_id: str) -> int:
    cur.execute(
        "SELECT COALESCE(SUM(delta), 0)::int FROM credit_ledger WHERE user_id = %s",
        (user_id,),
    )
    return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Tests — invalid input
# ---------------------------------------------------------------------------


class TestApplyDisputeEventValidation:
    """Input validation — invalid `p_new_status` values must raise."""

    def test_invalid_status_raises(self, db_conn) -> None:
        cur = db_conn.cursor()
        user_id = _insert_user(cur)
        now = datetime.now(tz=timezone.utc)

        with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
            _call_apply_dispute_event(
                cur,
                user_id=user_id,
                event_id="evt_bogus",
                event_at=now,
                new_status="refunded",  # not in the enum
            )
        assert exc_info.value.pgcode == _INVALID_DISPUTE_STATUS_SQLSTATE
        assert "invalid_dispute_status" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Tests — happy path
# ---------------------------------------------------------------------------


class TestApplyDisputeEventHappyPath:
    """In-order events: created → locks, closed_won → unlocks, funds_withdrawn → audit-only."""

    def test_created_sets_locked_at(self, db_conn) -> None:
        cur = db_conn.cursor()
        user_id = _insert_user(cur)
        t1 = datetime.now(tz=timezone.utc) - timedelta(minutes=10)

        result = _call_apply_dispute_event(
            cur,
            user_id=user_id,
            event_id="evt_1",
            event_at=t1,
            new_status=_STATUS_CREATED,
        )

        assert result["applied"] is True
        assert result["new_status"] == _STATUS_CREATED
        assert result["locked_at"] is not None

        row = _read_user(cur, user_id)
        assert row["locked_at"] is not None
        assert row["dispute_last_event_id"] == "evt_1"
        assert row["dispute_last_status"] == _STATUS_CREATED

    def test_created_then_closed_won_clears_lock(self, db_conn) -> None:
        cur = db_conn.cursor()
        user_id = _insert_user(cur)
        t1 = datetime.now(tz=timezone.utc) - timedelta(minutes=10)
        t2 = t1 + timedelta(minutes=5)

        _call_apply_dispute_event(
            cur,
            user_id=user_id,
            event_id="evt_1",
            event_at=t1,
            new_status=_STATUS_CREATED,
        )
        result = _call_apply_dispute_event(
            cur,
            user_id=user_id,
            event_id="evt_2",
            event_at=t2,
            new_status=_STATUS_CLOSED_WON,
        )

        assert result["applied"] is True
        assert result["new_status"] == _STATUS_CLOSED_WON
        assert result["locked_at"] is None

        row = _read_user(cur, user_id)
        assert row["locked_at"] is None
        assert row["dispute_last_event_id"] == "evt_2"
        assert row["dispute_last_status"] == _STATUS_CLOSED_WON

    def test_funds_withdrawn_is_audit_only(self, db_conn) -> None:
        """`funds_withdrawn` advances the CAS tuple but leaves locked_at unchanged."""
        cur = db_conn.cursor()
        user_id = _insert_user(cur)
        t1 = datetime.now(tz=timezone.utc) - timedelta(minutes=10)
        t2 = t1 + timedelta(minutes=1)
        t3 = t1 + timedelta(minutes=2)

        _call_apply_dispute_event(
            cur,
            user_id=user_id,
            event_id="evt_c",
            event_at=t1,
            new_status=_STATUS_CREATED,
        )
        _call_apply_dispute_event(
            cur,
            user_id=user_id,
            event_id="evt_l",
            event_at=t2,
            new_status=_STATUS_CLOSED_LOST,
        )
        row_before = _read_user(cur, user_id)

        result = _call_apply_dispute_event(
            cur,
            user_id=user_id,
            event_id="evt_w",
            event_at=t3,
            new_status=_STATUS_FUNDS_WITHDRAWN,
        )

        assert result["applied"] is True
        assert result["new_status"] == _STATUS_FUNDS_WITHDRAWN

        row_after = _read_user(cur, user_id)
        # locked_at preserved from the closed_lost transition.
        assert row_after["locked_at"] == row_before["locked_at"]
        assert row_after["locked_at"] is not None
        # CAS tuple advanced.
        assert row_after["dispute_last_event_id"] == "evt_w"
        assert row_after["dispute_last_status"] == _STATUS_FUNDS_WITHDRAWN


# ---------------------------------------------------------------------------
# Tests — idempotency
# ---------------------------------------------------------------------------


class TestApplyDisputeEventIdempotency:
    """Same event_id delivered twice must be a no-op the second time."""

    def test_duplicate_event_id_is_noop(self, db_conn) -> None:
        cur = db_conn.cursor()
        user_id = _insert_user(cur)
        t1 = datetime.now(tz=timezone.utc) - timedelta(minutes=10)

        first = _call_apply_dispute_event(
            cur,
            user_id=user_id,
            event_id="evt_dup",
            event_at=t1,
            new_status=_STATUS_CREATED,
        )
        assert first["applied"] is True

        first_locked_at = _read_user(cur, user_id)["locked_at"]

        # Redeliver same event_id — even with a later event_at, duplicate
        # detection wins over the CAS comparison.
        second = _call_apply_dispute_event(
            cur,
            user_id=user_id,
            event_id="evt_dup",
            event_at=t1 + timedelta(minutes=5),
            new_status=_STATUS_CREATED,
        )

        assert second["applied"] is False
        assert second["reason"] == "duplicate"

        # State unchanged.
        row = _read_user(cur, user_id)
        assert row["locked_at"] == first_locked_at
        assert row["dispute_last_event_id"] == "evt_dup"


# ---------------------------------------------------------------------------
# Tests — out-of-order (CAS)
# ---------------------------------------------------------------------------


class TestApplyDisputeEventOutOfOrder:
    """Out-of-order `charge.dispute.*` webhooks must be rejected via CAS."""

    def test_closed_won_first_then_late_created_rejected(self, db_conn) -> None:
        """The classic Stripe reordering: closed_won (t=10) arrives before
        created (t=5). Final state must be closed_won + locked_at NULL."""
        cur = db_conn.cursor()
        user_id = _insert_user(cur)
        t_early = datetime.now(tz=timezone.utc) - timedelta(minutes=10)
        t_late = t_early + timedelta(minutes=5)

        # closed_won arrives first.
        first = _call_apply_dispute_event(
            cur,
            user_id=user_id,
            event_id="evt_won",
            event_at=t_late,
            new_status=_STATUS_CLOSED_WON,
        )
        assert first["applied"] is True

        # Late `created` with older event_at — must be rejected.
        second = _call_apply_dispute_event(
            cur,
            user_id=user_id,
            event_id="evt_created",
            event_at=t_early,
            new_status=_STATUS_CREATED,
        )
        assert second["applied"] is False
        assert second["reason"] == "out_of_order"

        # Final state: closed_won, locked_at NULL.
        row = _read_user(cur, user_id)
        assert row["locked_at"] is None
        assert row["dispute_last_event_id"] == "evt_won"
        assert row["dispute_last_status"] == _STATUS_CLOSED_WON

    def test_closed_lost_first_then_late_created_rejected_user_stays_locked(
        self, db_conn
    ) -> None:
        """closed_lost (t=5) arrives before created (t=0). Final state must
        be closed_lost + locked_at set — lost-dominates semantics."""
        cur = db_conn.cursor()
        user_id = _insert_user(cur)
        t0 = datetime.now(tz=timezone.utc) - timedelta(minutes=10)
        t1 = t0 + timedelta(minutes=5)

        # closed_lost arrives first — no prior `created`, so the RPC
        # must set locked_at itself (lost-dominates invariant).
        first = _call_apply_dispute_event(
            cur,
            user_id=user_id,
            event_id="evt_lost",
            event_at=t1,
            new_status=_STATUS_CLOSED_LOST,
        )
        assert first["applied"] is True
        assert first["locked_at"] is not None

        # Late `created` with older event_at — must be rejected.
        second = _call_apply_dispute_event(
            cur,
            user_id=user_id,
            event_id="evt_created",
            event_at=t0,
            new_status=_STATUS_CREATED,
        )
        assert second["applied"] is False
        assert second["reason"] == "out_of_order"

        # Final state: closed_lost, locked_at still set.
        row = _read_user(cur, user_id)
        assert row["locked_at"] is not None
        assert row["dispute_last_event_id"] == "evt_lost"
        assert row["dispute_last_status"] == _STATUS_CLOSED_LOST

    def test_tied_timestamps_different_event_ids_cas_accepts_second(
        self, db_conn
    ) -> None:
        """Two events with IDENTICAL event_at (same microsecond, different
        event_ids). The CAS uses strict `>` so that tied timestamps on
        distinct events are accepted as last-write-wins — the
        duplicate-event_id branch already handles Stripe redeliveries, so
        this branch only fires for truly distinct events. Stripe can emit
        `created` + `closed_won` at the same millisecond in rare cases;
        accepting both is safe because closed transitions are idempotent
        semantically.
        """
        cur = db_conn.cursor()
        user_id = _insert_user(cur)
        # Stripe `created` timestamps are second-resolution, but Postgres
        # stores microseconds. Use a microsecond-zero timestamp to simulate
        # the real Stripe tie case.
        t_tied = (datetime.now(tz=timezone.utc) - timedelta(minutes=5)).replace(
            microsecond=0
        )

        first = _call_apply_dispute_event(
            cur,
            user_id=user_id,
            event_id="evt_a",
            event_at=t_tied,
            new_status=_STATUS_CREATED,
        )
        assert first["applied"] is True

        second = _call_apply_dispute_event(
            cur,
            user_id=user_id,
            event_id="evt_b",
            event_at=t_tied,
            new_status=_STATUS_CLOSED_WON,
        )
        assert second["applied"] is True

        # Terminal state pinned to the second arrival (last-write-wins on
        # tied timestamps with distinct event_ids).
        row = _read_user(cur, user_id)
        assert row["dispute_last_event_id"] == "evt_b"
        assert row["dispute_last_status"] == _STATUS_CLOSED_WON
        assert row["locked_at"] is None


# ---------------------------------------------------------------------------
# Tests — integration with credit_reserve (Unit 2)
# ---------------------------------------------------------------------------


@_requires_reserve
class TestDisputeLockRejectsReserve:
    """A user locked by `apply_dispute_event('created', ...)` must have
    `credit_reserve` reject with AccountLocked (SQLSTATE P0002)."""

    def test_reserve_rejects_when_locked(self, db_conn) -> None:
        cur = db_conn.cursor()
        user_id = _insert_user(cur)
        _grant_credits(cur, user_id, _PLAN_VERSION_V1_PRO_MONTHLY_ALLOTMENT_MILLI)
        t1 = datetime.now(tz=timezone.utc) - timedelta(minutes=10)

        # Lock the user.
        _call_apply_dispute_event(
            cur,
            user_id=user_id,
            event_id="evt_c",
            event_at=t1,
            new_status=_STATUS_CREATED,
        )
        assert _read_user(cur, user_id)["locked_at"] is not None

        reservation_id = str(uuid.uuid4())
        with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
            cur.execute(
                """
                SELECT credit_reserve(
                    %s::uuid, %s::uuid, %s::text
                )
                """,
                (user_id, reservation_id, _ACTION_GLOWUP),
            )
        assert exc_info.value.pgcode == _ACCOUNT_LOCKED_SQLSTATE

    def test_reserve_resumes_after_closed_won(self, db_conn) -> None:
        """Full in-order lifecycle: reserve blocked while locked, then
        `closed_won` clears `locked_at`, then `credit_reserve` succeeds."""
        cur = db_conn.cursor()
        user_id = _insert_user(cur)
        _grant_credits(cur, user_id, _PLAN_VERSION_V1_PRO_MONTHLY_ALLOTMENT_MILLI)
        t1 = datetime.now(tz=timezone.utc) - timedelta(minutes=10)
        t2 = t1 + timedelta(minutes=5)

        # Lock.
        _call_apply_dispute_event(
            cur,
            user_id=user_id,
            event_id="evt_c",
            event_at=t1,
            new_status=_STATUS_CREATED,
        )

        # Unlock.
        result = _call_apply_dispute_event(
            cur,
            user_id=user_id,
            event_id="evt_w",
            event_at=t2,
            new_status=_STATUS_CLOSED_WON,
        )
        assert result["applied"] is True
        assert _read_user(cur, user_id)["locked_at"] is None

        # Now reserve must succeed.
        reservation_id = str(uuid.uuid4())
        cur.execute(
            """
            SELECT credit_reserve(
                %s::uuid, %s::uuid, %s::text
            )
            """,
            (user_id, reservation_id, _ACTION_GLOWUP),
        )
        # No exception => reserve succeeded.
        balance_after = _balance(cur, user_id)
        assert balance_after == (
            _PLAN_VERSION_V1_PRO_MONTHLY_ALLOTMENT_MILLI
            - _PLAN_VERSION_V1_PRO_GLOWUP_COST_MILLI
        )


# ---------------------------------------------------------------------------
# Tests — integration with credit_dispute_compensate (Unit 3)
# ---------------------------------------------------------------------------


@_requires_reserve
@_requires_dispute_compensate
class TestClosedLostWithCompensatingLedger:
    """Full closed_lost path: apply_dispute_event stays locked, caller
    writes compensating ledger via credit_dispute_compensate → balance
    goes negative, user still locked."""

    def test_closed_lost_leaves_locked_and_compensating_entry(self, db_conn) -> None:
        cur = db_conn.cursor()
        user_id = _insert_user(cur)

        # Seed: user paid for a pack (+1000 milli) via a simulated
        # `charge.succeeded` ledger entry. The compensating RPC will look
        # this up by its reference_id (simulated charge_id).
        charge_id = f"ch_{uuid.uuid4().hex[:16]}"
        pack_amount_milli = 1000
        cur.execute(
            """
            INSERT INTO credit_ledger (user_id, delta, type, reference_id, note)
            VALUES (%s, %s, 'credit_pack_purchase', gen_random_uuid(), %s)
            """,
            (user_id, pack_amount_milli, charge_id),
        )

        t1 = datetime.now(tz=timezone.utc) - timedelta(minutes=10)
        t2 = t1 + timedelta(minutes=5)

        # created → lock.
        _call_apply_dispute_event(
            cur,
            user_id=user_id,
            event_id="evt_c",
            event_at=t1,
            new_status=_STATUS_CREATED,
        )

        # closed_lost → stay locked.
        result = _call_apply_dispute_event(
            cur,
            user_id=user_id,
            event_id="evt_l",
            event_at=t2,
            new_status=_STATUS_CLOSED_LOST,
        )
        assert result["applied"] is True
        assert result["locked_at"] is not None

        # Caller writes compensating ledger.
        cur.execute(
            "SELECT credit_dispute_compensate(%s::uuid, %s::text, %s::int)",
            (user_id, charge_id, pack_amount_milli),
        )

        # Compensating entry visible, negative balance acceptable per R-Dispute-3.
        cur.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(delta), 0)::int
              FROM credit_ledger
             WHERE user_id = %s AND type = %s
            """,
            (user_id, _LEDGER_TYPE_DISPUTE_COMPENSATION),
        )
        count, sum_delta = cur.fetchone()
        assert count == 1, "exactly one compensating entry"
        assert sum_delta < 0, "compensating delta must be negative"
        assert sum_delta == -pack_amount_milli, (
            "compensating delta must exactly offset the original purchase"
        )

        # User still locked.
        row = _read_user(cur, user_id)
        assert row["locked_at"] is not None
        assert row["dispute_last_status"] == _STATUS_CLOSED_LOST


# ---------------------------------------------------------------------------
# Tests — integration: full dispute lifecycle, in order
# ---------------------------------------------------------------------------


@_requires_reserve
class TestFullLifecycle:
    """End-to-end created → closed_won flow: user regains reserve access."""

    def test_created_then_closed_won_user_regains_access(self, db_conn) -> None:
        """End-to-end in-order lifecycle: created locks, reserve is blocked
        while locked (asserted via SAVEPOINT so the outer tx survives the
        RAISE), closed_won unlocks, reserve succeeds.
        """
        cur = db_conn.cursor()
        user_id = _insert_user(cur)
        _grant_credits(cur, user_id, _PLAN_VERSION_V1_PRO_MONTHLY_ALLOTMENT_MILLI)
        t1 = datetime.now(tz=timezone.utc) - timedelta(minutes=10)
        t2 = t1 + timedelta(minutes=5)

        # 1. created → lock.
        _call_apply_dispute_event(
            cur,
            user_id=user_id,
            event_id="evt_c",
            event_at=t1,
            new_status=_STATUS_CREATED,
        )

        # 2. reserve must fail with AccountLocked while locked. Wrap in a
        #    SAVEPOINT so the outer transaction survives the RAISE and the
        #    subsequent `closed_won` / reserve calls still execute in the
        #    same tx (otherwise the `user_id` row vanishes).
        cur.execute("SAVEPOINT sp_blocked_reserve")
        try:
            with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
                cur.execute(
                    """
                    SELECT credit_reserve(
                        %s::uuid, %s::uuid, %s::text
                    )
                    """,
                    (user_id, str(uuid.uuid4()), _ACTION_GLOWUP),
                )
            assert exc_info.value.pgcode == _ACCOUNT_LOCKED_SQLSTATE
        finally:
            cur.execute("ROLLBACK TO SAVEPOINT sp_blocked_reserve")
            cur.execute("RELEASE SAVEPOINT sp_blocked_reserve")

        # 3. closed_won → unlock.
        _call_apply_dispute_event(
            cur,
            user_id=user_id,
            event_id="evt_w",
            event_at=t2,
            new_status=_STATUS_CLOSED_WON,
        )
        assert _read_user(cur, user_id)["locked_at"] is None

        # 4. reserve now succeeds.
        cur.execute(
            """
            SELECT credit_reserve(
                %s::uuid, %s::uuid, %s::text
            )
            """,
            (user_id, str(uuid.uuid4()), _ACTION_GLOWUP),
        )
        balance = _balance(cur, user_id)
        assert balance == (
            _PLAN_VERSION_V1_PRO_MONTHLY_ALLOTMENT_MILLI
            - _PLAN_VERSION_V1_PRO_GLOWUP_COST_MILLI
        )
