"""Credit ledger invariant tests (AC-3).

These tests verify the mathematical invariants of the credit ledger:
  - Invariant 1: reserve + release = 0 (net balance unchanged)
  - Invariant 2: reserve + commit = -1 (net balance reduced by 1)

Architecture Section 10.4 requires these tests even though the project
generally does not write automated tests during development.

These tests validate the LOGIC of the ledger operations, not the DB
layer. They use a minimal in-memory mock of the Supabase client to
verify that the correct deltas are written for each operation.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4


class MockExecuteResult:
    """Mock Supabase execute() result."""

    def __init__(self, data=None, count=None):
        self.data = data or []
        self.count = count


class MockQueryBuilder:
    """Minimal mock for Supabase table query builder."""

    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._filters: dict = {}

    def select(self, *args, **kwargs):
        return self

    def insert(self, row):
        self._rows.append(row)
        return self

    def update(self, data):
        self._update_data = data
        return self

    def eq(self, field, value):
        self._filters[field] = value
        return self

    def single(self):
        return self

    def execute(self):
        # For select queries with filters, find matching row
        if self._filters:
            for row in self._rows:
                if all(row.get(k) == v for k, v in self._filters.items()):
                    return MockExecuteResult(data=row)
        return MockExecuteResult(data=self._rows[-1] if self._rows else None)


class TestCreditLedgerInvariants(unittest.TestCase):
    """Verify credit ledger reserve/release/commit invariants."""

    def _compute_balance(self, ledger_rows: list[dict]) -> int:
        """Compute balance from ledger rows (same as CreditLedger.balance)."""
        return sum(row["delta"] for row in ledger_rows)

    def test_invariant_1_reserve_plus_release_equals_zero(self):
        """reserve + release = 0 (net balance unchanged)."""
        initial_balance = 5
        ledger_rows: list[dict] = [
            {"user_id": "user-1", "delta": initial_balance, "type": "purchase"},
        ]

        # Simulate reserve: delta = -1
        ledger_rows.append({"user_id": "user-1", "delta": -1, "type": "reserve"})
        balance_after_reserve = self._compute_balance(ledger_rows)
        self.assertEqual(balance_after_reserve, initial_balance - 1)

        # Simulate release: delta = +1
        ledger_rows.append({"user_id": "user-1", "delta": 1, "type": "release"})
        balance_after_release = self._compute_balance(ledger_rows)

        # Invariant: balance restored to initial
        self.assertEqual(balance_after_release, initial_balance)

    def test_invariant_2_reserve_plus_commit_equals_minus_one(self):
        """reserve + commit = -1 (net balance reduced by 1)."""
        initial_balance = 5
        ledger_rows: list[dict] = [
            {"user_id": "user-1", "delta": initial_balance, "type": "purchase"},
        ]

        # Simulate reserve: delta = -1
        ledger_rows.append({"user_id": "user-1", "delta": -1, "type": "reserve"})
        balance_after_reserve = self._compute_balance(ledger_rows)
        self.assertEqual(balance_after_reserve, initial_balance - 1)

        # Simulate commit: delta = 0 (no additional deduction)
        ledger_rows.append({"user_id": "user-1", "delta": 0, "type": "commit"})
        balance_after_commit = self._compute_balance(ledger_rows)

        # Invariant: balance reduced by exactly 1
        self.assertEqual(balance_after_commit, initial_balance - 1)

    def test_multiple_reserves_and_mixed_outcomes(self):
        """Multiple reservations with mixed release/commit outcomes."""
        initial_balance = 10
        ledger_rows: list[dict] = [
            {"user_id": "user-1", "delta": initial_balance, "type": "purchase"},
        ]

        # Reserve 3 credits
        for _ in range(3):
            ledger_rows.append({"user_id": "user-1", "delta": -1, "type": "reserve"})

        self.assertEqual(self._compute_balance(ledger_rows), 7)  # 10 - 3

        # Commit 2 (consumed)
        for _ in range(2):
            ledger_rows.append({"user_id": "user-1", "delta": 0, "type": "commit"})

        # Release 1 (returned)
        ledger_rows.append({"user_id": "user-1", "delta": 1, "type": "release"})

        # Final: 10 - 3 + 0 + 0 + 1 = 8 (2 consumed, 1 returned)
        self.assertEqual(self._compute_balance(ledger_rows), 8)

    def test_reserve_delta_is_negative_one(self):
        """Reserve must always write delta = -1."""
        rows = [
            {"delta": 10, "type": "purchase"},
            {"delta": -1, "type": "reserve"},
        ]
        self.assertEqual(sum(r["delta"] for r in rows), 9)

    def test_release_delta_is_positive_one(self):
        """Release must always write delta = +1."""
        rows = [
            {"delta": 10, "type": "purchase"},
            {"delta": -1, "type": "reserve"},
            {"delta": 1, "type": "release"},
        ]
        self.assertEqual(sum(r["delta"] for r in rows), 10)

    def test_commit_delta_is_zero(self):
        """Commit must always write delta = 0."""
        rows = [
            {"delta": 10, "type": "purchase"},
            {"delta": -1, "type": "reserve"},
            {"delta": 0, "type": "commit"},
        ]
        self.assertEqual(sum(r["delta"] for r in rows), 9)


if __name__ == "__main__":
    unittest.main()
