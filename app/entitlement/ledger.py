"""Credit ledger — reserve/release/commit lifecycle.

AC-3 Invariants:
  - reserve + release = 0 (net). reserve: delta=-1, release: delta=+1
  - reserve + commit = -1 (net). reserve: delta=-1, commit: delta=0
  - balance = SUM(delta) over all ledger entries for a user

These invariants are verified by unit tests in tests/test_credit_ledger_invariants.py.

CS-1 L-1/L-2: All mutations use RPC only (atomic). No fallback two-write paths.
If an RPC is unavailable, the operation fails — the RPC exists for atomicity.
"""

from __future__ import annotations

import logging
from uuid import UUID, uuid4

from supabase import Client

logger = logging.getLogger(__name__)


class CreditLedger:
    """Manages credit balance via append-only ledger entries.

    All credit mutations go through this class. No other code should
    write to credit_ledger or credit_reservations directly (AC-D1).
    """

    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    def balance(self, user_id: UUID) -> int:
        """Return committed credit balance for user.

        This is the authoritative balance — never read from a cached column.
        Uses the sum_credit_balance RPC for a DB-side atomic SUM.

        NOTE: This reflects committed transactions only. In-flight reserves
        (not yet committed or released) are already deducted from the ledger
        as negative deltas. The balance is thus the "worst case" available amount.

        Returns 0 for users with no ledger entries (RPC returns NULL → 0).
        Raises on RPC failure (no fallback — CS-1 AC-1).
        """
        user_id_str = str(user_id)

        try:
            result = self._sb.rpc(
                "sum_credit_balance", {"p_user_id": user_id_str}
            ).execute()
        except Exception as exc:
            raise RuntimeError(f"Credit balance RPC failed for user {user_id}") from exc

        # RPC returns NULL (None) for users with no ledger entries → 0 is correct.
        return int(result.data) if result.data is not None else 0

    def reserve(self, user_id: UUID) -> UUID:
        """Create a credit reservation (optimistic hold).

        Atomic via credit_reserve RPC: inserts both credit_reservations
        row (status='reserved') and credit_ledger entry (delta=-1) in
        a single transaction.

        Returns:
            reservation_id (UUID)

        Raises:
            Exception: If the RPC fails (no fallback — atomicity is required).
        """
        user_id_str = str(user_id)
        reservation_id = uuid4()

        self._sb.rpc(
            "credit_reserve",
            {
                "p_user_id": user_id_str,
                "p_reservation_id": str(reservation_id),
            },
        ).execute()

        logger.info(
            "Credit reserved for user %s: reservation %s", user_id_str, reservation_id
        )
        return reservation_id

    def release(self, reservation_id: UUID) -> None:
        """Release a reservation — undo the hold (e.g., job failed).

        Atomic via credit_release RPC: uses UPDATE ... WHERE status = 'reserved'
        RETURNING * to prevent TOCTOU races. If the reservation was already
        resolved, the RPC returns empty and we raise ValueError.

        Invariant: reserve + release = 0 (net)
        """
        res_id_str = str(reservation_id)

        result = self._sb.rpc(
            "credit_release",
            {
                "p_reservation_id": res_id_str,
            },
        ).execute()

        # RPC uses UPDATE ... WHERE status = 'reserved' RETURNING *
        # Empty result means reservation was already resolved
        if not result.data:
            raise ValueError(
                f"Reservation {reservation_id} not found or already resolved"
            )

        logger.info("Credit released: reservation %s", reservation_id)

    def refund(self, reservation_id: UUID) -> None:
        """Refund a committed reservation — return the consumed credit.

        Atomic via credit_refund RPC: uses UPDATE ... WHERE status = 'committed'
        RETURNING * to prevent TOCTOU races. If the reservation was not committed
        (e.g. already released), the RPC returns empty and we raise ValueError.

        Unlike release() which undoes a hold (reserved -> released),
        refund() undoes a consumption (committed -> released, delta = +1).
        """
        res_id_str = str(reservation_id)

        result = self._sb.rpc(
            "credit_refund",
            {
                "p_reservation_id": res_id_str,
            },
        ).execute()

        # RPC uses UPDATE ... WHERE status = 'committed' RETURNING *
        # Empty result means reservation was not in committed state
        if not result.data:
            raise ValueError(
                f"Reservation {reservation_id} not found or not in committed state"
            )

        logger.info("Credit refunded: reservation %s", reservation_id)

    def commit(self, reservation_id: UUID) -> None:
        """Commit a reservation — credit is consumed (e.g., job succeeded).

        Atomic via credit_commit RPC: uses UPDATE ... WHERE status = 'reserved'
        RETURNING * to prevent TOCTOU races.

        Invariant: reserve + commit = -1 (net). The reserve already deducted
        the credit; commit records the consumption with delta=0.
        """
        res_id_str = str(reservation_id)

        result = self._sb.rpc(
            "credit_commit",
            {
                "p_reservation_id": res_id_str,
            },
        ).execute()

        if not result.data:
            raise ValueError(
                f"Reservation {reservation_id} not found or already resolved"
            )

        logger.info("Credit committed: reservation %s", reservation_id)
