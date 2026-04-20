-- 0061_weekly_grant_balance_gate.sql
-- Gate the weekly free-credit grant on current balance. Pre-existing
-- behaviour unconditionally inserted one grant per (user, iso_week) and
-- credits never expire, so a dormant free user could accumulate weeks of
-- grants and stockpile enough to generate many glow-ups at once. With
-- this change, the RPC only inserts when the user's current ledger
-- balance is below the supplied threshold (typically 1 glow-up's worth
-- of milli-credits).
--
-- The (user, iso_week) idempotency dedup is preserved — callers passing
-- the same iso_week twice in the same week still no-op.

-- UP

DROP FUNCTION IF EXISTS public.credit_apply_weekly_free_grant(UUID, TEXT, INT);

CREATE OR REPLACE FUNCTION public.credit_apply_weekly_free_grant(
    p_user_id            UUID,
    p_iso_week           TEXT,
    p_weekly_grant_milli INT,
    p_min_balance_milli  INT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_dedup_ref UUID;
    v_balance   INT;
    v_inserted  INT := 0;
BEGIN
    -- SEC-001: non-service-role callers must match `auth.uid()`.
    IF auth.role() IS NOT NULL
       AND auth.role() != 'service_role'
       AND auth.uid() IS DISTINCT FROM p_user_id THEN
        RAISE EXCEPTION 'forbidden' USING ERRCODE = '42501';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended(p_user_id::text, 0));

    -- Balance gate. Ledger is append-only and credits never expire, so a
    -- dormant free user would otherwise stack a week's grant indefinitely.
    -- Skipping when the user already holds at least one action's worth of
    -- credits caps stockpiling at one grant.
    SELECT COALESCE(SUM(delta), 0)
      INTO v_balance
      FROM credit_ledger
     WHERE user_id = p_user_id;

    IF v_balance >= p_min_balance_milli THEN
        RETURN FALSE;
    END IF;

    v_dedup_ref := extensions.uuid_generate_v5(
        extensions.uuid_ns_url(),
        'weekly:' || p_user_id::text || ':' || p_iso_week
    );

    -- Partial UNIQUE on reference_id WHERE type='weekly_free_grant'
    -- anchors the ON CONFLICT clause — second call for same
    -- (user, iso_week) is a silent no-op even when the balance check
    -- passes on a retry.
    INSERT INTO credit_ledger (user_id, delta, type, reference_id)
    VALUES (p_user_id, p_weekly_grant_milli, 'weekly_free_grant', v_dedup_ref)
    ON CONFLICT (reference_id) WHERE type = 'weekly_free_grant' DO NOTHING;

    GET DIAGNOSTICS v_inserted = ROW_COUNT;
    RETURN v_inserted > 0;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.credit_apply_weekly_free_grant(
    UUID, TEXT, INT, INT
) FROM PUBLIC;

-- DOWN:
DROP FUNCTION IF EXISTS public.credit_apply_weekly_free_grant(UUID, TEXT, INT, INT);
