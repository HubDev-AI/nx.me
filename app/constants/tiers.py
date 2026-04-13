"""Tier ID constants for runtime use.

Derived from the fixed UUIDs in app/config/tiers.py seed data.
These are stable across environments because the seed migration uses
deterministic UUIDs.
"""

# Tier IDs (must match SEED_TIERS in app/config/tiers.py)
TIER_ID_TRIAL = "a0000000-0000-0000-0000-000000000001"  # slug: free
TIER_ID_CREDIT_HOLDER = "a0000000-0000-0000-0000-000000000002"  # slug: credits
TIER_ID_PREMIUM = "a0000000-0000-0000-0000-000000000003"  # slug: premium

# Slug aliases used by generation.py queue routing
TRIAL = "free"
CREDIT_HOLDER = "credits"
PREMIUM = "premium"

# Slug → display name mapping (for API responses / UI)
SLUG_TO_TIER_NAME: dict[str, str] = {
    TRIAL: "Free",
    CREDIT_HOLDER: "Credits",
    PREMIUM: "Premium",
}

# Slug → DB enum value (must match glow_up_jobs_user_tier_at_enqueue_check constraint)
SLUG_TO_DB_TIER: dict[str, str] = {
    TRIAL: "TRIAL",
    CREDIT_HOLDER: "CREDIT_HOLDER",
    PREMIUM: "PREMIUM",
}
