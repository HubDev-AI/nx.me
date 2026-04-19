-- 0054: Drop legacy payments — tiers + usage_events + trial_analyses_remaining + legacy credit RPCs.
-- Pre-launch destructive cleanup. Phase A landed parallel _v2 RPCs (renamed to no-suffix in R1);
-- this migration removes the legacy v1 path entirely.

-- 1) Drop legacy credit RPCs
-- credit_reserve: 2-arg (uuid, uuid) — original in 0014, overridden in 0019 (advisory lock version)
DROP FUNCTION IF EXISTS public.credit_reserve(uuid, uuid);
-- credit_release: 1-arg (uuid) — 0014
DROP FUNCTION IF EXISTS public.credit_release(uuid);
-- credit_commit: 1-arg (uuid) — 0014
DROP FUNCTION IF EXISTS public.credit_commit(uuid);
-- credit_refund: 1-arg (uuid) — 0029
DROP FUNCTION IF EXISTS public.credit_refund(uuid);
-- handle_checkout_credit_atomic: 5-arg — 0015 (tier-upgrade on checkout; replaced by ledger-only)
DROP FUNCTION IF EXISTS public.handle_checkout_credit_atomic(uuid, integer, text, uuid, uuid);

-- 2) Drop FKs blocking column drops
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_tier_id_fkey;

-- 3) Drop legacy columns from users
ALTER TABLE users DROP COLUMN IF EXISTS tier_id;
ALTER TABLE users DROP COLUMN IF EXISTS trial_analyses_remaining;

-- 4) Drop usage_events (legacy time-window enforcement; replaced by ledger-based)
DROP TABLE IF EXISTS usage_events CASCADE;

-- 5) Drop tiers table (replaced by plan_versions)
DROP TABLE IF EXISTS tiers CASCADE;

-- 6) Tighten subscriptions status check — drop past_due/expired (not in new model)
ALTER TABLE subscriptions DROP CONSTRAINT IF EXISTS subscriptions_status_check;
ALTER TABLE subscriptions ADD CONSTRAINT subscriptions_status_check
    CHECK (status IN ('active', 'cancelled', 'incomplete', 'trialing'));
