-- 0019_credit_reserve_advisory_lock.sql
-- H-5: Add advisory lock to credit_reserve to prevent double-spend under
-- concurrent requests for the same user.

-- UP

CREATE OR REPLACE FUNCTION public.credit_reserve(
  p_user_id UUID,
  p_reservation_id UUID
)
RETURNS SETOF credit_reservations
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_balance INTEGER;
BEGIN
  -- Advisory lock prevents concurrent reserves for same user (H-5)
  PERFORM pg_advisory_xact_lock(hashtext(p_user_id::text));

  -- Guard: verify positive balance before reserving.
  SELECT COALESCE(SUM(delta), 0) INTO v_balance
  FROM credit_ledger WHERE user_id = p_user_id;

  IF v_balance <= 0 THEN
    RAISE EXCEPTION 'insufficient_credits' USING ERRCODE = 'P0001';
  END IF;

  -- Insert reservation
  INSERT INTO credit_reservations (id, user_id, amount, status, created_at)
  VALUES (p_reservation_id, p_user_id, 1, 'reserved', now());

  -- Deduct credit (delta = -1)
  INSERT INTO credit_ledger (id, user_id, delta, type, reference_id, created_at)
  VALUES (gen_random_uuid(), p_user_id, -1, 'reserve', p_reservation_id, now());

  RETURN QUERY SELECT * FROM credit_reservations WHERE id = p_reservation_id;
END;
$$;


-- DOWN

CREATE OR REPLACE FUNCTION public.credit_reserve(
  p_user_id UUID,
  p_reservation_id UUID
)
RETURNS SETOF credit_reservations
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_balance INTEGER;
BEGIN
  SELECT COALESCE(SUM(delta), 0) INTO v_balance
  FROM credit_ledger WHERE user_id = p_user_id;

  IF v_balance <= 0 THEN
    RAISE EXCEPTION 'insufficient_credits' USING ERRCODE = 'P0001';
  END IF;

  INSERT INTO credit_reservations (id, user_id, amount, status, created_at)
  VALUES (p_reservation_id, p_user_id, 1, 'reserved', now());

  INSERT INTO credit_ledger (id, user_id, delta, type, reference_id, created_at)
  VALUES (gen_random_uuid(), p_user_id, -1, 'reserve', p_reservation_id, now());

  RETURN QUERY SELECT * FROM credit_reservations WHERE id = p_reservation_id;
END;
$$;
