-- 0054: Drop legacy payments — tiers + usage_events + trial_analyses_remaining + legacy credit RPCs.
-- Pre-launch destructive cleanup. Phase A landed parallel _v2 RPCs (renamed to no-suffix in R1);
-- this migration removes the legacy v1 path entirely.

-- 1) Drop legacy credit RPCs.
--
-- After the _v2-suffix refactor (commit 014a321), 0049 creates the canonical
-- credit_reserve/credit_commit/credit_release/credit_refund with no-suffix
-- names. The pre-refactor drops here clobbered those fresh creates on any
-- chain that runs 0049 → 0054 — a regression. Retained drops are limited to
-- signatures that 0049 does NOT create:
--   * credit_reserve 2-arg (0014 baseline, superseded by 0049's 3-arg).
--   * handle_checkout_credit_atomic 5-arg (0015 tier-upgrade, no replacement).
DROP FUNCTION IF EXISTS public.credit_reserve(uuid, uuid);
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
