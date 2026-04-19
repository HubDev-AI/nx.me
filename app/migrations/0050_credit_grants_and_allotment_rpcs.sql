-- 0050_credit_grants_and_allotment_rpcs.sql
--
-- Credits-only engine: grant + allotment + pack + dispute-compensation
-- + guest-merge RPCs. Six RPCs, all SECURITY DEFINER, all
-- advisory-lock'd via hashtextextended(user_id::text, 0).
--
-- Assumes the schema landed by Unit 1 (migration 0048) already extended
-- `credit_ledger.type` to include the new type strings used here:
--   'monthly_allotment', 'signup_grant', 'signup_grant_suppressed_by_fingerprint',
--   'weekly_free_grant', 'credit_pack_purchase', 'dispute_compensation',
--   'guest_merge_non_pack', 'guest_merge_truncated'.
-- And that Unit 1 added:
--   plan_versions(id, version_num, monthly_allotment_milli, glowup_cost_milli, ...)
--   users.guest_install_uuid_hash BYTEA NULL
--   users.merged_into_user_id UUID NULL (ON DELETE SET NULL)
--   users.merged_at TIMESTAMPTZ NULL
-- And Unit 1b (0052) seeded `signup_grants_issued` (deterministic_hash PK).
--
-- Pattern references:
--   0014_credit_ledger_rpcs.sql        — RPC shape.
--   0019_credit_reserve_advisory_lock  — hashtext lock domain.
--   0021_security_definer_search_path  — SET search_path = public.
--   docs/solutions/best-practices/enumerate-before-cascade-with-cas-2026-04-19.md
--                                      — CAS discipline on idempotent writes.

-- UP

-- uuid-ossp provides uuid_generate_v5 + uuid_ns_url; pgcrypto's
-- gen_random_uuid is orthogonal and already in use elsewhere.
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- -------------------------------------------------------------------------
-- Schema extensions required by these RPCs.
--
-- * credit_ledger.metadata — audit payload carrier (discarded_milli on
--   monthly_allotment; truncated_milli on guest_merge_truncated).
-- * partial UNIQUE on reference_id WHERE type='weekly_free_grant' — the
--   dedup handle for credit_apply_weekly_free_grant_v2. Scoped to this
--   single type so other types that already reuse reference_id (e.g. the
--   per-reservation reserve/release/commit trio) continue to work.
-- -------------------------------------------------------------------------
ALTER TABLE credit_ledger
    ADD COLUMN IF NOT EXISTS metadata JSONB;

CREATE UNIQUE INDEX IF NOT EXISTS idx_credit_ledger_weekly_ref
    ON credit_ledger (reference_id)
    WHERE type = 'weekly_free_grant';

-- Pack + dispute-compensation dedup handles. Anchors the ON CONFLICT clauses
-- in `credit_apply_pack_purchase_v2` and `credit_dispute_compensate_v2` so a
-- caller that replays the same uuid5 reference for the same type silently
-- no-ops (belt-and-braces on top of the primary `processed_webhook_events`
-- dedup).
CREATE UNIQUE INDEX IF NOT EXISTS idx_credit_ledger_pack_ref
    ON credit_ledger (reference_id)
    WHERE type = 'credit_pack_purchase';

CREATE UNIQUE INDEX IF NOT EXISTS idx_credit_ledger_dispute_ref
    ON credit_ledger (reference_id)
    WHERE type = 'dispute_compensation';

-- Supports `SUM(delta) WHERE user_id = $1 AND type NOT IN (...)` in
-- `credit_reserve_v2` (0049) and `credit_apply_monthly_allotment_v2` below —
-- enables an index-only scan instead of a full table scan per reserve call.
CREATE INDEX IF NOT EXISTS idx_credit_ledger_user_type_delta
    ON credit_ledger (user_id, type) INCLUDE (delta);

-- =========================================================================
-- 1. credit_apply_monthly_allotment_v2
--    REPLACE semantics (R11): single ledger entry with metadata payload
--    capturing the discarded non-pack balance. Excludes pack credits
--    (so paid packs survive renewal) AND excludes in-flight reserve/commit
--    markers (so a mid-flight reservation cannot be REPLACE'd away, and a
--    subsequent release doesn't double-credit into the new allotment).
-- =========================================================================
CREATE OR REPLACE FUNCTION public.credit_apply_monthly_allotment_v2(
    p_user_id         UUID,
    p_plan_version_id UUID
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_current_non_pack_balance INTEGER;
    v_allotment                INTEGER;
BEGIN
    -- SEC-001: enforce RLS-equivalent scoping. Service-role bypasses (so the
    -- subscription-renewal worker can drive this); any other authenticated
    -- caller must match `auth.uid()`. Bare `auth.role() IS NULL` paths
    -- (e.g. direct migrator shell) also bypass — no auth context attached.
    IF auth.role() IS NOT NULL
       AND auth.role() != 'service_role'
       AND auth.uid() IS DISTINCT FROM p_user_id THEN
        RAISE EXCEPTION 'forbidden' USING ERRCODE = '42501';
    END IF;

    -- Single-user advisory lock (hashtextextended domain from Unit 2).
    PERFORM pg_advisory_xact_lock(hashtextextended(p_user_id::text, 0));

    -- Non-pack balance excludes pack credits (preserved across REPLACE)
    -- and in-flight reserve/commit markers (adversarial race fix — a
    -- reserve that lands after SUM runs would otherwise be wiped by the
    -- REPLACE delta, and a subsequent release would credit against the
    -- fresh allotment rather than the user's original hold).
    SELECT COALESCE(SUM(delta), 0)
      INTO v_current_non_pack_balance
      FROM credit_ledger
     WHERE user_id = p_user_id
       AND type NOT IN ('credit_pack_purchase', 'reserve', 'commit');

    SELECT monthly_allotment_milli
      INTO v_allotment
      FROM plan_versions
     WHERE id = p_plan_version_id;

    IF v_allotment IS NULL THEN
        RAISE EXCEPTION 'plan_version_not_found: %', p_plan_version_id
            USING ERRCODE = 'P0001';
    END IF;

    INSERT INTO credit_ledger (user_id, delta, type, reference_id, metadata)
    VALUES (
        p_user_id,
        v_allotment - v_current_non_pack_balance,
        'monthly_allotment',
        p_plan_version_id,
        jsonb_build_object(
            'discarded_milli',  v_current_non_pack_balance,
            'plan_version_id',  p_plan_version_id
        )
    );
END;
$$;

-- =========================================================================
-- 2. credit_apply_signup_grant_v2
--    One-time fingerprint-bound signup grant (R6a). NULL hash/salt args =
--    web signup, no fingerprint enforcement (documented residual risk).
-- =========================================================================
CREATE OR REPLACE FUNCTION public.credit_apply_signup_grant_v2(
    p_user_id             UUID,
    p_deterministic_hash  BYTEA,
    p_protected_hash      BYTEA,
    p_salt                BYTEA,
    p_signup_grant_milli  INT
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_exists BOOLEAN;
BEGIN
    -- SEC-001: non-service-role callers must match `auth.uid()`.
    IF auth.role() IS NOT NULL
       AND auth.role() != 'service_role'
       AND auth.uid() IS DISTINCT FROM p_user_id THEN
        RAISE EXCEPTION 'forbidden' USING ERRCODE = '42501';
    END IF;

    -- Reject inconsistent fingerprint arg combinations. Web signups pass
    -- all-NULL; mobile signups pass all-present. Anything else is a caller
    -- bug — fail fast rather than silently treat a partial fingerprint as
    -- a web signup and skip the dedup registry.
    IF (p_deterministic_hash IS NULL) <> (p_protected_hash IS NULL)
       OR (p_deterministic_hash IS NULL) <> (p_salt IS NULL) THEN
        RAISE EXCEPTION 'invalid_fingerprint_args' USING ERRCODE = 'P0001';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended(p_user_id::text, 0));

    -- Web signup (no install-UUID header): grant unconditionally, no
    -- registry row. The fingerprint table only carries mobile devices.
    IF p_deterministic_hash IS NULL
       AND p_protected_hash IS NULL
       AND p_salt IS NULL THEN
        INSERT INTO credit_ledger (user_id, delta, type)
        VALUES (p_user_id, p_signup_grant_milli, 'signup_grant');
        RETURN;
    END IF;

    -- Mobile signup: consult fingerprint registry.
    SELECT EXISTS (
        SELECT 1
          FROM signup_grants_issued
         WHERE deterministic_hash = p_deterministic_hash
    ) INTO v_exists;

    IF v_exists THEN
        -- Audit-only: preserve the attempt in the ledger with delta=0 so
        -- ops/analytics can tell abuse-suppression from "user never tried".
        INSERT INTO credit_ledger (user_id, delta, type)
        VALUES (p_user_id, 0, 'signup_grant_suppressed_by_fingerprint');
        RETURN;
    END IF;

    INSERT INTO signup_grants_issued (deterministic_hash, protected_hash, salt)
    VALUES (p_deterministic_hash, p_protected_hash, p_salt);

    INSERT INTO credit_ledger (user_id, delta, type)
    VALUES (p_user_id, p_signup_grant_milli, 'signup_grant');
END;
$$;

-- =========================================================================
-- 3. credit_apply_weekly_free_grant_v2
--    ISO-week scheduled grant (R6). Idempotent per (user, iso_week) via a
--    deterministic uuid5 reference + partial UNIQUE on reference_id.
-- =========================================================================
CREATE OR REPLACE FUNCTION public.credit_apply_weekly_free_grant_v2(
    p_user_id            UUID,
    p_iso_week           TEXT,
    p_weekly_grant_milli INT
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_dedup_ref UUID;
BEGIN
    -- SEC-001: non-service-role callers must match `auth.uid()`.
    IF auth.role() IS NOT NULL
       AND auth.role() != 'service_role'
       AND auth.uid() IS DISTINCT FROM p_user_id THEN
        RAISE EXCEPTION 'forbidden' USING ERRCODE = '42501';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended(p_user_id::text, 0));

    v_dedup_ref := extensions.uuid_generate_v5(
        extensions.uuid_ns_url(),
        'weekly:' || p_user_id::text || ':' || p_iso_week
    );

    -- Partial UNIQUE on reference_id WHERE type='weekly_free_grant'
    -- anchors the ON CONFLICT clause — second call for same
    -- (user, iso_week) is a silent no-op.
    INSERT INTO credit_ledger (user_id, delta, type, reference_id)
    VALUES (p_user_id, p_weekly_grant_milli, 'weekly_free_grant', v_dedup_ref)
    ON CONFLICT (reference_id) WHERE type = 'weekly_free_grant' DO NOTHING;
END;
$$;

-- =========================================================================
-- 4. credit_apply_pack_purchase_v2
--    Pack grant driven by a Stripe webhook. Primary dedup lives outside
--    this RPC in processed_webhook_events; the uuid5 reference_id + ON
--    CONFLICT DO NOTHING is belt-and-braces.
-- =========================================================================
CREATE OR REPLACE FUNCTION public.credit_apply_pack_purchase_v2(
    p_user_id       UUID,
    p_event_id      TEXT,
    p_credits_milli INT
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_pack_ref UUID;
BEGIN
    -- SEC-001: non-service-role callers must match `auth.uid()`. The
    -- webhook handler invokes this under the service-role key; clients
    -- calling the RPC directly are rejected.
    IF auth.role() IS NOT NULL
       AND auth.role() != 'service_role'
       AND auth.uid() IS DISTINCT FROM p_user_id THEN
        RAISE EXCEPTION 'forbidden' USING ERRCODE = '42501';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended(p_user_id::text, 0));

    v_pack_ref := extensions.uuid_generate_v5(
        extensions.uuid_ns_url(),
        'pack:' || p_event_id
    );

    -- Partial UNIQUE index `idx_credit_ledger_pack_ref` anchors this
    -- ON CONFLICT clause — second call for the same event_id silently
    -- no-ops. Outer `processed_webhook_events` dedup is the primary
    -- guard; this is belt-and-braces.
    INSERT INTO credit_ledger (user_id, delta, type, reference_id)
    VALUES (p_user_id, p_credits_milli, 'credit_pack_purchase', v_pack_ref)
    ON CONFLICT (reference_id) WHERE type = 'credit_pack_purchase' DO NOTHING;
END;
$$;

-- =========================================================================
-- 5. credit_dispute_compensate_v2
--    Negative compensating entry keyed to a Stripe charge_id (R-Dispute-3).
--    Negative balance is acceptable here per R-Dispute-3; outer dispute
--    state machine keeps the account locked.
-- =========================================================================
CREATE OR REPLACE FUNCTION public.credit_dispute_compensate_v2(
    p_user_id      UUID,
    p_charge_id    TEXT,
    p_amount_milli INT
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_comp_ref UUID;
BEGIN
    -- SEC-001: non-service-role callers must match `auth.uid()`. Normally
    -- invoked under service-role by the dispute webhook handler.
    IF auth.role() IS NOT NULL
       AND auth.role() != 'service_role'
       AND auth.uid() IS DISTINCT FROM p_user_id THEN
        RAISE EXCEPTION 'forbidden' USING ERRCODE = '42501';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended(p_user_id::text, 0));

    v_comp_ref := extensions.uuid_generate_v5(
        extensions.uuid_ns_url(),
        'dispute:' || p_charge_id
    );

    -- Partial UNIQUE index `idx_credit_ledger_dispute_ref` anchors the
    -- ON CONFLICT — repeat charge_id delivery is a no-op.
    INSERT INTO credit_ledger (user_id, delta, type, reference_id)
    VALUES (p_user_id, -p_amount_milli, 'dispute_compensation', v_comp_ref)
    ON CONFLICT (reference_id) WHERE type = 'dispute_compensation' DO NOTHING;
END;
$$;

-- =========================================================================
-- 6. merge_guest_ledger_v2
--    Atomic guest → authenticated-user merge (R16). Install-UUID binding
--    prevents pack drain via guest-token theft. 2× signup-grant cap on
--    non-pack; pack credits transfer whole.
--
--    Returns JSON for the HTTP layer so the mobile client can surface
--    any truncated amount to the user.
-- =========================================================================
CREATE OR REPLACE FUNCTION public.merge_guest_ledger_v2(
    p_guest_user_id      UUID,
    p_new_user_id        UUID,
    p_signup_grant_milli INT,
    p_install_uuid_hash  BYTEA
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_stored_hash       BYTEA;
    v_merged_at         TIMESTAMPTZ;
    v_non_pack_balance  INTEGER;
    v_pack_balance      INTEGER;
    v_transfer_non_pack INTEGER;
    v_truncated         INTEGER;
    v_pack_ref          UUID;
BEGIN
    -- SEC-001: the merge destination is `p_new_user_id` (where credits
    -- land). Non-service-role callers must match it — a mobile client
    -- authenticates as the NEW user to claim its guest balance. Bogus
    -- callers that try to merge somebody else's guest row into their own
    -- account still hit the install-UUID binding below, but we reject
    -- the cross-user case early as well.
    IF auth.role() IS NOT NULL
       AND auth.role() != 'service_role'
       AND auth.uid() IS DISTINCT FROM p_new_user_id THEN
        RAISE EXCEPTION 'forbidden' USING ERRCODE = '42501';
    END IF;

    -- Advisory locks on BOTH user_ids in UUID order (lexicographic via
    -- ::text cast) so two concurrent merges never deadlock on opposite
    -- lock orders.
    IF p_guest_user_id::text < p_new_user_id::text THEN
        PERFORM pg_advisory_xact_lock(hashtextextended(p_guest_user_id::text, 0));
        PERFORM pg_advisory_xact_lock(hashtextextended(p_new_user_id::text,   0));
    ELSE
        PERFORM pg_advisory_xact_lock(hashtextextended(p_new_user_id::text,   0));
        PERFORM pg_advisory_xact_lock(hashtextextended(p_guest_user_id::text, 0));
    END IF;

    -- Install-UUID binding: mismatch is a theft attempt.
    -- Pre-rollout guests have v_stored_hash IS NULL and tolerate any
    -- caller-provided hash (documented residual risk).
    SELECT guest_install_uuid_hash, merged_at
      INTO v_stored_hash, v_merged_at
      FROM users
     WHERE id = p_guest_user_id;

    IF v_stored_hash IS NOT NULL
       AND (p_install_uuid_hash IS NULL OR p_install_uuid_hash <> v_stored_hash) THEN
        RAISE EXCEPTION 'install_uuid_mismatch'
            USING ERRCODE = 'P0001';
    END IF;

    IF v_merged_at IS NOT NULL THEN
        RAISE EXCEPTION 'already_merged'
            USING ERRCODE = 'P0001';
    END IF;

    -- Non-pack balance excludes pack credits AND reserve/commit markers
    -- (mirror of monthly_allotment logic: defensive even though a guest
    -- shouldn't have in-flight reservations at merge time). Combined into
    -- a single scan via conditional SUMs to halve the lock hold time.
    SELECT
        COALESCE(SUM(CASE WHEN type = 'credit_pack_purchase' THEN delta ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN type NOT IN ('credit_pack_purchase', 'reserve', 'commit') THEN delta ELSE 0 END), 0)
      INTO v_pack_balance, v_non_pack_balance
      FROM credit_ledger
     WHERE user_id = p_guest_user_id;

    v_transfer_non_pack := LEAST(v_non_pack_balance, 2 * p_signup_grant_milli);
    v_truncated         := v_non_pack_balance - v_transfer_non_pack;

    INSERT INTO credit_ledger (user_id, delta, type)
    VALUES (p_new_user_id, v_transfer_non_pack, 'guest_merge_non_pack');

    -- Skip the pack INSERT on a zero-pack merge: the uuid5
    -- `guest_merge:<guest_id>` reference_id is one-shot per guest, and a
    -- zero-delta row would burn it for no accounting benefit.
    IF v_pack_balance > 0 THEN
        v_pack_ref := extensions.uuid_generate_v5(
            extensions.uuid_ns_url(),
            'guest_merge:' || p_guest_user_id::text
        );

        INSERT INTO credit_ledger (user_id, delta, type, reference_id)
        VALUES (
            p_new_user_id,
            v_pack_balance,
            'credit_pack_purchase',
            v_pack_ref
        );
    END IF;

    IF v_truncated > 0 THEN
        INSERT INTO credit_ledger (user_id, delta, type, metadata)
        VALUES (
            p_new_user_id,
            0,
            'guest_merge_truncated',
            jsonb_build_object('truncated_milli', v_truncated)
        );
    END IF;

    UPDATE users
       SET merged_into_user_id = p_new_user_id,
           merged_at           = now()
     WHERE id = p_guest_user_id;

    RETURN jsonb_build_object(
        'transferred_non_pack', v_transfer_non_pack,
        'transferred_pack',     v_pack_balance,
        'truncated_milli',      v_truncated
    );
END;
$$;


-- SEC-001 belt-and-braces: explicitly revoke direct RPC execute from
-- anon + authenticated. The in-function `auth.uid()` guards are the
-- primary defence; these REVOKEs stop a caller from reaching the
-- function body at all. service_role bypasses via SECURITY DEFINER
-- ownership, so no REVOKE is applied there.
REVOKE EXECUTE ON FUNCTION public.credit_apply_monthly_allotment_v2(UUID, UUID)
    FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.credit_apply_signup_grant_v2(UUID, BYTEA, BYTEA, BYTEA, INT)
    FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.credit_apply_weekly_free_grant_v2(UUID, TEXT, INT)
    FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.credit_apply_pack_purchase_v2(UUID, TEXT, INT)
    FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.credit_dispute_compensate_v2(UUID, TEXT, INT)
    FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.merge_guest_ledger_v2(UUID, UUID, INT, BYTEA)
    FROM PUBLIC, anon, authenticated;


-- DOWN:
--
-- Note: `ALTER TABLE credit_ledger ADD COLUMN metadata` is intentionally
-- NOT reverted (pre-launch destructive-OK policy — the column is cheap
-- to carry forward, and dropping it would risk downstream references).
-- The partial UNIQUE index is also left in place for the same reason.

DROP FUNCTION IF EXISTS public.merge_guest_ledger_v2(UUID, UUID, INT, BYTEA);
DROP FUNCTION IF EXISTS public.credit_dispute_compensate_v2(UUID, TEXT, INT);
DROP FUNCTION IF EXISTS public.credit_apply_pack_purchase_v2(UUID, TEXT, INT);
DROP FUNCTION IF EXISTS public.credit_apply_weekly_free_grant_v2(UUID, TEXT, INT);
DROP FUNCTION IF EXISTS public.credit_apply_signup_grant_v2(UUID, BYTEA, BYTEA, BYTEA, INT);
DROP FUNCTION IF EXISTS public.credit_apply_monthly_allotment_v2(UUID, UUID);
