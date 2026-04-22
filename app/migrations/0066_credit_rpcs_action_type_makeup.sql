-- 0066_credit_rpcs_action_type_makeup.sql
-- Extends the credit_reserve action_type allowlist to include 'makeup'.
--
-- 0049 shipped credit_reserve with the guard:
--   IF p_action_type NOT IN ('glowup', 'ada_message') THEN
-- Path A (credit-based makeup) makes the debit a no-op for v1, but the
-- RPC must accept 'makeup' without raising unknown_action_type so the
-- Unit 5 worker can call it consistently. The CASE cost-resolution block
-- below maps 'makeup' to the same plan_versions cost column as 'glowup'
-- for now; this can be refined to a dedicated makeup_cost_milli column
-- in a later migration without touching callers.
--
-- Uses CREATE OR REPLACE — idempotent, no destructive DROP needed.

CREATE OR REPLACE FUNCTION public.credit_reserve(
  p_user_id UUID,
  p_reservation_id UUID,
  p_action_type TEXT
)
RETURNS SETOF credit_reservations
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_plan_version_id UUID;
  v_cost            INTEGER;
  v_balance         INTEGER;
  v_locked_at       TIMESTAMPTZ;
BEGIN
  IF p_action_type NOT IN ('glowup', 'ada_message', 'makeup') THEN
    RAISE EXCEPTION 'unknown_action_type: %', p_action_type
      USING ERRCODE = 'P0001';
  END IF;

  IF auth.role() IS NOT NULL
     AND auth.role() != 'service_role'
     AND auth.uid() IS DISTINCT FROM p_user_id THEN
    RAISE EXCEPTION 'forbidden' USING ERRCODE = '42501';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(p_user_id::text, 0));

  SELECT locked_at INTO v_locked_at FROM users WHERE id = p_user_id;
  IF v_locked_at IS NOT NULL THEN
    RAISE EXCEPTION 'account_locked' USING ERRCODE = 'P0001';
  END IF;

  SELECT s.plan_version_id INTO v_plan_version_id
  FROM subscriptions s
  WHERE s.user_id = p_user_id AND s.status = 'active'
  LIMIT 1;

  IF v_plan_version_id IS NULL THEN
    SELECT id INTO v_plan_version_id
    FROM plan_versions
    WHERE version_num = 'v1_free_default'
    LIMIT 1;
  END IF;

  IF v_plan_version_id IS NULL THEN
    RAISE EXCEPTION 'plan_version_unresolved' USING ERRCODE = 'P0001';
  END IF;

  SELECT
    CASE p_action_type
      WHEN 'glowup'      THEN pv.glowup_cost_milli
      WHEN 'makeup'      THEN pv.glowup_cost_milli  -- same cost as glowup for v1
      WHEN 'ada_message' THEN pv.ada_cost_milli
    END
  INTO v_cost
  FROM plan_versions pv
  WHERE pv.id = v_plan_version_id;

  IF v_cost IS NULL OR v_cost <= 0 THEN
    RAISE EXCEPTION 'cost_unresolved' USING ERRCODE = 'P0001';
  END IF;

  SELECT COALESCE(SUM(delta), 0) INTO v_balance
  FROM credit_ledger WHERE user_id = p_user_id;

  IF v_balance < v_cost THEN
    RAISE EXCEPTION 'insufficient_credits' USING ERRCODE = 'P0001';
  END IF;

  INSERT INTO credit_reservations (id, user_id, amount, status, created_at)
  VALUES (p_reservation_id, p_user_id, v_cost, 'reserved', now());

  INSERT INTO credit_ledger (id, user_id, delta, type, reference_id, created_at)
  VALUES (gen_random_uuid(), p_user_id, -v_cost, 'reserve', p_reservation_id, now());

  RETURN QUERY SELECT * FROM credit_reservations WHERE id = p_reservation_id;
END;
$$;
