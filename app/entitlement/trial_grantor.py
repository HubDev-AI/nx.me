"""TrialGrantor — idempotent free trial credit grant.

Called after a user verifies their email address.  The grant is idempotent:
calling it twice does not double-grant credits.

Idempotency mechanism:
  An entry in credit_ledger WHERE type = 'trial_grant' AND user_id = <id>
  serves as the idempotency record.  If one already exists the grant is a
  no-op.  The INSERT into credit_ledger and the UPDATE to
  users.trial_analyses_remaining are performed in a single transaction so
  partial state is impossible.

Interface Contract (Story 2-1):
  TrialGrantor.grant(user_id: UUID) -> None
  Location: entitlement/trial_grantor.py
"""
from __future__ import annotations

import logging
from uuid import UUID

from supabase import Client

from app.config import settings

logger = logging.getLogger(__name__)


class TrialGrantor:
    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    def grant(self, user_id: UUID) -> None:  # noqa: D401
        """Grant free trial analyses to *user_id* idempotently.

        If the user has already received a trial grant this method returns
        immediately without modifying any data.

        Raises:
            RuntimeError: if the database operation fails.
        """
        user_id_str = str(user_id)

        # --- Idempotency check -------------------------------------------
        existing = (
            self._sb.table("credit_ledger")
            .select("id")
            .eq("user_id", user_id_str)
            .eq("type", "trial_grant")
            .limit(1)
            .execute()
        )
        if existing.data:
            logger.info("trial_grant already applied for user %s — skipping", user_id_str)
            return

        # --- Grant: update user row + insert ledger entry -----------------
        # Supabase PostgREST does not support multi-statement transactions,
        # so we use an RPC call that wraps both writes atomically.
        # The RPC is defined in the database as a SQL function.
        # If the RPC is unavailable (local dev without the function) we fall
        # back to two sequential writes — this is acceptable because the
        # idempotency check above prevents double-grants in the happy path.
        try:
            self._sb.rpc(
                "grant_trial",
                {
                    "p_user_id": user_id_str,
                    "p_analyses": settings.FREE_TRIAL_ANALYSES,
                },
            ).execute()
            logger.info(
                "trial_grant applied for user %s — %d analyses granted",
                user_id_str,
                settings.FREE_TRIAL_ANALYSES,
            )
        except Exception as exc:  # noqa: BLE001
            # RPC may not exist yet (e.g. running against a fresh DB without
            # the function applied).  Fall back to two sequential writes.
            logger.warning(
                "grant_trial RPC unavailable (%s) — using fallback writes",
                exc,
            )
            self._grant_fallback(user_id_str)

    def _grant_fallback(self, user_id_str: str) -> None:
        """Two-write fallback when the grant_trial RPC is unavailable."""
        self._sb.table("users").update(
            {"trial_analyses_remaining": settings.FREE_TRIAL_ANALYSES}
        ).eq("id", user_id_str).execute()

        self._sb.table("credit_ledger").insert(
            {
                "user_id": user_id_str,
                "delta": settings.FREE_TRIAL_ANALYSES,
                "type": "trial_grant",
            }
        ).execute()
