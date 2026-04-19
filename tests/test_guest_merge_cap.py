"""Tests for merge_guest_ledger_v2 (Unit 10).

The RPC atomically transfers a guest user's ledger into a new
authenticated user:

  * non_pack = SUM(delta) WHERE type NOT IN
        ('credit_pack_purchase', 'reserve', 'commit')
  * pack     = SUM(delta) WHERE type = 'credit_pack_purchase'
  * transfer_non_pack = LEAST(non_pack, 2 * signup_grant_milli)
  * truncated         = non_pack - transfer_non_pack
  * pack transfers whole (no cap) — theft prevention lives in the
    install-UUID binding, not a cap
  * audit row (0, 'guest_merge_truncated') with metadata.truncated_milli
    written iff truncated > 0
  * users.merged_into_user_id + merged_at stamped on the guest row
  * install-UUID mismatch → P0003 (no transfer, guest not marked merged)
  * already_merged guest → P0004

Pattern mirrors tests/test_credit_ledger_invariants.py and
tests/test_monthly_allotment_replace.py — the RPC contract is modelled
in Python so the tests run without a live Postgres.
"""

from __future__ import annotations

import unittest
import uuid
from uuid import uuid4


_NS_URL = uuid.NAMESPACE_URL

_NON_PACK_EXCLUDED_TYPES = frozenset({"credit_pack_purchase", "reserve", "commit"})


# Error codes matching the SQL RAISE ERRCODE values.
_ERR_INSTALL_UUID_MISMATCH = "P0001"
_ERR_ALREADY_MERGED = "P0001"


class GuestMergeError(RuntimeError):
    def __init__(self, sqlstate: str, message: str) -> None:
        super().__init__(message)
        self.sqlstate = sqlstate


class _MergeFake:
    """Python model of merge_guest_ledger_v2 + users.merged_* columns."""

    def __init__(self) -> None:
        self.ledger: list[dict] = []
        # users keyed by id → {guest_install_uuid_hash, merged_into_user_id, merged_at}
        self.users: dict[str, dict] = {}

    # -- Seeding -------------------------------------------------------
    def seed_user(
        self,
        user_id: str,
        guest_install_uuid_hash: bytes | None = None,
    ) -> None:
        self.users[user_id] = {
            "id": user_id,
            "guest_install_uuid_hash": guest_install_uuid_hash,
            "merged_into_user_id": None,
            "merged_at": None,
        }

    def insert_ledger(
        self,
        user_id: str,
        delta: int,
        type_: str,
        reference_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        self.ledger.append(
            {
                "user_id": user_id,
                "delta": delta,
                "type": type_,
                "reference_id": reference_id,
                "metadata": metadata,
            }
        )

    # -- Queries --------------------------------------------------------
    def rows_for(self, user_id: str) -> list[dict]:
        return [r for r in self.ledger if r["user_id"] == user_id]

    def balance(self, user_id: str) -> int:
        return sum(r["delta"] for r in self.ledger if r["user_id"] == user_id)

    def _non_pack(self, user_id: str) -> int:
        return sum(
            r["delta"]
            for r in self.ledger
            if r["user_id"] == user_id and r["type"] not in _NON_PACK_EXCLUDED_TYPES
        )

    def _pack(self, user_id: str) -> int:
        return sum(
            r["delta"]
            for r in self.ledger
            if r["user_id"] == user_id and r["type"] == "credit_pack_purchase"
        )

    # -- RPC contract ---------------------------------------------------
    def merge_guest_ledger_v2(
        self,
        guest_user_id: str,
        new_user_id: str,
        signup_grant_milli: int,
        install_uuid_hash: bytes | None,
    ) -> dict:
        guest = self.users[guest_user_id]

        # Install-UUID binding.
        stored = guest["guest_install_uuid_hash"]
        if stored is not None:
            if install_uuid_hash is None or install_uuid_hash != stored:
                raise GuestMergeError(
                    _ERR_INSTALL_UUID_MISMATCH, "install_uuid_mismatch"
                )

        if guest["merged_at"] is not None:
            raise GuestMergeError(_ERR_ALREADY_MERGED, "already_merged")

        non_pack = self._non_pack(guest_user_id)
        pack = self._pack(guest_user_id)
        cap = 2 * signup_grant_milli
        transfer_non_pack = min(non_pack, cap)
        truncated = non_pack - transfer_non_pack

        self.insert_ledger(new_user_id, transfer_non_pack, "guest_merge_non_pack")

        pack_ref = uuid.uuid5(_NS_URL, f"guest_merge:{guest_user_id}")
        self.insert_ledger(
            new_user_id,
            pack,
            "credit_pack_purchase",
            reference_id=pack_ref,
        )

        if truncated > 0:
            self.insert_ledger(
                new_user_id,
                0,
                "guest_merge_truncated",
                metadata={"truncated_milli": truncated},
            )

        guest["merged_into_user_id"] = new_user_id
        guest["merged_at"] = "now"

        return {
            "transferred_non_pack": transfer_non_pack,
            "transferred_pack": pack,
            "truncated_milli": truncated,
        }


class TestGuestMergeCap(unittest.TestCase):
    SIGNUP_GRANT = 300  # 2x cap = 600
    INSTALL_HASH = b"\x11" * 32

    def setUp(self) -> None:
        self.db = _MergeFake()
        self.guest_id = str(uuid4())
        self.new_user_id = str(uuid4())
        self.db.seed_user(self.guest_id, guest_install_uuid_hash=self.INSTALL_HASH)
        self.db.seed_user(self.new_user_id)

    # -- Non-pack: under cap ------------------------------------------
    def test_non_pack_under_cap_full_transfer(self) -> None:
        """Guest with 500 non-pack (< 2x300 cap) transfers whole."""
        self.db.insert_ledger(self.guest_id, 300, "signup_grant")
        self.db.insert_ledger(self.guest_id, 100, "weekly_free_grant")
        self.db.insert_ledger(self.guest_id, 100, "weekly_free_grant")

        result = self.db.merge_guest_ledger_v2(
            self.guest_id,
            self.new_user_id,
            self.SIGNUP_GRANT,
            self.INSTALL_HASH,
        )

        self.assertEqual(result["transferred_non_pack"], 500)
        self.assertEqual(result["transferred_pack"], 0)
        self.assertEqual(result["truncated_milli"], 0)
        self.assertEqual(self.db.balance(self.new_user_id), 500)
        # No truncation audit row.
        truncated_rows = [
            r
            for r in self.db.rows_for(self.new_user_id)
            if r["type"] == "guest_merge_truncated"
        ]
        self.assertEqual(truncated_rows, [])

    def test_non_pack_exactly_at_cap_no_truncation(self) -> None:
        """Boundary: non_pack == 2x signup_grant exactly → no truncation."""
        cap = 2 * self.SIGNUP_GRANT  # 600
        self.db.insert_ledger(self.guest_id, cap, "signup_grant")

        result = self.db.merge_guest_ledger_v2(
            self.guest_id,
            self.new_user_id,
            self.SIGNUP_GRANT,
            self.INSTALL_HASH,
        )

        self.assertEqual(result["transferred_non_pack"], cap)
        self.assertEqual(result["truncated_milli"], 0)

    # -- Non-pack: over cap (truncated) -------------------------------
    def test_non_pack_over_cap_truncated_and_audit_written(self) -> None:
        """Guest with 700 non-pack transfers 600 (cap); 100 truncated;
        audit row (0, 'guest_merge_truncated', metadata.truncated_milli=100)
        written on the new user."""
        self.db.insert_ledger(self.guest_id, 700, "signup_grant")

        result = self.db.merge_guest_ledger_v2(
            self.guest_id,
            self.new_user_id,
            self.SIGNUP_GRANT,
            self.INSTALL_HASH,
        )

        self.assertEqual(result["transferred_non_pack"], 600)
        self.assertEqual(result["truncated_milli"], 100)

        audit = [
            r
            for r in self.db.rows_for(self.new_user_id)
            if r["type"] == "guest_merge_truncated"
        ]
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0]["delta"], 0)
        self.assertEqual(audit[0]["metadata"]["truncated_milli"], 100)
        # Balance reflects the capped transfer, not the pre-cap amount.
        self.assertEqual(self.db.balance(self.new_user_id), 600)

    # -- Pack: always whole (no cap) ----------------------------------
    def test_pack_transfers_whole_even_over_cap(self) -> None:
        """Pack credits bypass the 2x signup_grant cap (R16)."""
        # Non-pack under cap but pack is huge.
        self.db.insert_ledger(self.guest_id, 200, "signup_grant")
        self.db.insert_ledger(self.guest_id, 1500, "credit_pack_purchase")
        self.db.insert_ledger(self.guest_id, 500, "credit_pack_purchase")

        result = self.db.merge_guest_ledger_v2(
            self.guest_id,
            self.new_user_id,
            self.SIGNUP_GRANT,
            self.INSTALL_HASH,
        )

        self.assertEqual(result["transferred_non_pack"], 200)
        self.assertEqual(result["transferred_pack"], 2000)
        self.assertEqual(result["truncated_milli"], 0)

        pack_total = sum(
            r["delta"]
            for r in self.db.rows_for(self.new_user_id)
            if r["type"] == "credit_pack_purchase"
        )
        self.assertEqual(pack_total, 2000)

    def test_pack_and_non_pack_mixed_over_cap(self) -> None:
        """Non-pack truncated but pack untouched."""
        self.db.insert_ledger(self.guest_id, 1000, "signup_grant")
        self.db.insert_ledger(self.guest_id, 500, "credit_pack_purchase")

        result = self.db.merge_guest_ledger_v2(
            self.guest_id,
            self.new_user_id,
            self.SIGNUP_GRANT,
            self.INSTALL_HASH,
        )

        self.assertEqual(result["transferred_non_pack"], 600)  # capped
        self.assertEqual(result["transferred_pack"], 500)  # whole
        self.assertEqual(result["truncated_milli"], 400)

    def test_zero_balance_guest_marked_merged(self) -> None:
        """Guest with 0 balance still has its merged_at stamped."""
        result = self.db.merge_guest_ledger_v2(
            self.guest_id,
            self.new_user_id,
            self.SIGNUP_GRANT,
            self.INSTALL_HASH,
        )

        self.assertEqual(result["transferred_non_pack"], 0)
        self.assertEqual(result["transferred_pack"], 0)
        self.assertEqual(result["truncated_milli"], 0)
        self.assertIsNotNone(self.db.users[self.guest_id]["merged_at"])
        self.assertEqual(
            self.db.users[self.guest_id]["merged_into_user_id"], self.new_user_id
        )

    def test_pack_reference_id_is_deterministic(self) -> None:
        """pack reference_id = uuid5(NS_URL, 'guest_merge:<guest_user_id>')"""
        self.db.insert_ledger(self.guest_id, 200, "credit_pack_purchase")
        self.db.merge_guest_ledger_v2(
            self.guest_id,
            self.new_user_id,
            self.SIGNUP_GRANT,
            self.INSTALL_HASH,
        )

        expected = uuid.uuid5(_NS_URL, f"guest_merge:{self.guest_id}")
        pack_rows = [
            r
            for r in self.db.rows_for(self.new_user_id)
            if r["type"] == "credit_pack_purchase"
        ]
        self.assertEqual(len(pack_rows), 1)
        self.assertEqual(pack_rows[0]["reference_id"], expected)

    # -- Install-UUID binding -----------------------------------------
    def test_install_uuid_mismatch_raises_p0003_no_transfer(self) -> None:
        """Theft attempt: attacker calls merge with a different
        install-UUID → P0003; NO ledger rows written; guest NOT marked
        merged (victim can still legitimately merge later)."""
        # Seed the guest with credits an attacker would want to steal.
        self.db.insert_ledger(self.guest_id, 500, "credit_pack_purchase")
        self.db.insert_ledger(self.guest_id, 200, "signup_grant")

        attacker_hash = b"\x22" * 32
        with self.assertRaises(GuestMergeError) as ctx:
            self.db.merge_guest_ledger_v2(
                self.guest_id,
                self.new_user_id,
                self.SIGNUP_GRANT,
                attacker_hash,
            )
        self.assertEqual(ctx.exception.sqlstate, _ERR_INSTALL_UUID_MISMATCH)

        # No side effects on the new user.
        self.assertEqual(self.db.rows_for(self.new_user_id), [])
        self.assertEqual(self.db.balance(self.new_user_id), 0)

        # Guest not marked merged.
        self.assertIsNone(self.db.users[self.guest_id]["merged_at"])
        self.assertIsNone(self.db.users[self.guest_id]["merged_into_user_id"])

    def test_null_input_hash_against_stored_hash_raises(self) -> None:
        """Caller forgot to pass X-Install-UUID header but the guest
        was bound to one → still a mismatch, not a bypass."""
        with self.assertRaises(GuestMergeError) as ctx:
            self.db.merge_guest_ledger_v2(
                self.guest_id,
                self.new_user_id,
                self.SIGNUP_GRANT,
                None,  # attacker drops the header
            )
        self.assertEqual(ctx.exception.sqlstate, _ERR_INSTALL_UUID_MISMATCH)

    def test_null_stored_hash_accepts_any_caller_hash(self) -> None:
        """Pre-rollout guest (stored hash is NULL): merge accepts any
        caller-provided hash. This is the documented residual risk."""
        pre_rollout_guest = str(uuid4())
        self.db.seed_user(pre_rollout_guest, guest_install_uuid_hash=None)
        self.db.insert_ledger(pre_rollout_guest, 300, "signup_grant")

        result = self.db.merge_guest_ledger_v2(
            pre_rollout_guest,
            self.new_user_id,
            self.SIGNUP_GRANT,
            b"\x99" * 32,  # any hash
        )

        self.assertEqual(result["transferred_non_pack"], 300)
        self.assertIsNotNone(self.db.users[pre_rollout_guest]["merged_at"])

    def test_null_stored_and_null_input_accepted(self) -> None:
        """Pre-rollout guest + web signup (both NULL): accepted."""
        pre_rollout_guest = str(uuid4())
        self.db.seed_user(pre_rollout_guest, guest_install_uuid_hash=None)

        result = self.db.merge_guest_ledger_v2(
            pre_rollout_guest,
            self.new_user_id,
            self.SIGNUP_GRANT,
            None,
        )

        self.assertEqual(result["transferred_non_pack"], 0)
        self.assertIsNotNone(self.db.users[pre_rollout_guest]["merged_at"])

    # -- Already merged ------------------------------------------------
    def test_already_merged_raises_p0004(self) -> None:
        """Second merge attempt on the same guest → P0004."""
        # First merge succeeds.
        self.db.merge_guest_ledger_v2(
            self.guest_id,
            self.new_user_id,
            self.SIGNUP_GRANT,
            self.INSTALL_HASH,
        )

        # Second attempt on the same guest.
        another_user = str(uuid4())
        self.db.seed_user(another_user)
        with self.assertRaises(GuestMergeError) as ctx:
            self.db.merge_guest_ledger_v2(
                self.guest_id,
                another_user,
                self.SIGNUP_GRANT,
                self.INSTALL_HASH,
            )
        self.assertEqual(ctx.exception.sqlstate, _ERR_ALREADY_MERGED)

        # No ledger writes on the second target.
        self.assertEqual(self.db.rows_for(another_user), [])


if __name__ == "__main__":
    unittest.main()
