-- 0004_seed_tiers.sql
-- Seeds the 3 initial tiers with fixed deterministic UUIDs.
-- Fixed UUIDs allow app/constants/tiers.py to reference them directly
-- in tests and admin scripts without DB lookups.
--
-- After seeding, sets tier_id NOT NULL on users (all existing users
-- are assigned to the free tier as the safe default).

INSERT INTO tiers (
    id,
    slug,
    display_name,
    is_default,
    is_active,
    generation_type,
    generation_limit,
    generation_period_seconds,
    advisor_nudges_type,
    advisor_nudges_limit,
    advisor_nudges_period_seconds,
    max_concurrent_generations,
    identity_similarity_threshold,
    feature_advisor_chat,
    feature_visual_comparison,
    credits_based
) VALUES
(
    'a0000000-0000-0000-0000-000000000001',
    'free',
    'Free',
    true,
    true,
    'daily',
    1,
    86400,
    'weekly',
    3,
    604800,
    1,
    0.800,
    false,
    false,
    false
),
(
    'a0000000-0000-0000-0000-000000000002',
    'credits',
    'Credits',
    false,
    true,
    'credits',
    NULL,
    NULL,
    'weekly',
    10,
    604800,
    2,
    0.750,
    false,
    true,
    true
),
(
    'a0000000-0000-0000-0000-000000000003',
    'premium',
    'Premium',
    false,
    true,
    'monthly',
    100,
    2592000,
    'unlimited',
    NULL,
    NULL,
    3,
    0.700,
    true,
    true,
    false
);

-- Assign all existing users to the free tier, then enforce NOT NULL.
UPDATE users SET tier_id = 'a0000000-0000-0000-0000-000000000001' WHERE tier_id IS NULL;
ALTER TABLE users ALTER COLUMN tier_id SET NOT NULL;

-- DOWN:

ALTER TABLE users ALTER COLUMN tier_id DROP NOT NULL;
DELETE FROM tiers WHERE id IN (
    'a0000000-0000-0000-0000-000000000001',
    'a0000000-0000-0000-0000-000000000002',
    'a0000000-0000-0000-0000-000000000003'
);
