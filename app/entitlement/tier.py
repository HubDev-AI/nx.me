from __future__ import annotations

import hashlib

from supabase import Client

from app.repositories.subscription_repo import SubscriptionRepository


def _in_rollout_cohort(user_id: str, pct: int) -> bool:
    """Return True when user_id falls in the [0, pct) bucket.

    Uses MD5 of user_id for a stable, evenly-distributed hash. Monotonically
    inclusive: a user who is in-cohort at pct=10 stays in-cohort at pct=50.
    Boundary cases: pct ≤ 0 → False always; pct ≥ 100 → True always.
    """
    if pct <= 0:
        return False
    if pct >= 100:
        return True
    bucket = (
        int(hashlib.md5(user_id.encode(), usedforsecurity=False).hexdigest(), 16) % 100
    )
    return bucket < pct


def has_active_pro(user_id: str, supabase: Client) -> bool:
    """Return True if the user has an active or trialing Pro subscription."""
    repo = SubscriptionRepository(supabase)
    return repo.get_active_subscription(user_id) is not None


def has_makeup_access(user_id: str, supabase: Client) -> bool:
    """Pro subscription AND makeup rollout cohort membership.

    Composed from has_active_pro + _in_rollout_cohort so both checks are
    enforced at the entitlement layer. MAKEUP_ROLLOUT_PCT=0 (default) means
    no one gets access until the rollout is started via the runbook.
    """
    from app.config import settings

    if not has_active_pro(user_id, supabase):
        return False
    return _in_rollout_cohort(user_id, settings.MAKEUP_ROLLOUT_PCT)
