"""Credit ledger invariant tests (AC-3).

These tests verify the mathematical invariants of the credit ledger:
  - Invariant 1: reserve + release = 0 (net balance unchanged)
  - Invariant 2: reserve + commit = -1 (net balance reduced by 1)

Architecture Section 10.4 requires these tests even though the project
generally does not write automated tests during development.

Tests exercise the production CreditLedger class with a mocked Supabase
client that captures written rows in memory.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock
from uuid import UUID, uuid4

# Delay import to handle missing supabase dependency gracefully
try:
    from app.entitlement.ledger import CreditLedger
    _HAS_SUPABASE = True
except ImportError:
    _HAS_SUPABASE = False


class _MockExecuteResult:
    """Mock Supabase .execute() result."""

    def __init__(self, data=None, count=None):
        self.data = data
        self.count = count


class _InMemorySupabase:
    """Minimal in-memory mock of the Supabase Client for ledger testing.

    Captures all inserts to credit_ledger and credit_reservations tables.
    Supports select/single queries by id on credit_reservations.
    """

    def __init__(self) -> None:
        self.ledger_rows: list[dict] = []
        self.reservation_rows: list[dict] = []

    def table(self, name: str) -> "_TableBuilder":
        return _TableBuilder(self, name)

    def rpc(self, name: str, params: dict) -> "_RpcBuilder":
        # Simulate RPC unavailable — force fallback path
        raise Exception(f"RPC {name} not available in test")


class _TableBuilder:
    """Mock table query builder that stores/retrieves from _InMemorySupabase."""

    def __init__(self, db: _InMemorySupabase, table: str) -> None:
        self._db = db
        self._table = table
        self._row: dict | None = None
        self._filters: dict = {}
        self._update_data: dict | None = None
        self._select_fields: str = "*"

    def select(self, fields: str = "*", **kwargs) -> "_TableBuilder":
        self._select_fields = fields
        return self

    def insert(self, row: dict) -> "_TableBuilder":
        self._row = row
        return self

    def update(self, data: dict) -> "_TableBuilder":
        self._update_data = data
        return self

    def eq(self, field: str, value) -> "_TableBuilder":
        self._filters[field] = value
        return self

    def single(self) -> "_TableBuilder":
        return self

    def execute(self) -> _MockExecuteResult:
        rows = self._db.ledger_rows if self._table == "credit_ledger" else self._db.reservation_rows

        # INSERT
        if self._row is not None:
            rows.append(self._row)
            return _MockExecuteResult(data=self._row)

        # UPDATE
        if self._update_data is not None:
            for row in rows:
                if all(row.get(k) == v for k, v in self._filters.items()):
                    row.update(self._update_data)
                    return _MockExecuteResult(data=row)
            return _MockExecuteResult(data=None)

        # SELECT with filters
        if self._filters:
            for row in rows:
                if all(row.get(k) == v for k, v in self._filters.items()):
                    return _MockExecuteResult(data=row)
            return _MockExecuteResult(data=None)

        # SELECT all (for balance computation)
        return _MockExecuteResult(data=rows)


@unittest.skipUnless(_HAS_SUPABASE, "supabase package not installed")
class TestCreditLedgerInvariants(unittest.TestCase):
    """Verify credit ledger reserve/release/commit invariants using production CreditLedger."""

    def setUp(self) -> None:
        self.db = _InMemorySupabase()
        self.ledger = CreditLedger(self.db)  # type: ignore[arg-type]
        self.user_id = uuid4()

        # Seed initial balance of 5 credits
        self.db.ledger_rows.append({
            "user_id": str(self.user_id),
            "delta": 5,
            "type": "purchase",
        })

    def test_invariant_1_reserve_plus_release_equals_zero(self):
        """reserve + release = 0 (net balance unchanged)."""
        initial = self.ledger.balance(self.user_id)
        self.assertEqual(initial, 5)

        reservation_id = self.ledger.reserve(self.user_id)
        after_reserve = self.ledger.balance(self.user_id)
        self.assertEqual(after_reserve, 4)

        self.ledger.release(reservation_id)
        after_release = self.ledger.balance(self.user_id)
        self.assertEqual(after_release, 5)  # restored

    def test_invariant_2_reserve_plus_commit_equals_minus_one(self):
        """reserve + commit = -1 (net balance reduced by 1)."""
        initial = self.ledger.balance(self.user_id)
        self.assertEqual(initial, 5)

        reservation_id = self.ledger.reserve(self.user_id)
        after_reserve = self.ledger.balance(self.user_id)
        self.assertEqual(after_reserve, 4)

        self.ledger.commit(reservation_id)
        after_commit = self.ledger.balance(self.user_id)
        self.assertEqual(after_commit, 4)  # same as after reserve (commit delta=0)

    def test_multiple_reserves_mixed_outcomes(self):
        """3 reserves: 2 committed, 1 released → balance reduced by 2."""
        initial = self.ledger.balance(self.user_id)
        self.assertEqual(initial, 5)

        r1 = self.ledger.reserve(self.user_id)
        r2 = self.ledger.reserve(self.user_id)
        r3 = self.ledger.reserve(self.user_id)
        self.assertEqual(self.ledger.balance(self.user_id), 2)  # 5 - 3

        self.ledger.commit(r1)
        self.ledger.commit(r2)
        self.ledger.release(r3)
        self.assertEqual(self.ledger.balance(self.user_id), 3)  # 5 - 2 consumed, 1 returned

    def test_reserve_writes_delta_negative_one(self):
        """Reserve creates a ledger entry with delta = -1."""
        self.ledger.reserve(self.user_id)
        reserve_entries = [r for r in self.db.ledger_rows if r["type"] == "reserve"]
        self.assertEqual(len(reserve_entries), 1)
        self.assertEqual(reserve_entries[0]["delta"], -1)

    def test_release_writes_delta_positive_one(self):
        """Release creates a ledger entry with delta = +1."""
        rid = self.ledger.reserve(self.user_id)
        self.ledger.release(rid)
        release_entries = [r for r in self.db.ledger_rows if r["type"] == "release"]
        self.assertEqual(len(release_entries), 1)
        self.assertEqual(release_entries[0]["delta"], 1)

    def test_commit_writes_delta_zero(self):
        """Commit creates a ledger entry with delta = 0."""
        rid = self.ledger.reserve(self.user_id)
        self.ledger.commit(rid)
        commit_entries = [r for r in self.db.ledger_rows if r["type"] == "commit"]
        self.assertEqual(len(commit_entries), 1)
        self.assertEqual(commit_entries[0]["delta"], 0)

    def test_release_already_released_raises(self):
        """Releasing an already-released reservation raises ValueError."""
        rid = self.ledger.reserve(self.user_id)
        self.ledger.release(rid)
        with self.assertRaises(ValueError):
            self.ledger.release(rid)

    def test_commit_already_committed_raises(self):
        """Committing an already-committed reservation raises ValueError."""
        rid = self.ledger.reserve(self.user_id)
        self.ledger.commit(rid)
        with self.assertRaises(ValueError):
            self.ledger.commit(rid)


if __name__ == "__main__":
    unittest.main()
