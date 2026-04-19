"""Tests for the `_v2` credit RPCs added by migration 0049.

These RPCs resolve cost server-side from `plan_versions` via an action-type
parameter (R23). The test harness mirrors `tests/test_credit_ledger_invariants.py`
— it simulates RPC behaviour in memory rather than touching a live database —
because `tests/conftest.py` is mocks-only.

Covered scenarios (from Unit 2 of the payments-credits-only plan):

  * Happy path — reserve → commit (balance drops by cost).
  * Happy path — reserve → release (balance restored).
  * Happy path — reserve → refund on committed (balance restored).
  * Edge case — ada_message reserve at balance < 5 raises InsufficientCredits.
  * Edge case — concurrent reserves serialize via an advisory lock: 10 threads
    at balance=300 milli (glowup=100 each) → exactly 3 succeed.
  * Error path — unknown action type raises.
  * Error path — reserve on a user with `locked_at IS NOT NULL` raises
    AccountLocked (P0002).
  * Integration — `locked_at` set between reserve and commit converts the
    commit to a release (dispute-during-in-flight, R4).
  * Integration — Phase A legacy `credit_reserve/release/commit/refund` remain
    callable alongside the `_v2` RPCs (no type clash).
"""

from __future__ import annotations

import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import UUID, uuid4


# Cost table — mirrors the seeded `v1_free_default` row from migration 0048
# (price=0, monthly=0, glowup=100, ada=5).
_GLOWUP_COST_MILLI = 100
_ADA_COST_MILLI = 5
_V1_FREE_DEFAULT_ID = UUID("11111111-2222-3333-4444-555555555555")
_V1_PRO_ID = UUID("66666666-7777-8888-9999-aaaaaaaaaaaa")


class _RpcException(Exception):
    """Mock analogue of a Postgres RAISE EXCEPTION."""

    def __init__(self, message: str, errcode: str) -> None:
        super().__init__(message)
        self.errcode = errcode


class _MockExecuteResult:
    def __init__(self, data=None):
        self.data = data


class _RpcResult:
    def __init__(self, data=None):
        self._data = data

    def execute(self) -> _MockExecuteResult:
        return _MockExecuteResult(data=self._data)


class _InMemorySupabaseV2:
    """Simulates the `_v2` RPCs plus the legacy v1 RPCs in memory.

    Matches the behaviour defined in `app/migrations/0049_credit_rpcs_v2.sql`:
      * cost resolved via plan_versions lookup (active subscription or
        v1_free_default fallback),
      * dispute lock via `users.locked_at`,
      * advisory lock per user (modelled as a re-entrant `threading.RLock`
        keyed on the stringified user_id) to serialize concurrent reserves.
    """

    def __init__(self) -> None:
        self.ledger_rows: list[dict] = []
        self.reservation_rows: list[dict] = []
        # user_id (str) -> row dict
        self.users: dict[str, dict] = {}
        # user_id (str) -> plan_version_id
        self.active_subscriptions: dict[str, UUID] = {}
        # plan_version_id -> costs dict
        self.plan_versions: dict[UUID, dict] = {
            _V1_FREE_DEFAULT_ID: {
                "glowup_cost_milli": _GLOWUP_COST_MILLI,
                "ada_cost_milli": _ADA_COST_MILLI,
                "version_num": "v1_free_default",
            },
            _V1_PRO_ID: {
                "glowup_cost_milli": _GLOWUP_COST_MILLI,
                "ada_cost_milli": _ADA_COST_MILLI,
                "version_num": "v1_pro",
            },
        }
        # user_id (str) -> lock — models pg_advisory_xact_lock(hashtextextended(user_id, 0)).
        self._user_locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    # -- helpers -----------------------------------------------------------

    def _lock_for(self, user_id: str) -> threading.RLock:
        with self._locks_guard:
            lock = self._user_locks.get(user_id)
            if lock is None:
                lock = threading.RLock()
                self._user_locks[user_id] = lock
            return lock

    def _balance(self, user_id: str) -> int:
        return sum(r["delta"] for r in self.ledger_rows if r["user_id"] == user_id)

    def _resolve_plan_version_id(self, user_id: str) -> UUID:
        plan_version_id = self.active_subscriptions.get(user_id)
        if plan_version_id is None:
            plan_version_id = _V1_FREE_DEFAULT_ID  # v1_free_default fallback
        return plan_version_id

    def _resolve_cost(self, plan_version_id: UUID, action_type: str) -> int:
        row = self.plan_versions[plan_version_id]
        if action_type == "glowup":
            return int(row["glowup_cost_milli"])
        if action_type == "ada_message":
            return int(row["ada_cost_milli"])
        raise _RpcException(f"unknown_action_type: {action_type}", "P0001")

    # -- RPC dispatch ------------------------------------------------------

    def rpc(self, name: str, params: dict) -> _RpcResult:
        if name == "credit_reserve_v2":
            return self._credit_reserve_v2(params)
        if name == "credit_commit_v2":
            return self._credit_commit_v2(params)
        if name == "credit_release_v2":
            return self._credit_release_v2(params)
        if name == "credit_refund_v2":
            return self._credit_refund_v2(params)
        # Legacy v1 RPCs — used by the Phase A coexistence test.
        if name == "sum_credit_balance":
            user_id = params["p_user_id"]
            return _RpcResult(data=self._balance(user_id))
        if name == "credit_reserve":
            return self._credit_reserve_v1(params)
        if name == "credit_release":
            return self._credit_release_v1(params)
        if name == "credit_commit":
            return self._credit_commit_v1(params)
        if name == "credit_refund":
            return self._credit_refund_v1(params)
        raise _RpcException(f"Unknown RPC: {name}", "42883")

    # -- _v2 RPCs ---------------------------------------------------------

    def _credit_reserve_v2(self, params: dict) -> _RpcResult:
        user_id = str(params["p_user_id"])
        reservation_id = str(params["p_reservation_id"])
        action_type = params["p_action_type"]

        # Fail fast on unknown action types before acquiring the lock
        # (matches SQL: unknown_action_type check precedes advisory lock).
        if action_type not in ("glowup", "ada_message"):
            raise _RpcException(f"unknown_action_type: {action_type}", "P0001")

        with self._lock_for(user_id):
            user_row = self.users.get(user_id, {})
            if user_row.get("locked_at") is not None:
                raise _RpcException("account_locked", "P0001")

            plan_version_id = self._resolve_plan_version_id(user_id)
            cost = self._resolve_cost(plan_version_id, action_type)

            balance = self._balance(user_id)
            if balance < cost:
                raise _RpcException("insufficient_credits", "P0001")

            now = datetime.now(tz=timezone.utc).isoformat()
            self.reservation_rows.append(
                {
                    "id": reservation_id,
                    "user_id": user_id,
                    "amount": cost,
                    "status": "reserved",
                    "created_at": now,
                }
            )
            self.ledger_rows.append(
                {
                    "user_id": user_id,
                    "delta": -cost,
                    "type": "reserve",
                    "reference_id": reservation_id,
                }
            )
            return _RpcResult(data={"id": reservation_id, "amount": cost})

    def _credit_commit_v2(self, params: dict) -> _RpcResult:
        reservation_id = str(params["p_reservation_id"])
        reservation = self._find_reservation(reservation_id)
        if reservation is None:
            return _RpcResult(data=None)

        user_id = reservation["user_id"]
        amount = reservation["amount"]

        with self._lock_for(user_id):
            user_row = self.users.get(user_id, {})
            if user_row.get("locked_at") is not None:
                # Dispute lock landed between reserve and commit — convert to
                # release so the user is refunded. Image stays visible
                # (quarantine deferred to v1.1).
                if reservation["status"] != "reserved":
                    return _RpcResult(data=None)
                reservation["status"] = "released"
                self.ledger_rows.append(
                    {
                        "user_id": user_id,
                        "delta": amount,
                        "type": "release",
                        "reference_id": reservation_id,
                    }
                )
                return _RpcResult(
                    data={"id": reservation_id, "converted_to_release": True}
                )

            if reservation["status"] != "reserved":
                return _RpcResult(data=None)
            reservation["status"] = "committed"
            self.ledger_rows.append(
                {
                    "user_id": user_id,
                    "delta": 0,
                    "type": "commit",
                    "reference_id": reservation_id,
                }
            )
            return _RpcResult(data={"id": reservation_id})

    def _credit_release_v2(self, params: dict) -> _RpcResult:
        reservation_id = str(params["p_reservation_id"])
        reservation = self._find_reservation(reservation_id)
        if reservation is None:
            return _RpcResult(data=None)
        user_id = reservation["user_id"]
        amount = reservation["amount"]
        with self._lock_for(user_id):
            if reservation["status"] != "reserved":
                return _RpcResult(data=None)
            reservation["status"] = "released"
            self.ledger_rows.append(
                {
                    "user_id": user_id,
                    "delta": amount,
                    "type": "release",
                    "reference_id": reservation_id,
                }
            )
            return _RpcResult(data={"id": reservation_id})

    def _credit_refund_v2(self, params: dict) -> _RpcResult:
        reservation_id = str(params["p_reservation_id"])
        reservation = self._find_reservation(reservation_id)
        if reservation is None:
            return _RpcResult(data=None)
        user_id = reservation["user_id"]
        amount = reservation["amount"]
        with self._lock_for(user_id):
            if reservation["status"] != "committed":
                return _RpcResult(data=None)
            reservation["status"] = "released"
            self.ledger_rows.append(
                {
                    "user_id": user_id,
                    "delta": amount,
                    "type": "refund",
                    "reference_id": reservation_id,
                }
            )
            return _RpcResult(data={"id": reservation_id})

    # -- legacy v1 RPCs (Phase A coexistence) -----------------------------

    def _credit_reserve_v1(self, params: dict) -> _RpcResult:
        user_id = str(params["p_user_id"])
        reservation_id = str(params["p_reservation_id"])
        with self._lock_for(user_id):
            if self._balance(user_id) <= 0:
                raise _RpcException("insufficient_credits", "P0001")
            self.reservation_rows.append(
                {
                    "id": reservation_id,
                    "user_id": user_id,
                    "amount": 1,
                    "status": "reserved",
                    "created_at": datetime.now(tz=timezone.utc).isoformat(),
                }
            )
            self.ledger_rows.append(
                {
                    "user_id": user_id,
                    "delta": -1,
                    "type": "reserve",
                    "reference_id": reservation_id,
                }
            )
            return _RpcResult(data={"id": reservation_id})

    def _credit_release_v1(self, params: dict) -> _RpcResult:
        reservation_id = str(params["p_reservation_id"])
        reservation = self._find_reservation(reservation_id)
        if reservation is None or reservation["status"] != "reserved":
            return _RpcResult(data=None)
        reservation["status"] = "released"
        self.ledger_rows.append(
            {
                "user_id": reservation["user_id"],
                "delta": 1,
                "type": "release",
                "reference_id": reservation_id,
            }
        )
        return _RpcResult(data={"id": reservation_id})

    def _credit_commit_v1(self, params: dict) -> _RpcResult:
        reservation_id = str(params["p_reservation_id"])
        reservation = self._find_reservation(reservation_id)
        if reservation is None or reservation["status"] != "reserved":
            return _RpcResult(data=None)
        reservation["status"] = "committed"
        self.ledger_rows.append(
            {
                "user_id": reservation["user_id"],
                "delta": 0,
                "type": "commit",
                "reference_id": reservation_id,
            }
        )
        return _RpcResult(data={"id": reservation_id})

    def _credit_refund_v1(self, params: dict) -> _RpcResult:
        reservation_id = str(params["p_reservation_id"])
        reservation = self._find_reservation(reservation_id)
        if reservation is None or reservation["status"] != "committed":
            return _RpcResult(data=None)
        reservation["status"] = "released"
        self.ledger_rows.append(
            {
                "user_id": reservation["user_id"],
                "delta": 1,
                "type": "refund",
                "reference_id": reservation_id,
            }
        )
        return _RpcResult(data={"id": reservation_id})

    # -- internal helpers --------------------------------------------------

    def _find_reservation(self, reservation_id: str) -> dict | None:
        for row in self.reservation_rows:
            if row["id"] == reservation_id:
                return row
        return None


# ---------------------------------------------------------------------------
# Helpers for tests
# ---------------------------------------------------------------------------


def _seed_user(
    db: _InMemorySupabaseV2,
    balance_milli: int,
    *,
    locked: bool = False,
    plan: str = "v1_free_default",
) -> str:
    user_id = str(uuid4())
    db.users[user_id] = {
        "id": user_id,
        "locked_at": datetime.now(tz=timezone.utc).isoformat() if locked else None,
    }
    if plan == "v1_pro":
        db.active_subscriptions[user_id] = _V1_PRO_ID
    # Seed initial balance via a `monthly_allotment`-like entry (type irrelevant
    # in-memory; real DB uses the 0048 extended enum).
    if balance_milli:
        db.ledger_rows.append(
            {
                "user_id": user_id,
                "delta": balance_milli,
                "type": "monthly_allotment",
                "reference_id": None,
            }
        )
    return user_id


def _reserve(db: _InMemorySupabaseV2, user_id: str, action_type: str) -> str:
    reservation_id = str(uuid4())
    db.rpc(
        "credit_reserve_v2",
        {
            "p_user_id": user_id,
            "p_reservation_id": reservation_id,
            "p_action_type": action_type,
        },
    ).execute()
    return reservation_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCreditRpcsV2HappyPath(unittest.TestCase):
    """Reserve → commit, reserve → release, reserve → refund."""

    def test_reserve_then_commit_drops_balance_by_cost(self) -> None:
        db = _InMemorySupabaseV2()
        user_id = _seed_user(db, balance_milli=3000)

        self.assertEqual(db._balance(user_id), 3000)

        res_id = _reserve(db, user_id, "glowup")
        self.assertEqual(db._balance(user_id), 2900)

        db.rpc("credit_commit_v2", {"p_reservation_id": res_id}).execute()
        # commit writes delta=0 — balance stays at 2900.
        self.assertEqual(db._balance(user_id), 2900)

        reservation = db._find_reservation(res_id)
        assert reservation is not None
        self.assertEqual(reservation["status"], "committed")
        self.assertEqual(reservation["amount"], _GLOWUP_COST_MILLI)

    def test_reserve_then_release_restores_balance(self) -> None:
        db = _InMemorySupabaseV2()
        user_id = _seed_user(db, balance_milli=3000)

        res_id = _reserve(db, user_id, "glowup")
        self.assertEqual(db._balance(user_id), 2900)

        db.rpc("credit_release_v2", {"p_reservation_id": res_id}).execute()
        self.assertEqual(db._balance(user_id), 3000)

        reservation = db._find_reservation(res_id)
        assert reservation is not None
        self.assertEqual(reservation["status"], "released")

    def test_refund_on_committed_restores_balance(self) -> None:
        db = _InMemorySupabaseV2()
        user_id = _seed_user(db, balance_milli=3000)

        res_id = _reserve(db, user_id, "glowup")
        db.rpc("credit_commit_v2", {"p_reservation_id": res_id}).execute()
        self.assertEqual(db._balance(user_id), 2900)

        db.rpc("credit_refund_v2", {"p_reservation_id": res_id}).execute()
        self.assertEqual(db._balance(user_id), 3000)

        reservation = db._find_reservation(res_id)
        assert reservation is not None
        self.assertEqual(reservation["status"], "released")

    def test_ada_message_costs_five_milli(self) -> None:
        db = _InMemorySupabaseV2()
        user_id = _seed_user(db, balance_milli=50)

        res_id = _reserve(db, user_id, "ada_message")
        self.assertEqual(db._balance(user_id), 45)

        reservation = db._find_reservation(res_id)
        assert reservation is not None
        self.assertEqual(reservation["amount"], _ADA_COST_MILLI)


class TestCreditRpcsV2EdgeCases(unittest.TestCase):
    """Edge cases around cost resolution, insufficient balance, and locking."""

    def test_ada_message_at_balance_under_five_raises_insufficient_credits(
        self,
    ) -> None:
        db = _InMemorySupabaseV2()
        user_id = _seed_user(db, balance_milli=4)

        with self.assertRaises(_RpcException) as ctx:
            _reserve(db, user_id, "ada_message")

        self.assertEqual(ctx.exception.errcode, "P0001")
        self.assertIn("insufficient_credits", str(ctx.exception))
        # No ledger mutation — balance unchanged.
        self.assertEqual(db._balance(user_id), 4)

    def test_glowup_at_balance_under_cost_raises_insufficient_credits(self) -> None:
        db = _InMemorySupabaseV2()
        user_id = _seed_user(db, balance_milli=99)

        with self.assertRaises(_RpcException) as ctx:
            _reserve(db, user_id, "glowup")

        self.assertEqual(ctx.exception.errcode, "P0001")

    def test_concurrent_reserves_serialize_via_advisory_lock(self) -> None:
        """10 concurrent glowup reserves on balance=300 → exactly 3 succeed."""
        db = _InMemorySupabaseV2()
        user_id = _seed_user(db, balance_milli=300)

        successes: list[str] = []
        failures: list[_RpcException] = []
        successes_lock = threading.Lock()

        def attempt() -> None:
            try:
                rid = _reserve(db, user_id, "glowup")
                with successes_lock:
                    successes.append(rid)
            except _RpcException as exc:
                with successes_lock:
                    failures.append(exc)

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(attempt) for _ in range(10)]
            for f in futures:
                f.result()

        self.assertEqual(
            len(successes), 3, "balance=300 / cost=100 → exactly 3 reserves succeed"
        )
        self.assertEqual(len(failures), 7)
        for exc in failures:
            self.assertEqual(exc.errcode, "P0001")
            self.assertIn("insufficient_credits", str(exc))

        # Balance drained to zero; reservation rows count matches successes.
        self.assertEqual(db._balance(user_id), 0)
        reserved = [r for r in db.reservation_rows if r["user_id"] == user_id]
        self.assertEqual(len(reserved), 3)


class TestCreditRpcsV2ErrorPaths(unittest.TestCase):
    """Unknown action type, locked account."""

    def test_unknown_action_type_raises(self) -> None:
        db = _InMemorySupabaseV2()
        user_id = _seed_user(db, balance_milli=3000)

        with self.assertRaises(_RpcException) as ctx:
            db.rpc(
                "credit_reserve_v2",
                {
                    "p_user_id": user_id,
                    "p_reservation_id": str(uuid4()),
                    "p_action_type": "unknown",
                },
            ).execute()

        self.assertEqual(ctx.exception.errcode, "P0001")
        self.assertIn("unknown_action_type", str(ctx.exception))
        # No reservation or ledger row created.
        self.assertEqual(db.reservation_rows, [])
        self.assertEqual(db._balance(user_id), 3000)

    def test_reserve_on_locked_user_raises_account_locked(self) -> None:
        db = _InMemorySupabaseV2()
        user_id = _seed_user(db, balance_milli=3000, locked=True)

        with self.assertRaises(_RpcException) as ctx:
            _reserve(db, user_id, "glowup")

        self.assertEqual(ctx.exception.errcode, "P0001")
        self.assertIn("account_locked", str(ctx.exception))


class TestCreditRpcsV2Integration(unittest.TestCase):
    """Dispute-during-in-flight + Phase A coexistence."""

    def test_commit_during_dispute_lock_converts_to_release(self) -> None:
        """locked_at set between reserve and commit → commit_v2 refunds user.

        Mirrors the R4 dispute-during-in-flight path: reservation is in
        'reserved' state when the dispute lock lands; commit_v2 detects
        locked_at, flips status='released', and writes +amount/'release'.
        """
        db = _InMemorySupabaseV2()
        user_id = _seed_user(db, balance_milli=3000)

        res_id = _reserve(db, user_id, "glowup")
        self.assertEqual(db._balance(user_id), 2900)

        # Simulate apply_dispute_event setting locked_at between reserve
        # and commit.
        db.users[user_id]["locked_at"] = datetime.now(tz=timezone.utc).isoformat()

        db.rpc("credit_commit_v2", {"p_reservation_id": res_id}).execute()

        # Balance restored (release refund); reservation marked 'released'
        # rather than 'committed' — the user gets the credit back even though
        # the image generation already happened (quarantine deferred to v1.1).
        self.assertEqual(db._balance(user_id), 3000)
        reservation = db._find_reservation(res_id)
        assert reservation is not None
        self.assertEqual(reservation["status"], "released")

        # The ledger entry for the conversion is type='release', not 'commit'.
        commit_rows = [
            r
            for r in db.ledger_rows
            if r["reference_id"] == res_id and r["type"] == "commit"
        ]
        release_rows = [
            r
            for r in db.ledger_rows
            if r["reference_id"] == res_id and r["type"] == "release"
        ]
        self.assertEqual(commit_rows, [], "no commit row written when dispute-locked")
        self.assertEqual(len(release_rows), 1)
        self.assertEqual(release_rows[0]["delta"], _GLOWUP_COST_MILLI)

    def test_legacy_v1_rpcs_coexist_with_v2(self) -> None:
        """Phase A invariant: legacy credit_reserve/release/commit/refund stay
        callable alongside the `_v2` RPCs without conflict."""
        db = _InMemorySupabaseV2()
        user_id = _seed_user(db, balance_milli=100)

        # Legacy path — cost=1 hardcoded.
        v1_rid = str(uuid4())
        db.rpc(
            "credit_reserve",
            {"p_user_id": user_id, "p_reservation_id": v1_rid},
        ).execute()
        self.assertEqual(db._balance(user_id), 99)

        db.rpc("credit_commit", {"p_reservation_id": v1_rid}).execute()
        self.assertEqual(db._balance(user_id), 99)

        # v2 path — cost resolved from plan_versions (glowup=100). Balance is
        # now 99 after the legacy reserve+commit; glowup=100 → rejection.
        with self.assertRaises(_RpcException) as ctx:
            _reserve(db, user_id, "glowup")
        self.assertEqual(ctx.exception.errcode, "P0001")

        # ada_message fits (cost=5) → succeeds.
        v2_rid = _reserve(db, user_id, "ada_message")
        self.assertEqual(db._balance(user_id), 94)

        # Both reservations present, with their respective amounts.
        v1_row = db._find_reservation(v1_rid)
        v2_row = db._find_reservation(v2_rid)
        assert v1_row is not None and v2_row is not None
        self.assertEqual(v1_row["amount"], 1)
        self.assertEqual(v2_row["amount"], _ADA_COST_MILLI)

        # Legacy refund still flips committed → released and writes +1.
        db.rpc("credit_refund", {"p_reservation_id": v1_rid}).execute()
        self.assertEqual(db._balance(user_id), 95)
        v1_row_after = db._find_reservation(v1_rid)
        assert v1_row_after is not None
        self.assertEqual(v1_row_after["status"], "released")


class TestCreditRpcsV2PlanVersionLookup(unittest.TestCase):
    """Cost resolution path — active subscription vs v1_free_default fallback."""

    def test_user_without_subscription_uses_v1_free_default(self) -> None:
        db = _InMemorySupabaseV2()
        user_id = _seed_user(db, balance_milli=200)
        # No active subscription → v1_free_default (glowup=100).
        self.assertNotIn(user_id, db.active_subscriptions)

        _reserve(db, user_id, "glowup")
        self.assertEqual(db._balance(user_id), 100)

    def test_user_with_active_subscription_uses_that_plan_version(self) -> None:
        db = _InMemorySupabaseV2()
        user_id = _seed_user(db, balance_milli=500, plan="v1_pro")
        self.assertEqual(db.active_subscriptions[user_id], _V1_PRO_ID)

        _reserve(db, user_id, "glowup")
        self.assertEqual(db._balance(user_id), 400)


# ---------------------------------------------------------------------------
# Live-DB concurrency + auth-guard tests (G9)
# ---------------------------------------------------------------------------
#
# The in-memory harness above models the advisory-lock contract but cannot
# prove that Postgres's own `pg_advisory_xact_lock` serializes concurrent
# transactions the same way, nor that the `auth.uid()` guard raises
# SQLSTATE 42501 on a cross-user invocation. These live-DB tests close
# both gaps against the local Supabase Postgres at 127.0.0.1:54322.
#
# Skipped cleanly when the DB isn't reachable (pattern mirrors
# tests/test_dispute_lifecycle.py) so CI/laptops without Supabase pass.


import os  # noqa: E402 — optional deps live-DB block isolated from in-memory tests

try:
    import psycopg2  # noqa: E402

    _PSYCOPG_AVAILABLE = True
except ImportError:  # pragma: no cover — psycopg2 missing in some test envs
    _PSYCOPG_AVAILABLE = False


_DEFAULT_LOCAL_DSN = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
_LIVE_GLOWUP_BALANCE_MILLI = 300
_LIVE_EXPECTED_SUCCESSES = 3  # balance 300 / glowup cost 100
_LIVE_THREAD_COUNT = 10
_ACCOUNT_LOCKED_SQLSTATE = "P0001"
_FORBIDDEN_SQLSTATE = "42501"


def _live_db_dsn() -> str:
    return os.environ.get("DATABASE_URL", _DEFAULT_LOCAL_DSN)


def _live_db_reachable() -> bool:
    if not _PSYCOPG_AVAILABLE:
        return False
    try:
        conn = psycopg2.connect(_live_db_dsn(), connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


def _live_auth_helpers_installed() -> bool:
    """True iff the `auth.uid()` / `auth.role()` helpers Supabase installs
    are present. Vanilla Postgres lacks them and would make the 42501 test
    spurious."""
    if not _PSYCOPG_AVAILABLE:
        return False
    try:
        conn = psycopg2.connect(_live_db_dsn(), connect_timeout=2)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1
                      FROM pg_proc p
                      JOIN pg_namespace n ON n.oid = p.pronamespace
                     WHERE n.nspname = 'auth'
                       AND p.proname IN ('uid', 'role')
                    """
                )
                return len(cur.fetchall()) >= 2
        finally:
            conn.close()
    except Exception:
        return False


def _live_rpc_installed(rpc_name: str) -> bool:
    if not _PSYCOPG_AVAILABLE:
        return False
    try:
        conn = psycopg2.connect(_live_db_dsn(), connect_timeout=2)
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


@unittest.skipUnless(_PSYCOPG_AVAILABLE, "psycopg2 not installed")
@unittest.skipUnless(
    _live_db_reachable(), f"local Postgres not reachable at {_live_db_dsn()}"
)
@unittest.skipUnless(
    _live_rpc_installed("credit_reserve_v2"),
    "migration 0049 not applied — credit_reserve_v2 missing",
)
class TestLiveDBConcurrency(unittest.TestCase):
    """Live-DB proofs for advisory-lock serialization + `auth.uid()` guard.

    Every test commits its fixtures (each worker thread needs its own
    autocommit connection so the main thread sees the seeded user) and
    cleans up explicitly in `tearDown` — no outer rollback-the-world
    transaction because the point is to exercise multiple concurrent
    sessions against the same row.
    """

    def setUp(self) -> None:
        self._conn = psycopg2.connect(_live_db_dsn())
        self._conn.autocommit = True
        self._created_user_ids: list[str] = []

    def tearDown(self) -> None:
        try:
            if self._created_user_ids:
                with self._conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM credit_reservations WHERE user_id = ANY(%s::uuid[])",
                        (self._created_user_ids,),
                    )
                    cur.execute(
                        "DELETE FROM credit_ledger WHERE user_id = ANY(%s::uuid[])",
                        (self._created_user_ids,),
                    )
                    cur.execute(
                        "DELETE FROM users WHERE id = ANY(%s::uuid[])",
                        (self._created_user_ids,),
                    )
        finally:
            self._conn.close()

    def _insert_user_and_seed_balance(self, balance_milli: int) -> str:
        with self._conn.cursor() as cur:
            suffix = uuid4().hex[:12]
            cur.execute(
                """
                INSERT INTO users (username, display_name, email_verified, tier_id)
                VALUES (
                    %s, %s, FALSE,
                    (SELECT id FROM tiers WHERE is_default = TRUE LIMIT 1)
                )
                RETURNING id
                """,
                (f"livetest_{suffix}", f"LiveTest {suffix}"),
            )
            user_id = cur.fetchone()[0]
            self._created_user_ids.append(str(user_id))
            cur.execute(
                """
                INSERT INTO credit_ledger (user_id, delta, type, reference_id)
                VALUES (%s, %s, 'monthly_allotment', gen_random_uuid())
                """,
                (str(user_id), balance_milli),
            )
            return str(user_id)

    def test_concurrent_reserves_serialize_via_advisory_lock_real_postgres(
        self,
    ) -> None:
        """10 threads, separate connections, balance=300. Exactly 3 succeed.

        Proves `pg_advisory_xact_lock(hashtextextended(user_id::text, 0))`
        serializes Stripe-style concurrent reserves under real Postgres —
        the in-memory harness uses a Python `threading.RLock`, which could
        mask a missing advisory lock in the SQL.
        """
        user_id = self._insert_user_and_seed_balance(_LIVE_GLOWUP_BALANCE_MILLI)

        successes: list[str] = []
        failures: list[Exception] = []
        results_lock = threading.Lock()

        def attempt() -> None:
            conn = psycopg2.connect(_live_db_dsn())
            try:
                conn.autocommit = True
                reservation_id = str(uuid4())
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT credit_reserve_v2(%s::uuid, %s::uuid, %s::text)",
                            (user_id, reservation_id, "glowup"),
                        )
                    with results_lock:
                        successes.append(reservation_id)
                except psycopg2.errors.RaiseException as exc:
                    with results_lock:
                        failures.append(exc)
            finally:
                conn.close()

        with ThreadPoolExecutor(max_workers=_LIVE_THREAD_COUNT) as pool:
            list(pool.map(lambda _: attempt(), range(_LIVE_THREAD_COUNT)))

        self.assertEqual(
            len(successes),
            _LIVE_EXPECTED_SUCCESSES,
            f"balance=300 / glowup=100 → exactly {_LIVE_EXPECTED_SUCCESSES} reserves succeed",
        )
        self.assertEqual(len(failures), _LIVE_THREAD_COUNT - _LIVE_EXPECTED_SUCCESSES)
        for exc in failures:
            self.assertEqual(exc.pgcode, _ACCOUNT_LOCKED_SQLSTATE)
            self.assertIn("insufficient_credits", str(exc))

        # Balance drained to zero.
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(delta), 0) FROM credit_ledger WHERE user_id = %s",
                (user_id,),
            )
            final_balance = cur.fetchone()[0]
        self.assertEqual(final_balance, 0)

    @unittest.skipUnless(
        _live_auth_helpers_installed(),
        "auth.uid()/auth.role() not installed — Supabase helpers missing",
    )
    def test_42501_cross_user_call_rejected(self) -> None:
        """Setting JWT claims for user A and invoking credit_reserve_v2 for
        user B must RAISE with SQLSTATE 42501 (`forbidden`).

        Proves the `auth.uid() IS DISTINCT FROM p_user_id` guard added by
        migration 0049 rejects cross-user calls. The test skips when the
        `auth` schema helpers aren't present, so running against a vanilla
        Postgres image (no Supabase bootstrap) doesn't produce a false
        failure.
        """
        user_a = self._insert_user_and_seed_balance(_LIVE_GLOWUP_BALANCE_MILLI)
        user_b = self._insert_user_and_seed_balance(_LIVE_GLOWUP_BALANCE_MILLI)

        # New dedicated connection so SET LOCAL is scoped to this one tx.
        conn = psycopg2.connect(_live_db_dsn())
        conn.autocommit = False
        try:
            with conn.cursor() as cur:
                claims = f'{{"role":"authenticated","sub":"{user_a}"}}'
                cur.execute("SET LOCAL request.jwt.claims = %s", (claims,))
                reservation_id = str(uuid4())
                with self.assertRaises(psycopg2.errors.InsufficientPrivilege) as ctx:
                    cur.execute(
                        "SELECT credit_reserve_v2(%s::uuid, %s::uuid, %s::text)",
                        (user_b, reservation_id, "glowup"),
                    )
                self.assertEqual(ctx.exception.pgcode, _FORBIDDEN_SQLSTATE)
        finally:
            conn.rollback()
            conn.close()


if __name__ == "__main__":
    unittest.main()
