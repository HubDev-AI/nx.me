"""Security test: install-UUID binding prevents guest-token theft (Unit 10).

Two scenarios:
(a) install-UUID-A creates guest, install-UUID-A merges → credits transferred.
(b) install-UUID-A creates guest, install-UUID-B attempts merge → 403 +
    ledger NOT transferred + guest row merged_at IS NULL.

These tests exercise the Python model of the RPC (same fake as
test_guest_merge_cap.py) to verify the security contract without requiring
a live database.  The live-DB variant of this scenario is covered by the
install-UUID mismatch tests already present in test_guest_merge_cap.py.
"""

from __future__ import annotations

import unittest
import uuid
from uuid import uuid4

# Re-use the fake RPC model from test_guest_merge_cap.
# Import the classes directly from the sibling module.
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from test_guest_merge_cap import GuestMergeError, _MergeFake  # noqa: E402

_NS_URL = uuid.NAMESPACE_URL


class TestInstallUUIDBindingSecurity(unittest.TestCase):
    """Security binding: same-device succeeds, different-device is rejected."""

    SIGNUP_GRANT = 300  # 2x cap = 600

    # Simulate what the backend computes from X-Install-UUID headers.
    # In production: HMAC-SHA256(server_secret, install_uuid).
    # For tests: deterministic fixed bytes suffice.
    _INSTALL_UUID_A_HASH = b"\xaa" * 32
    _INSTALL_UUID_B_HASH = b"\xbb" * 32

    def setUp(self) -> None:
        self.db = _MergeFake()
        self.guest_id = str(uuid4())
        self.new_user_id = str(uuid4())

    # ------------------------------------------------------------------
    # Scenario (a): legitimate owner merges — full transfer
    # ------------------------------------------------------------------

    def test_matching_install_uuid_transfers_credits(self) -> None:
        """Guest created with UUID-A; merge called with UUID-A → success.

        Verifies that a legitimate user who created the guest session on
        their own device can always claim their accumulated credits.
        """
        # Guest bound to UUID-A at creation time.
        self.db.seed_user(
            self.guest_id,
            guest_install_uuid_hash=self._INSTALL_UUID_A_HASH,
        )
        self.db.seed_user(self.new_user_id)

        # Give the guest some credits to verify they transfer.
        self.db.insert_ledger(self.guest_id, 200, "signup_grant")
        self.db.insert_ledger(self.guest_id, 500, "credit_pack_purchase")

        result = self.db.merge_guest_ledger(
            self.guest_id,
            self.new_user_id,
            self.SIGNUP_GRANT,
            self._INSTALL_UUID_A_HASH,  # correct hash
        )

        # Non-pack: 200 < 600 cap → full transfer
        self.assertEqual(result["transferred_non_pack"], 200)
        # Pack: always whole
        self.assertEqual(result["transferred_pack"], 500)
        self.assertEqual(result["truncated_milli"], 0)

        # Guest row marked merged.
        self.assertIsNotNone(self.db.users[self.guest_id]["merged_at"])
        self.assertEqual(
            self.db.users[self.guest_id]["merged_into_user_id"], self.new_user_id
        )

    # ------------------------------------------------------------------
    # Scenario (b): attacker uses stolen token from different device → 403
    # ------------------------------------------------------------------

    def test_mismatched_install_uuid_blocked_no_ledger_transfer(self) -> None:
        """Guest created with UUID-A; merge called with UUID-B → rejected.

        Security HIGH: an attacker who intercepts the guest_session_token
        but uses a different device must be denied. The guest's credits
        must remain intact so the victim can still legitimately claim them.
        """
        # Guest bound to UUID-A at creation time.
        self.db.seed_user(
            self.guest_id,
            guest_install_uuid_hash=self._INSTALL_UUID_A_HASH,
        )
        self.db.seed_user(self.new_user_id)

        # Seed credits that the attacker wants to steal.
        self.db.insert_ledger(self.guest_id, 300, "signup_grant")
        self.db.insert_ledger(self.guest_id, 1000, "credit_pack_purchase")

        # Attacker calls merge with UUID-B.
        with self.assertRaises(GuestMergeError):
            self.db.merge_guest_ledger(
                self.guest_id,
                self.new_user_id,
                self.SIGNUP_GRANT,
                self._INSTALL_UUID_B_HASH,  # attacker's device hash
            )

        # No ledger rows written on the attacker's account.
        self.assertEqual(self.db.rows_for(self.new_user_id), [])
        self.assertEqual(self.db.balance(self.new_user_id), 0)

        # Guest NOT marked merged — victim can still legitimately claim.
        self.assertIsNone(
            self.db.users[self.guest_id]["merged_at"],
            "Guest merged_at must remain NULL after rejected merge attempt",
        )
        self.assertIsNone(self.db.users[self.guest_id]["merged_into_user_id"])

    def test_null_header_against_bound_guest_blocked(self) -> None:
        """Attacker drops the X-Install-UUID header entirely → still rejected.

        A NULL caller hash against a non-NULL stored hash is a mismatch,
        not a bypass. This closes the "omit the header" attack vector.
        """
        self.db.seed_user(
            self.guest_id,
            guest_install_uuid_hash=self._INSTALL_UUID_A_HASH,
        )
        self.db.seed_user(self.new_user_id)
        self.db.insert_ledger(self.guest_id, 500, "credit_pack_purchase")

        with self.assertRaises(GuestMergeError):
            self.db.merge_guest_ledger(
                self.guest_id,
                self.new_user_id,
                self.SIGNUP_GRANT,
                None,  # header omitted by attacker
            )

        self.assertEqual(self.db.rows_for(self.new_user_id), [])
        self.assertIsNone(self.db.users[self.guest_id]["merged_at"])

    def test_victim_can_merge_after_failed_theft_attempt(self) -> None:
        """After a rejected theft attempt the victim merges successfully.

        Confirms that a failed merge leaves the guest in a state where the
        legitimate owner (UUID-A) can still complete the merge.
        """
        self.db.seed_user(
            self.guest_id,
            guest_install_uuid_hash=self._INSTALL_UUID_A_HASH,
        )
        self.db.seed_user(self.new_user_id)
        self.db.insert_ledger(self.guest_id, 200, "signup_grant")

        # Attacker fails.
        with self.assertRaises(GuestMergeError):
            self.db.merge_guest_ledger(
                self.guest_id,
                self.new_user_id,
                self.SIGNUP_GRANT,
                self._INSTALL_UUID_B_HASH,
            )

        # Victim succeeds.
        victim_user_id = str(uuid4())
        self.db.seed_user(victim_user_id)
        result = self.db.merge_guest_ledger(
            self.guest_id,
            victim_user_id,
            self.SIGNUP_GRANT,
            self._INSTALL_UUID_A_HASH,
        )
        self.assertEqual(result["transferred_non_pack"], 200)
        self.assertIsNotNone(self.db.users[self.guest_id]["merged_at"])

    # ------------------------------------------------------------------
    # Pre-rollout / web guests (stored hash IS NULL) accept any caller
    # ------------------------------------------------------------------

    def test_unbound_guest_accepts_any_install_uuid(self) -> None:
        """Guest created without X-Install-UUID (pre-rollout / web) accepts
        any caller hash — documented residual risk, narrow scope."""
        self.db.seed_user(self.guest_id, guest_install_uuid_hash=None)
        self.db.seed_user(self.new_user_id)
        self.db.insert_ledger(self.guest_id, 100, "signup_grant")

        result = self.db.merge_guest_ledger(
            self.guest_id,
            self.new_user_id,
            self.SIGNUP_GRANT,
            self._INSTALL_UUID_B_HASH,  # any hash accepted when stored=NULL
        )

        self.assertEqual(result["transferred_non_pack"], 100)
        self.assertIsNotNone(self.db.users[self.guest_id]["merged_at"])

    def test_unbound_guest_accepts_null_caller_hash(self) -> None:
        """Pre-rollout guest + web signup (both NULL): accepted."""
        self.db.seed_user(self.guest_id, guest_install_uuid_hash=None)
        self.db.seed_user(self.new_user_id)

        result = self.db.merge_guest_ledger(
            self.guest_id,
            self.new_user_id,
            self.SIGNUP_GRANT,
            None,
        )

        self.assertEqual(result["transferred_non_pack"], 0)
        self.assertIsNotNone(self.db.users[self.guest_id]["merged_at"])


if __name__ == "__main__":
    unittest.main()
