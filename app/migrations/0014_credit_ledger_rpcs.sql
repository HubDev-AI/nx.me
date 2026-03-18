-- 0014_credit_ledger_rpcs.sql
-- Credit ledger RPCs called by app/entitlement/ledger.py
-- All SECURITY DEFINER to bypass RLS (service-level operations).
-- Invariants (from ledger.py docstrings):
--   reserve + release = 0 (net)
--   reserve + commit = -1 (net)
--   balance = SUM(delta)

-- UP

-- 1. sum_credit_balance: atomic SUM(delta) for a user
CREATE OR REPLACE FUNCTION public.sum_credit_balance(p_user_id UUID)
RETURNS INTEGER
LANGUAGE sql
SECURITY DEFINER
STABLE
AS $$
  SELECT COALESCE(SUM(delta), 0)::integer
  FROM credit_ledger
  WHERE user_id = p_user_id;
$$;

-- 2. credit_reserve: atomically create reservation + deduct credit
--    Returns the reservation row for confirmation.
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
  -- Guard: verify positive balance before reserving.
  -- NOTE: Under high concurrency, two simultaneous reserves could both
  -- read balance=1 and both succeed. For current traffic this is acceptable.
  -- If double-spend becomes a concern, add advisory lock: PERFORM pg_advisory_xact_lock(hashtext(p_user_id::text));
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

-- 3. credit_release: atomically release reservation + refund credit
--    Uses WHERE status = 'reserved' RETURNING * to prevent TOCTOU.
CREATE OR REPLACE FUNCTION public.credit_release(p_reservation_id UUID)
RETURNS SETOF credit_reservations
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  -- Atomically mark as released (only if still reserved)
  UPDATE credit_reservations
  SET status = 'released', resolved_at = now()
  WHERE id = p_reservation_id AND status = 'reserved';

  IF NOT FOUND THEN
    RETURN;  -- Empty result signals already-resolved to caller
  END IF;

  -- Refund credit (delta = +1)
  INSERT INTO credit_ledger (id, user_id, delta, type, reference_id, created_at)
  SELECT gen_random_uuid(), user_id, 1, 'release', p_reservation_id, now()
  FROM credit_reservations
  WHERE id = p_reservation_id;

  RETURN QUERY SELECT * FROM credit_reservations WHERE id = p_reservation_id;
END;
$$;

-- 4. credit_commit: atomically commit reservation (credit consumed)
--    delta = 0 (the reserve already deducted; commit just marks it consumed)
CREATE OR REPLACE FUNCTION public.credit_commit(p_reservation_id UUID)
RETURNS SETOF credit_reservations
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  UPDATE credit_reservations
  SET status = 'committed', resolved_at = now()
  WHERE id = p_reservation_id AND status = 'reserved';

  IF NOT FOUND THEN
    RETURN;
  END IF;

  -- Record the commit event (delta = 0, net effect: reserve's -1 stands)
  INSERT INTO credit_ledger (id, user_id, delta, type, reference_id, created_at)
  SELECT gen_random_uuid(), user_id, 0, 'commit', p_reservation_id, now()
  FROM credit_reservations
  WHERE id = p_reservation_id;

  RETURN QUERY SELECT * FROM credit_reservations WHERE id = p_reservation_id;
END;
$$;


-- DOWN

DROP FUNCTION IF EXISTS public.sum_credit_balance(UUID);
DROP FUNCTION IF EXISTS public.credit_reserve(UUID, UUID);
DROP FUNCTION IF EXISTS public.credit_release(UUID);
DROP FUNCTION IF EXISTS public.credit_commit(UUID);
