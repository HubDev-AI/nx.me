"""Tests for credit_apply_weekly_free_grant_v2 (Unit 3).

The RPC must be idempotent per (user_id, iso_week):

    reference_id = uuid5(uuid_ns_url(), f'weekly:{user_id}:{iso_week}')
    INSERT ... ON CONFLICT (reference_id)
        WHERE type='weekly_free_grant' DO NOTHING

A second call for the same (user, iso_week) therefore becomes a
silent no-op (the partial UNIQUE index rejects it).

Pattern mirrors tests/test_credit_ledger_invariants.py.
"""

from __future__ import annotations

import unittest
import uuid
from uuid import UUID, uuid4


# Stable URL namespace matches Postgres' uuid_ns_url() value so tests
# that peek at reference_id can verify the derivation without pulling
# in the server-side RPC.
_NS_URL = uuid.NAMESPACE_URL


def _weekly_ref(user_id: str, iso_week: str) -> UUID:
    return uuid.uuid5(_NS_URL, f"weekly:{user_id}:{iso_week}")


class _WeeklyGrantFake:
    """Python model of credit_apply_weekly_free_grant_v2 backed by
    the partial UNIQUE index."""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    def credit_apply_weekly_free_grant_v2(
        self,
        user_id: str,
        iso_week: str,
        weekly_grant_milli: int,
    ) -> None:
        dedup = _weekly_ref(user_id, iso_week)

        # Partial UNIQUE on reference_id WHERE type='weekly_free_grant'.
        # Only weekly_free_grant rows participate in the dedup check —
        # other types (signup_grant, pack_purchase) can reuse UUIDs
        # freely.
        existing = [
            r
            for r in self.rows
            if r["type"] == "weekly_free_grant" and r["reference_id"] == dedup
        ]
        if existing:
            return  # ON CONFLICT DO NOTHING

        self.rows.append(
            {
                "user_id": user_id,
                "delta": weekly_grant_milli,
                "type": "weekly_free_grant",
                "reference_id": dedup,
            }
        )

    def rows_for(self, user_id: str) -> list[dict]:
        return [r for r in self.rows if r["user_id"] == user_id]

    def balance(self, user_id: str) -> int:
        return sum(r["delta"] for r in self.rows if r["user_id"] == user_id)


class TestWeeklyFreeGrantIdempotency(unittest.TestCase):
    def setUp(self) -> None:
        self.db = _WeeklyGrantFake()
        self.user_id = str(uuid4())
        self.iso_week = "2026-W16"
        self.grant = 100  # per plan_versions v1 (1 glowup worth)

    # -- Happy path ----------------------------------------------------
    def test_first_call_inserts_single_entry(self) -> None:
        self.db.credit_apply_weekly_free_grant_v2(
            self.user_id, self.iso_week, self.grant
        )

        rows = self.db.rows_for(self.user_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["delta"], 100)
        self.assertEqual(rows[0]["type"], "weekly_free_grant")
        self.assertEqual(self.db.balance(self.user_id), 100)

    def test_reference_id_is_deterministic_uuid5(self) -> None:
        """The reference_id must be uuid5(NS_URL, 'weekly:<user>:<iso_week>')
        so two independent callers with the same inputs derive the same UUID
        and the second insert collides on the partial UNIQUE index."""
        self.db.credit_apply_weekly_free_grant_v2(
            self.user_id, self.iso_week, self.grant
        )

        rows = self.db.rows_for(self.user_id)
        expected = _weekly_ref(self.user_id, self.iso_week)
        self.assertEqual(rows[0]["reference_id"], expected)

    # -- Core idempotency ---------------------------------------------
    def test_same_week_is_noop(self) -> None:
        """Second call for the same (user, iso_week) is a silent no-op.

        One ledger row; balance unchanged on the second call.
        This is the test referenced in plan Unit 3 Verification:
            tests/test_weekly_free_grant_idempotency.py::test_same_week_is_noop
        """
        self.db.credit_apply_weekly_free_grant_v2(
            self.user_id, self.iso_week, self.grant
        )
        self.db.credit_apply_weekly_free_grant_v2(
            self.user_id, self.iso_week, self.grant
        )

        rows = self.db.rows_for(self.user_id)
        self.assertEqual(len(rows), 1, "ON CONFLICT DO NOTHING suppressed duplicate")
        self.assertEqual(self.db.balance(self.user_id), 100)

    def test_n_times_same_week_still_one_entry(self) -> None:
        """Stress the ON CONFLICT branch: many repeat calls still emit
        exactly one ledger row."""
        for _ in range(25):
            self.db.credit_apply_weekly_free_grant_v2(
                self.user_id, self.iso_week, self.grant
            )

        rows = self.db.rows_for(self.user_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(self.db.balance(self.user_id), 100)

    # -- Boundary: different weeks --------------------------------------
    def test_different_iso_weeks_both_insert(self) -> None:
        """Different ISO weeks derive different reference_ids → both
        calls succeed. This is the "next Monday" case."""
        self.db.credit_apply_weekly_free_grant_v2(self.user_id, "2026-W16", self.grant)
        self.db.credit_apply_weekly_free_grant_v2(self.user_id, "2026-W17", self.grant)

        rows = self.db.rows_for(self.user_id)
        self.assertEqual(len(rows), 2)
        self.assertEqual(self.db.balance(self.user_id), 200)

    def test_different_users_same_week_both_insert(self) -> None:
        """Different users in the same ISO week derive different
        reference_ids → both rows are written."""
        other_user = str(uuid4())
        self.db.credit_apply_weekly_free_grant_v2(
            self.user_id, self.iso_week, self.grant
        )
        self.db.credit_apply_weekly_free_grant_v2(other_user, self.iso_week, self.grant)

        self.assertEqual(len(self.db.rows_for(self.user_id)), 1)
        self.assertEqual(len(self.db.rows_for(other_user)), 1)


if __name__ == "__main__":
    unittest.main()
