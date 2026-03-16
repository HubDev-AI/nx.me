"""Credit ledger — reserve/release/commit lifecycle.

AC-3 Invariants:
  - reserve + release = 0 (net). reserve: delta=-1, release: delta=+1
  - reserve + commit = -1 (net). reserve: delta=-1, commit: delta=0
  - balance = SUM(delta) over all ledger entries for a user

These invariants are verified by unit tests in tests/test_credit_ledger_invariants.py.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
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
        """Compute current credit balance from ledger SUM(delta).

        This is the authoritative balance — never read from a cached column.
        """
        user_id_str = str(user_id)

        # Try RPC first (single query, DB-side SUM)
        try:
            result = self._sb.rpc(
                "sum_credit_balance", {"p_user_id": user_id_str}
            ).execute()
            if result.data is not None:
                return int(result.data)
        except Exception:  # noqa: BLE001
            pass

        # Fallback: client-side sum
        entries = (
            self._sb.table("credit_ledger")
            .select("delta")
            .eq("user_id", user_id_str)
            .execute()
        )
        return sum(e["delta"] for e in (entries.data or []))

    def reserve(self, user_id: UUID) -> UUID:
        """Create a credit reservation (optimistic hold).

        Writes:
          - credit_ledger: type='reserve', delta=-1
          - credit_reservations: status='reserved'

        Returns:
            reservation_id (UUID)
        """
        user_id_str = str(user_id)
        reservation_id = uuid4()
        now_utc = datetime.now(tz=timezone.utc).isoformat()

        # Insert reservation record
        self._sb.table("credit_reservations").insert({
            "id": str(reservation_id),
            "user_id": user_id_str,
            "amount": 1,
            "status": "reserved",
            "created_at": now_utc,
        }).execute()

        # Insert ledger entry
        self._sb.table("credit_ledger").insert({
            "user_id": user_id_str,
            "delta": -1,
            "type": "reserve",
            "reference_id": str(reservation_id),
        }).execute()

        logger.info("Credit reserved for user %s: reservation %s", user_id_str, reservation_id)
        return reservation_id

    def release(self, reservation_id: UUID) -> None:
        """Release a reservation — undo the hold (e.g., job failed).

        Writes:
          - credit_ledger: type='release', delta=+1
          - credit_reservations: status='released', resolved_at=NOW()

        Invariant: reserve + release = 0 (net)
        """
        res_id_str = str(reservation_id)
        now_utc = datetime.now(tz=timezone.utc).isoformat()

        # Fetch reservation to get user_id
        result = (
            self._sb.table("credit_reservations")
            .select("user_id, status")
            .eq("id", res_id_str)
            .single()
            .execute()
        )
        if not result.data:
            raise ValueError(f"Reservation {reservation_id} not found")
        if result.data["status"] != "reserved":
            raise ValueError(f"Reservation {reservation_id} is already {result.data['status']}")

        user_id_str: str = result.data["user_id"]

        # Update reservation status
        self._sb.table("credit_reservations").update({
            "status": "released",
            "resolved_at": now_utc,
        }).eq("id", res_id_str).execute()

        # Insert release ledger entry
        self._sb.table("credit_ledger").insert({
            "user_id": user_id_str,
            "delta": 1,
            "type": "release",
            "reference_id": res_id_str,
        }).execute()

        logger.info("Credit released for user %s: reservation %s", user_id_str, reservation_id)

    def commit(self, reservation_id: UUID) -> None:
        """Commit a reservation — credit is consumed (e.g., job succeeded).

        Writes:
          - credit_ledger: type='commit', delta=0
          - credit_reservations: status='committed', resolved_at=NOW()

        Invariant: reserve + commit = -1 (net). The reserve already deducted
        the credit; commit records the consumption with delta=0.
        """
        res_id_str = str(reservation_id)
        now_utc = datetime.now(tz=timezone.utc).isoformat()

        # Fetch reservation to get user_id
        result = (
            self._sb.table("credit_reservations")
            .select("user_id, status")
            .eq("id", res_id_str)
            .single()
            .execute()
        )
        if not result.data:
            raise ValueError(f"Reservation {reservation_id} not found")
        if result.data["status"] != "reserved":
            raise ValueError(f"Reservation {reservation_id} is already {result.data['status']}")

        user_id_str: str = result.data["user_id"]

        # Update reservation status
        self._sb.table("credit_reservations").update({
            "status": "committed",
            "resolved_at": now_utc,
        }).eq("id", res_id_str).execute()

        # Insert commit ledger entry (delta=0 — reserve already deducted)
        self._sb.table("credit_ledger").insert({
            "user_id": user_id_str,
            "delta": 0,
            "type": "commit",
            "reference_id": res_id_str,
        }).execute()

        logger.info("Credit committed for user %s: reservation %s", user_id_str, reservation_id)
