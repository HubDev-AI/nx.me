-- 0029_credit_refund_rpc.sql
-- Add credit_refund RPC for refunding committed reservations.
-- Unlike credit_release (which only transitions reserved -> released),
-- credit_refund transitions committed -> released and adds +1 delta
-- to return the consumed credit to the user's balance.

-- UP

CREATE OR REPLACE FUNCTION public.credit_refund(p_reservation_id UUID)
RETURNS SETOF credit_reservations
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  -- Atomically mark as released (only if currently committed)
  UPDATE credit_reservations
  SET status = 'released', resolved_at = now()
  WHERE id = p_reservation_id AND status = 'committed';

  IF NOT FOUND THEN
    RETURN;  -- Empty result signals already-released or not-found to caller
  END IF;

  -- Refund credit (delta = +1)
  INSERT INTO credit_ledger (id, user_id, delta, type, reference_id, created_at)
  SELECT gen_random_uuid(), user_id, 1, 'refund', p_reservation_id, now()
  FROM credit_reservations
  WHERE id = p_reservation_id;

  RETURN QUERY SELECT * FROM credit_reservations WHERE id = p_reservation_id;
END;
$$;

-- DOWN:

DROP FUNCTION IF EXISTS public.credit_refund(UUID);
