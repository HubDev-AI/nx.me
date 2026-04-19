-- 0048_payments_schema_phase_a.sql
-- Payments & credits engine — Phase A schema additions (unit 1 of plan
-- docs/plans/2026-04-19-002-feat-payments-credits-only-engine-plan.md).
--
-- Additive-safe so it can interleave with the concurrent bug-fix agent
-- touching `app/api/entitlement.py`, `app/api/webhooks.py`, and
-- `app/entitlement/service.py`. No shared-trio file is edited as part of
-- this migration; no existing RPC is changed.
--
-- The migration runner (app/migrations/run.py) wraps every file in its
-- own transaction, so we do not add a redundant BEGIN/COMMIT here.
--
-- Scope (R7, R8, R12, R22, R23 Phase A):
--   1. New table `plan_versions` with RLS deny-all + seeded v1 rows.
--   2. Extend `users` with dispute / merge / lock / stripe / fingerprint cols.
--   3. Extend `subscriptions` with plan_version_id + grace_until + backfill.
--   4. Partial UNIQUE index enforcing one active subscription per user.
--   5. Partial BTREE index speeding up dispute-lock scans.
--   6. Extend `credit_ledger.type` CHECK enum with v2 entry types. The new
--      enum is a strict superset of the 0001 baseline; `retained_preserved`
--      is deliberately NOT added (single net-delta REPLACE instead).
--
-- `signup_grants_issued` is split out to 0052 because it carries a legal
-- gate; keeping it out of 0048 unblocks the rest of Phase A.

-- UP

-- 1. plan_versions — immutable, cohort-frozen pricing and costs.
--    price_usd_cents is INT so the $9.99 price round-trips without float
--    drift; NULL allowed only for non-paid plan versions (e.g. the
--    seeded `v1_free_default`). stripe_price_id is populated by the
--    `make stripe-dev` bootstrap in a later unit and stays NULL for the
--    free default.
CREATE TABLE plan_versions (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_num            TEXT UNIQUE NOT NULL,
    price_usd_cents        INT,
    monthly_allotment_milli INT,
    glowup_cost_milli      INT NOT NULL,
    ada_cost_milli         INT NOT NULL,
    stripe_price_id        TEXT NULL,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- RLS deny-all: only the service role (which bypasses RLS) reads/writes.
-- Mirrors the `username_reservations` treatment in 0044.
ALTER TABLE plan_versions ENABLE ROW LEVEL SECURITY;
CREATE POLICY plan_versions_deny_all ON plan_versions
    FOR ALL TO anon, authenticated
    USING (false) WITH CHECK (false);

-- 2. Seed v1 plan versions. Numbers per plan line 117:
--    v1_free_default: zero-cost default for unsubscribed users.
--    v1_pro: $9.99/mo, 3000 milli monthly allotment.
INSERT INTO plan_versions (
    version_num, price_usd_cents, monthly_allotment_milli,
    glowup_cost_milli, ada_cost_milli
) VALUES
    ('v1_free_default', 0,   0,    100, 5),
    ('v1_pro',          999, 3000, 100, 5);

-- 3. Extend users.
--    - locked_at: dispute-lock timestamp (NULL = unlocked).
--    - dispute_last_event_{id,at,status}: CAS state for out-of-order
--      dispute webhook events (security review CRITICAL fix).
--    - merged_into_user_id / merged_at: guest->auth merge audit; self-FK
--      SET NULL so deleting the survivor does not break audit rows.
--    - stripe_customer_id: lazily populated; UNIQUE so two user rows
--      cannot claim the same Stripe customer.
--    - guest_install_uuid_hash: mobile installation-UUID hash used to
--      match guest merges (security review HIGH fix).
ALTER TABLE users
    ADD COLUMN locked_at               TIMESTAMPTZ NULL,
    ADD COLUMN dispute_last_event_id   TEXT NULL,
    ADD COLUMN dispute_last_event_at   TIMESTAMPTZ NULL,
    ADD COLUMN dispute_last_status     TEXT NULL,
    ADD COLUMN merged_into_user_id     UUID NULL
        REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN merged_at               TIMESTAMPTZ NULL,
    ADD COLUMN stripe_customer_id      TEXT NULL UNIQUE,
    ADD COLUMN guest_install_uuid_hash BYTEA NULL;

-- 4. Extend subscriptions. plan_version_id points at the cohort-frozen
--    pricing row used at renewal; grace_until carries the 3-day window
--    set by `invoice.payment_failed` handlers (Phase B).
ALTER TABLE subscriptions
    ADD COLUMN plan_version_id UUID REFERENCES plan_versions(id),
    ADD COLUMN grace_until     TIMESTAMPTZ NULL;

-- Backfill any existing subscription rows to v1_pro. Pre-launch the
-- table is expected to be small-to-empty; statement is a no-op on a
-- fresh DB.
UPDATE subscriptions
   SET plan_version_id = (SELECT id FROM plan_versions WHERE version_num = 'v1_pro')
 WHERE plan_version_id IS NULL;

-- 5. Partial UNIQUE index: at most one row with status='active' per user
--    (R8). Matches the pattern in
--    docs/solutions/best-practices/partial-unique-index-for-republish-after-soft-delete-2026-04-19.md.
--    Note: 0001 already has a non-unique partial index `idx_subscriptions_user`
--    on the same predicate used for lookups; the new UNIQUE index is
--    additive and enforces the invariant.
CREATE UNIQUE INDEX idx_subscriptions_one_active_per_user
    ON subscriptions (user_id)
    WHERE status = 'active';

-- 6. Partial index speeding up dispute-lock scans — far fewer locked
--    rows than total users, so a partial index keeps this cheap.
CREATE INDEX idx_users_locked_at_not_null
    ON users (locked_at)
    WHERE locked_at IS NOT NULL;

-- 7. Extend credit_ledger.type CHECK enum. Baseline from 0001:106 is
--    ('trial_grant','purchase','reserve','commit','release','refund',
--     'adjustment'). Union with the Phase A v2 types listed in the plan
--    (excluding `retained_preserved` — single net-delta REPLACE stores
--    the discarded balance in metadata instead). DROP/ADD pattern per
--    0032.
ALTER TABLE credit_ledger
    DROP CONSTRAINT IF EXISTS credit_ledger_type_check;

ALTER TABLE credit_ledger
    ADD CONSTRAINT credit_ledger_type_check
    CHECK (type IN (
        -- Preserved from 0001 baseline.
        'trial_grant',
        'purchase',
        'reserve',
        'commit',
        'release',
        'refund',
        'adjustment',
        -- New in Phase A.
        'signup_grant',
        'signup_grant_suppressed_by_fingerprint',
        'weekly_free_grant',
        'monthly_allotment',
        'credit_pack_purchase',
        'ada_message',
        'dispute_compensation',
        'guest_merge_non_pack',
        'guest_merge_truncated'
    ));

-- DOWN:
-- Pre-launch, destructive schema refactor. Reverting this migration
-- would require deleting backfilled plan_version_id values, dropping
-- the partial UNIQUE index while any 'active' rows exist, reverting the
-- credit_ledger.type CHECK (which would reject any new-type rows the
-- v2 code already wrote), and removing the new users columns (with
-- the self-FK). Use `make nuke` + re-run migrations if you need to
-- start over locally.
DO $$
BEGIN
    RAISE EXCEPTION
        'migration 0048 is destructive and has no down path — use `make nuke` and re-run forward migrations';
END
$$;
