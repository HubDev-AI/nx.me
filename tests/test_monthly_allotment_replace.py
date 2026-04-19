"""Tests for credit_apply_monthly_allotment_v2 (Unit 3).

Verifies the REPLACE semantics of the monthly-allotment RPC:

    current_non_pack_balance = SUM(delta)
        WHERE type NOT IN ('credit_pack_purchase', 'reserve', 'commit')
    net_delta = plan.monthly_allotment_milli - current_non_pack_balance
    INSERT single ledger row:
        (delta=net_delta, type='monthly_allotment',
         reference_id=plan_version_id,
         metadata={discarded_milli: <prior>, plan_version_id: <uuid>})

Pattern mirrors tests/test_credit_ledger_invariants.py — the RPC contract
is modelled in Python so the test matrix runs without a live Postgres.
"""

from __future__ import annotations

import unittest
from uuid import uuid4


# Types that must be excluded from the non-pack REPLACE baseline.
# Pack credits survive renewals (R11). Reserve/commit markers are
# excluded so a mid-flight reservation is not REPLACE'd away, and so
# the subsequent release cannot double-credit into the new allotment
# (adversarial race fix — see Key Technical Decisions).
_NON_PACK_EXCLUDED_TYPES = frozenset({"credit_pack_purchase", "reserve", "commit"})


class _LedgerFake:
    """In-memory model of `credit_ledger` + `plan_versions` tables
    and the monthly-allotment RPC contract."""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.plan_versions: dict[str, dict] = {}

    # -- table helpers -------------------------------------------------
    def seed_plan_version(
        self, plan_version_id: str, monthly_allotment_milli: int
    ) -> None:
        self.plan_versions[plan_version_id] = {
            "id": plan_version_id,
            "monthly_allotment_milli": monthly_allotment_milli,
        }

    def insert(
        self,
        user_id: str,
        delta: int,
        type_: str,
        reference_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        self.rows.append(
            {
                "user_id": user_id,
                "delta": delta,
                "type": type_,
                "reference_id": reference_id,
                "metadata": metadata,
            }
        )

    def rows_for(self, user_id: str) -> list[dict]:
        return [r for r in self.rows if r["user_id"] == user_id]

    def balance(self, user_id: str) -> int:
        return sum(r["delta"] for r in self.rows if r["user_id"] == user_id)

    def non_pack_balance(self, user_id: str) -> int:
        return sum(
            r["delta"]
            for r in self.rows
            if r["user_id"] == user_id and r["type"] not in _NON_PACK_EXCLUDED_TYPES
        )

    # -- RPC contract --------------------------------------------------
    def credit_apply_monthly_allotment_v2(
        self, user_id: str, plan_version_id: str
    ) -> None:
        plan = self.plan_versions.get(plan_version_id)
        if plan is None:
            raise RuntimeError(f"plan_version_not_found: {plan_version_id}")

        current = self.non_pack_balance(user_id)
        allotment = plan["monthly_allotment_milli"]

        self.insert(
            user_id=user_id,
            delta=allotment - current,
            type_="monthly_allotment",
            reference_id=plan_version_id,
            metadata={
                "discarded_milli": current,
                "plan_version_id": plan_version_id,
            },
        )


class TestMonthlyAllotmentReplace(unittest.TestCase):
    def setUp(self) -> None:
        self.db = _LedgerFake()
        self.user_id = str(uuid4())
        self.plan_id = str(uuid4())
        self.db.seed_plan_version(self.plan_id, monthly_allotment_milli=3000)

    # -- Happy path ----------------------------------------------------
    def test_replace_emits_single_entry_with_discarded_metadata(self) -> None:
        """Pro user with 2500 non-pack + 500 pack: single entry with
        delta=+500, metadata.discarded_milli=2500."""
        # Seed prior balance: 2500 non-pack (signup_grant) + 500 pack.
        self.db.insert(self.user_id, 2500, "signup_grant")
        self.db.insert(self.user_id, 500, "credit_pack_purchase")

        self.db.credit_apply_monthly_allotment_v2(self.user_id, self.plan_id)

        alloc_entries = [
            r
            for r in self.db.rows_for(self.user_id)
            if r["type"] == "monthly_allotment"
        ]
        self.assertEqual(len(alloc_entries), 1, "exactly one monthly_allotment entry")
        entry = alloc_entries[0]
        self.assertEqual(
            entry["delta"], 500, "3000 allotment - 2500 prior = +500 delta"
        )
        self.assertEqual(entry["metadata"]["discarded_milli"], 2500)
        self.assertEqual(entry["metadata"]["plan_version_id"], self.plan_id)
        self.assertEqual(entry["reference_id"], self.plan_id)

    def test_balance_lands_at_allotment_plus_pack(self) -> None:
        """Post-REPLACE: non-pack = allotment (3000), pack preserved (500),
        total balance = 3500."""
        self.db.insert(self.user_id, 2500, "signup_grant")
        self.db.insert(self.user_id, 500, "credit_pack_purchase")

        self.db.credit_apply_monthly_allotment_v2(self.user_id, self.plan_id)

        self.assertEqual(self.db.non_pack_balance(self.user_id), 3000)
        # Pack row + monthly_allotment delta: pack survives.
        pack_total = sum(
            r["delta"]
            for r in self.db.rows_for(self.user_id)
            if r["type"] == "credit_pack_purchase"
        )
        self.assertEqual(pack_total, 500)
        self.assertEqual(self.db.balance(self.user_id), 3500)

    # -- Edge case: zero baseline -------------------------------------
    def test_zero_baseline_emits_single_entry_no_phantom(self) -> None:
        """Fresh user with 0 non-pack balance: single entry
        (+3000, monthly_allotment, metadata.discarded_milli=0).
        No "phantom" second row."""
        self.db.credit_apply_monthly_allotment_v2(self.user_id, self.plan_id)

        rows = self.db.rows_for(self.user_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["delta"], 3000)
        self.assertEqual(rows[0]["metadata"]["discarded_milli"], 0)
        self.assertEqual(self.db.balance(self.user_id), 3000)

    # -- Adversarial race: in-flight reserve ---------------------------
    def test_in_flight_reserve_is_excluded_from_replace_baseline(self) -> None:
        """Adversarial race: user reserves 100 milli, then renewal fires.

        current_non_pack_balance must exclude the reserve entry so the
        REPLACE delta is computed from the pre-reserve baseline (200),
        not the post-reserve remainder (100).

        Sequence:
          1. Seed 200 non-pack (signup_grant)
          2. Simulate reserve -100 (type='reserve')  — in-flight
          3. Renewal fires → credit_apply_monthly_allotment_v2
             expected delta: 3000 - 200 = 2800  (not 3000 - 100 = 2900)

        Rationale (see plan Key Technical Decisions / Unit 3 Approach):
          - If we included 'reserve', a subsequent 'commit' (delta=0)
            or 'release' (delta=+100) would either over- or under-credit
            the new allotment. Excluding both keeps the released refund
            going back to the user on top of the new allotment, which is
            the correct user-facing behaviour.
        """
        # Pre-reserve baseline.
        self.db.insert(self.user_id, 200, "signup_grant")
        # In-flight reservation lands mid-allotment.
        self.db.insert(self.user_id, -100, "reserve", reference_id=str(uuid4()))

        self.db.credit_apply_monthly_allotment_v2(self.user_id, self.plan_id)

        alloc = [
            r
            for r in self.db.rows_for(self.user_id)
            if r["type"] == "monthly_allotment"
        ][0]
        # 3000 - 200 = 2800; the -100 reserve is excluded from the baseline.
        self.assertEqual(alloc["delta"], 2800)
        self.assertEqual(alloc["metadata"]["discarded_milli"], 200)

    def test_commit_marker_is_excluded_from_replace_baseline(self) -> None:
        """Same principle, for the commit marker (delta=0 but excluded
        to keep the symmetry with 'reserve' — neither side of the
        reserve/commit pair distorts the REPLACE baseline)."""
        self.db.insert(self.user_id, 200, "signup_grant")
        self.db.insert(self.user_id, -100, "reserve", reference_id=str(uuid4()))
        self.db.insert(self.user_id, 0, "commit", reference_id=str(uuid4()))

        self.db.credit_apply_monthly_allotment_v2(self.user_id, self.plan_id)

        alloc = [
            r
            for r in self.db.rows_for(self.user_id)
            if r["type"] == "monthly_allotment"
        ][0]
        self.assertEqual(alloc["delta"], 2800)

    def test_pack_credits_survive_replace_unchanged(self) -> None:
        """R11 invariant: pack credits are preserved across REPLACE."""
        self.db.insert(
            self.user_id, 500, "credit_pack_purchase", reference_id=str(uuid4())
        )
        self.db.insert(
            self.user_id, 750, "credit_pack_purchase", reference_id=str(uuid4())
        )
        # Add non-pack that should be discarded.
        self.db.insert(self.user_id, 1000, "weekly_free_grant")

        self.db.credit_apply_monthly_allotment_v2(self.user_id, self.plan_id)

        pack_total = sum(
            r["delta"]
            for r in self.db.rows_for(self.user_id)
            if r["type"] == "credit_pack_purchase"
        )
        self.assertEqual(pack_total, 1250, "pack rows untouched by REPLACE")
        self.assertEqual(self.db.non_pack_balance(self.user_id), 3000)
        self.assertEqual(self.db.balance(self.user_id), 3000 + 1250)

    # -- Error path ----------------------------------------------------
    def test_unknown_plan_version_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            self.db.credit_apply_monthly_allotment_v2(self.user_id, str(uuid4()))


if __name__ == "__main__":
    unittest.main()
