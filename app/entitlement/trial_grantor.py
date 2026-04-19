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
from app.utils.db_errors import is_unique_violation

logger = logging.getLogger(__name__)


class TrialGrantor:
    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    def grant(self, user_id: UUID) -> None:
        """Grant free trial analyses atomically and idempotently."""
        user_id_str = str(user_id)

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
        except Exception as exc:
            # Idempotency: unique_violation means the trial was already
            # granted (another concurrent call or a retry). Centralised
            # detection lives in ``app.utils.db_errors`` so drift between
            # Supabase/PostgREST/psycopg wrapper versions is a one-file fix.
            if is_unique_violation(exc):
                logger.info(
                    "trial_grant already applied for user %s — skipping", user_id_str
                )
                return

            logger.error("grant_trial RPC failed for user %s: %s", user_id_str, exc)
            raise RuntimeError(f"Failed to grant trial for user {user_id_str}") from exc
