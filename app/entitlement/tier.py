from __future__ import annotations

from supabase import Client

from app.repositories.subscription_repo import SubscriptionRepository


def has_active_pro(user_id: str, supabase: Client) -> bool:
    """Return True if the user has an active or trialing Pro subscription."""
    repo = SubscriptionRepository(supabase)
    return repo.get_active_subscription(user_id) is not None
