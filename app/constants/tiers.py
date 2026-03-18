# Tier slug constants (AC-4)
# Used ONLY in: API response serialization, queue routing, admin scripts, seed references
# NEVER used in EntitlementService business logic conditionals

TRIAL: str = "TRIAL"
CREDIT_HOLDER: str = "CREDIT_HOLDER"
PREMIUM: str = "PREMIUM"

# Maps DB tier slug → public API tier identifier
SLUG_TO_TIER_NAME: dict[str, str] = {
    "free": TRIAL,
    "credits": CREDIT_HOLDER,
    "premium": PREMIUM,
}

# Fixed UUIDs matching 0004_seed_tiers.sql
# For tests and admin scripts only
TIER_ID_TRIAL: str = "a0000000-0000-0000-0000-000000000001"
TIER_ID_CREDIT_HOLDER: str = "a0000000-0000-0000-0000-000000000002"
TIER_ID_PREMIUM: str = "a0000000-0000-0000-0000-000000000003"
