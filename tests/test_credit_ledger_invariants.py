"""Credit ledger invariant tests (AC-3).

These tests verify the mathematical invariants of the credit ledger:
  - Invariant 1: reserve + release = 0 (net balance unchanged)
  - Invariant 2: reserve + commit = -1 (net balance reduced by 1)

Tests exercise the production CreditLedger class with a mocked Supabase
client that simulates the RPC calls.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from uuid import uuid4

try:
    from app.entitlement.ledger import CreditLedger

    _HAS_SUPABASE = True
except ImportError:
    _HAS_SUPABASE = False


class _MockExecuteResult:
    def __init__(self, data=None):
        self.data = data


class _InMemorySupabase:
    """Mock Supabase client that simulates credit ledger RPCs in memory."""

    def __init__(self) -> None:
        self.ledger_rows: list[dict] = []
        self.reservation_rows: list[dict] = []

    def rpc(self, name: str, params: dict) -> "_RpcResult":
        if name == "sum_credit_balance":
            user_id = params["p_user_id"]
            total = sum(r["delta"] for r in self.ledger_rows if r["user_id"] == user_id)
            return _RpcResult(data=total)

        if name == "credit_reserve":
            user_id = params["p_user_id"]
            res_id = params["p_reservation_id"]
            now = datetime.now(tz=timezone.utc).isoformat()
            self.reservation_rows.append(
                {
                    "id": res_id,
                    "user_id": user_id,
                    "amount": 1,
                    "status": "reserved",
                    "created_at": now,
                }
            )
            self.ledger_rows.append(
                {
                    "user_id": user_id,
                    "delta": -1,
                    "type": "reserve",
                    "reference_id": res_id,
                }
            )
            return _RpcResult(data={"id": res_id})

        if name == "credit_release":
            res_id = params["p_reservation_id"]
            for row in self.reservation_rows:
                if row["id"] == res_id and row["status"] == "reserved":
                    row["status"] = "released"
                    self.ledger_rows.append(
                        {
                            "user_id": row["user_id"],
                            "delta": 1,
                            "type": "release",
                            "reference_id": res_id,
                        }
                    )
                    return _RpcResult(data={"id": res_id})
            return _RpcResult(data=None)

        if name == "credit_commit":
            res_id = params["p_reservation_id"]
            for row in self.reservation_rows:
                if row["id"] == res_id and row["status"] == "reserved":
                    row["status"] = "committed"
                    self.ledger_rows.append(
                        {
                            "user_id": row["user_id"],
                            "delta": 0,
                            "type": "commit",
                            "reference_id": res_id,
                        }
                    )
                    return _RpcResult(data={"id": res_id})
            return _RpcResult(data=None)

        raise Exception(f"Unknown RPC: {name}")


class _RpcResult:
    def __init__(self, data=None):
        self._data = data

    def execute(self) -> _MockExecuteResult:
        return _MockExecuteResult(data=self._data)


@unittest.skipUnless(_HAS_SUPABASE, "supabase package not installed")
class TestCreditLedgerInvariants(unittest.TestCase):
    """Verify credit ledger reserve/release/commit invariants using production CreditLedger."""

    def setUp(self) -> None:
        self.db = _InMemorySupabase()
        self.ledger = CreditLedger(self.db)  # type: ignore[arg-type]
        self.user_id = uuid4()

        # Seed initial balance of 5 credits via a "purchase" ledger entry
        self.db.ledger_rows.append(
            {
                "user_id": str(self.user_id),
                "delta": 5,
                "type": "purchase",
            }
        )

    def test_invariant_1_reserve_plus_release_equals_zero(self):
        """reserve + release = 0 (net balance unchanged)."""
        self.assertEqual(self.ledger.balance(self.user_id), 5)

        rid = self.ledger.reserve(self.user_id)
        self.assertEqual(self.ledger.balance(self.user_id), 4)

        self.ledger.release(rid)
        self.assertEqual(self.ledger.balance(self.user_id), 5)

    def test_invariant_2_reserve_plus_commit_equals_minus_one(self):
        """reserve + commit = -1 (net balance reduced by 1)."""
        self.assertEqual(self.ledger.balance(self.user_id), 5)

        rid = self.ledger.reserve(self.user_id)
        self.assertEqual(self.ledger.balance(self.user_id), 4)

        self.ledger.commit(rid)
        self.assertEqual(self.ledger.balance(self.user_id), 4)

    def test_multiple_reserves_mixed_outcomes(self):
        """3 reserves: 2 committed, 1 released -> balance reduced by 2."""
        r1 = self.ledger.reserve(self.user_id)
        r2 = self.ledger.reserve(self.user_id)
        r3 = self.ledger.reserve(self.user_id)
        self.assertEqual(self.ledger.balance(self.user_id), 2)

        self.ledger.commit(r1)
        self.ledger.commit(r2)
        self.ledger.release(r3)
        self.assertEqual(self.ledger.balance(self.user_id), 3)

    def test_reserve_writes_delta_negative_one(self):
        self.ledger.reserve(self.user_id)
        reserve_entries = [r for r in self.db.ledger_rows if r["type"] == "reserve"]
        self.assertEqual(reserve_entries[0]["delta"], -1)

    def test_release_writes_delta_positive_one(self):
        rid = self.ledger.reserve(self.user_id)
        self.ledger.release(rid)
        release_entries = [r for r in self.db.ledger_rows if r["type"] == "release"]
        self.assertEqual(release_entries[0]["delta"], 1)

    def test_commit_writes_delta_zero(self):
        rid = self.ledger.reserve(self.user_id)
        self.ledger.commit(rid)
        commit_entries = [r for r in self.db.ledger_rows if r["type"] == "commit"]
        self.assertEqual(commit_entries[0]["delta"], 0)

    def test_double_release_raises(self):
        rid = self.ledger.reserve(self.user_id)
        self.ledger.release(rid)
        with self.assertRaises(ValueError):
            self.ledger.release(rid)

    def test_double_commit_raises(self):
        rid = self.ledger.reserve(self.user_id)
        self.ledger.commit(rid)
        with self.assertRaises(ValueError):
            self.ledger.commit(rid)


@unittest.skipUnless(_HAS_SUPABASE, "supabase package not installed")
class TestCreditLedgerRPCFailure(unittest.TestCase):
    """CS-1 AC-1: RPC failure must propagate as exception (no silent fallback)."""

    def test_balance_raises_on_rpc_failure(self):
        """balance() propagates RPC exceptions."""
        db = _FailingSupabase()
        ledger = CreditLedger(db)  # type: ignore[arg-type]
        with self.assertRaises(Exception):
            ledger.balance(uuid4())

    def test_reserve_raises_on_rpc_failure(self):
        """reserve() propagates RPC exceptions."""
        db = _FailingSupabase()
        ledger = CreditLedger(db)  # type: ignore[arg-type]
        with self.assertRaises(Exception):
            ledger.reserve(uuid4())

    def test_release_raises_on_rpc_failure(self):
        """release() propagates RPC exceptions."""
        db = _FailingSupabase()
        ledger = CreditLedger(db)  # type: ignore[arg-type]
        with self.assertRaises(Exception):
            ledger.release(uuid4())

    def test_commit_raises_on_rpc_failure(self):
        """commit() propagates RPC exceptions."""
        db = _FailingSupabase()
        ledger = CreditLedger(db)  # type: ignore[arg-type]
        with self.assertRaises(Exception):
            ledger.commit(uuid4())


class _FailingSupabase:
    """Mock Supabase client where all RPCs fail."""

    def rpc(self, name: str, params: dict) -> "_FailingRpc":
        return _FailingRpc()


class _FailingRpc:
    def execute(self):
        raise ConnectionError("Supabase RPC unavailable")


if __name__ == "__main__":
    unittest.main()
