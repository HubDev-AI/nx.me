-- 0058_remove_credit_pack_artifacts.sql
--
-- Pre-launch destructive removal of the credit-pack SKU.
-- Pro subscription becomes the only paid SKU; pack SKU removed per the
-- 2026-04-20 brainstorm revision (R-Pack-Removal) and plan
-- docs/plans/2026-04-20-002-feat-payments-pack-removal-and-copy-rewrite-plan.md.
--
-- Surface removed:
--   1. credit_apply_pack_purchase() RPC.
--   2. idx_credit_ledger_pack_ref partial UNIQUE index.
--   3. 'credit_pack_purchase' value in the credit_ledger.type CHECK enum.
--
-- Pre-launch destructive policy: no backfill, no rename of existing rows
-- (none exist in production; dev DBs are reset). The migration will fail
-- loudly if any credit_ledger row still carries the dropped type.

-- 1) Drop the pack RPC.
DROP FUNCTION IF EXISTS public.credit_apply_pack_purchase(uuid, text, integer);

-- 2) Drop the pack-dedup partial UNIQUE index (from 0050).
DROP INDEX IF EXISTS public.idx_credit_ledger_pack_ref;

-- 3) Narrow credit_ledger.type CHECK enum — remove 'credit_pack_purchase'.
-- Retains every other type from 0056; keep this block in sync with the
-- canonical list in 0056_remove_guest_artifacts.sql.
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
        -- Credits-only engine.
        'signup_grant',
        'signup_grant_suppressed_by_fingerprint',
        'weekly_free_grant',
        'monthly_allotment',
        'ada_message',
        'dispute_compensation'
    ));

-- DOWN:

-- Recreate the pack-purchase RPC (body mirrors 0050 so a rollback restores
-- the exact pre-0058 behaviour).
CREATE OR REPLACE FUNCTION public.credit_apply_pack_purchase(
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

    INSERT INTO credit_ledger (user_id, delta, type, reference_id)
    VALUES (p_user_id, p_credits_milli, 'credit_pack_purchase', v_pack_ref)
    ON CONFLICT (reference_id) WHERE type = 'credit_pack_purchase' DO NOTHING;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.credit_apply_pack_purchase(UUID, TEXT, INT)
    FROM PUBLIC, anon, authenticated;

-- Restore the pack-dedup partial UNIQUE index.
CREATE UNIQUE INDEX IF NOT EXISTS idx_credit_ledger_pack_ref
    ON credit_ledger (reference_id)
    WHERE type = 'credit_pack_purchase';

-- Restore the 'credit_pack_purchase' enum value.
ALTER TABLE credit_ledger
    DROP CONSTRAINT IF EXISTS credit_ledger_type_check;

ALTER TABLE credit_ledger
    ADD CONSTRAINT credit_ledger_type_check
    CHECK (type IN (
        'trial_grant',
        'purchase',
        'reserve',
        'commit',
        'release',
        'refund',
        'adjustment',
        'signup_grant',
        'signup_grant_suppressed_by_fingerprint',
        'weekly_free_grant',
        'monthly_allotment',
        'credit_pack_purchase',
        'ada_message',
        'dispute_compensation'
    ));
