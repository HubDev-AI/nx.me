-- migration: 0055_dlq_mark_attempt_rpc
-- Atomic DLQ attempt increment.
--
-- Replaces the non-atomic SELECT-then-UPDATE pattern in
-- StripeCustomerDLQRepository.mark_attempt with a single UPDATE so concurrent
-- reconciler runs cannot lose increments.

CREATE OR REPLACE FUNCTION public.dlq_mark_attempt(
    p_customer_id TEXT,
    p_last_error  TEXT
) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    UPDATE stripe_customer_dlq
    SET attempts   = attempts + 1,
        last_error = p_last_error,
        updated_at = now()
    WHERE customer_id = p_customer_id;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.dlq_mark_attempt(TEXT, TEXT) FROM PUBLIC, anon, authenticated;
