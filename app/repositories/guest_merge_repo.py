"""Repository for the merge_guest_ledger RPC (Unit 10).

Wraps the Postgres function that atomically transfers a guest user's credit
ledger into a newly-registered authenticated user's ledger.

RPC contract (migration 0050):
    merge_guest_ledger(
        p_guest_user_id      UUID,
        p_new_user_id        UUID,
        p_signup_grant_milli INT,
        p_install_uuid_hash  BYTEA  -- NULL accepted when guest has no stored hash
    ) RETURNS jsonb {
        transferred_non_pack: int,
        transferred_pack:     int,
        truncated_milli:      int
    }

Error codes raised by the RPC:
    P0001 — install_uuid_mismatch (theft attempt) or already_merged
    42501 — forbidden (cross-user attempt)

Callers map these to HTTP 403 / 409 as appropriate.
"""

from __future__ import annotations

import logging
from uuid import UUID

from supabase import Client

logger = logging.getLogger(__name__)


class GuestMergeRepository:
    def __init__(self, supabase: Client) -> None:
        self._supabase = supabase

    def merge(
        self,
        guest_user_id: UUID,
        new_user_id: UUID,
        signup_grant_milli: int,
        install_uuid_hash: bytes | None,
    ) -> dict:
        """Invoke the merge_guest_ledger RPC and return its result dict.

        Args:
            guest_user_id: UUID of the ephemeral guest user.
            new_user_id: UUID of the newly-registered authenticated user.
            signup_grant_milli: Signup grant value used to compute the 2x cap.
            install_uuid_hash: HMAC-SHA256 hash of the X-Install-UUID header,
                or None when the header was absent (pre-rollout / web clients).

        Returns:
            dict with keys: transferred_non_pack, transferred_pack, truncated_milli.

        Raises:
            Exception: Raw Supabase/Postgres exception. Callers inspect the
                message/code to map to HTTP errors:
                - SQLSTATE P0001 (install_uuid_mismatch) → HTTP 403
                - SQLSTATE P0001 (already_merged)        → HTTP 409
                - SQLSTATE 42501 (forbidden)             → HTTP 403
        """
        params: dict = {
            "p_guest_user_id": str(guest_user_id),
            "p_new_user_id": str(new_user_id),
            "p_signup_grant_milli": signup_grant_milli,
            # Supabase RPC sends BYTEA as a hex-encoded string prefixed with \x
            "p_install_uuid_hash": (
                f"\\x{install_uuid_hash.hex()}"
                if install_uuid_hash is not None
                else None
            ),
        }
        result = self._supabase.rpc("merge_guest_ledger", params).execute()
        data: dict = result.data or {}
        logger.info(
            "merge_guest_ledger guest=%s new_user=%s result=%s",
            guest_user_id,
            new_user_id,
            data,
        )
        return data
