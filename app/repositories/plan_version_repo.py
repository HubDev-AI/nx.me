"""Plan-version repository — reads the immutable ``plan_versions`` table.

``plan_versions`` is seeded by migration 0048 with:

* ``v1_free_default`` — Free tier divisors (price=0, monthly=0,
  glowup_cost_milli=100, ada_cost_milli=5).
* ``v1_pro`` — active Pro cohort (price=999, monthly=3000, same divisors).

Rows are immutable once seeded (per R12: plan_versions freezes the full
{price, monthly_allotment_milli, glowup_cost_milli, ada_cost_milli} bundle
per cohort), so this repo caches the default-free id in-process per
instance. The cache is intentionally instance-level — a fresh repo is built
per request, and tests can get a clean cache by building a new instance.

Free users don't own a subscription row; R3 resolves divisors via the
``COALESCE(subscriptions.plan_version_id, <v1_free_default>)`` rule.
``get_active_version_for_user`` encodes that rule on the read path so
callers never have to duplicate the fallback.

Pattern mirrors ``app/repositories/subscription_repo.py``: sync Supabase,
constructor takes ``Client``, caller uses ``run_sync`` from async handlers.
"""

from __future__ import annotations

import logging
from uuid import UUID

from supabase import Client

logger = logging.getLogger(__name__)

# Seeded version_num identifiers (see migration 0048). Kept in Python so we
# don't sprinkle raw strings across services and ops scripts.
FREE_DEFAULT_VERSION_NUM = "v1_free_default"
PRO_VERSION_NUM = "v1_pro"


class PlanVersionRepository:
    """All reads against ``plan_versions`` + the subscription-to-plan lookup."""

    def __init__(self, supabase: Client) -> None:
        self._sb = supabase
        # Instance-level cache: avoids a per-request round trip to resolve
        # the Free-default id, without leaking across the process lifetime.
        # ``plan_versions`` rows are immutable once seeded, so caching the
        # id is safe. We never cache the full row — seed-time edits to
        # cost columns would poison the cache for the process.
        self._default_free_id: UUID | None = None

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_by_version_num(self, version_num: str) -> dict | None:
        """Return the ``plan_versions`` row for ``version_num``, or ``None``."""
        result = (
            self._sb.table("plan_versions")
            .select(
                "id, version_num, price_usd_cents, monthly_allotment_milli, "
                "glowup_cost_milli, ada_cost_milli, stripe_price_id"
            )
            .eq("version_num", version_num)
            .maybe_single()
            .execute()
        )
        if not result or not result.data:
            return None
        return result.data

    def get_default_free_id(self) -> UUID:
        """Return the id of the seeded ``v1_free_default`` row, cached.

        Raises ``RuntimeError`` if the seed row is missing — that is a DB
        corruption / migration regression (R12: seed is part of the
        immutable contract), not a runtime condition the caller can
        recover from.
        """
        if self._default_free_id is not None:
            return self._default_free_id
        row = self.get_by_version_num(FREE_DEFAULT_VERSION_NUM)
        if not row:
            raise RuntimeError(
                f"plan_versions seed row '{FREE_DEFAULT_VERSION_NUM}' is missing; "
                "migration 0048 did not seed correctly."
            )
        self._default_free_id = UUID(row["id"])
        return self._default_free_id

    def get_active_version_for_user(self, user_id: UUID) -> dict:
        """Return the plan_version row the user is currently billed against.

        Resolution order (R3):
          1. Active subscription row → follow its ``plan_version_id``.
          2. Otherwise → the seeded ``v1_free_default`` row.

        Always returns a row — Free users get the default. Raises
        ``RuntimeError`` only if the referenced ``plan_version_id`` row has
        been deleted (which 0048 prevents via FK, so this indicates DB
        corruption).
        """
        sub = (
            self._sb.table("subscriptions")
            .select("plan_version_id")
            .eq("user_id", str(user_id))
            .eq("status", "active")
            .limit(1)
            .execute()
        )
        plan_version_id: str | None = None
        if sub and sub.data:
            plan_version_id = sub.data[0].get("plan_version_id")

        if plan_version_id:
            row = (
                self._sb.table("plan_versions")
                .select(
                    "id, version_num, price_usd_cents, monthly_allotment_milli, "
                    "glowup_cost_milli, ada_cost_milli, stripe_price_id"
                )
                .eq("id", plan_version_id)
                .maybe_single()
                .execute()
            )
            if row and row.data:
                return row.data
            # Subscription pointed at a plan_version row that no longer exists.
            # With the FK from 0048 this should be impossible; if it happens,
            # surface it loudly rather than silently downgrading the user.
            raise RuntimeError(
                f"subscriptions.plan_version_id={plan_version_id} does not "
                "resolve to a plan_versions row (DB corruption or orphan)."
            )

        # No active subscription → Free default.
        free_row = self.get_by_version_num(FREE_DEFAULT_VERSION_NUM)
        if not free_row:
            raise RuntimeError(
                f"plan_versions seed row '{FREE_DEFAULT_VERSION_NUM}' is missing; "
                "migration 0048 did not seed correctly."
            )
        return free_row
