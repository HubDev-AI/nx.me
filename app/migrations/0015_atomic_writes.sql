-- 0015_atomic_writes.sql
-- Atomic RPCs replacing multi-step writes that can leave inconsistent state.
-- All SECURITY DEFINER to bypass RLS.

-- UP

-- 1. insert_comment_atomic: INSERT comment + increment count in one transaction
CREATE OR REPLACE FUNCTION public.insert_comment_atomic(
  p_post_id UUID,
  p_user_id UUID,
  p_content TEXT
)
RETURNS SETOF comments
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_comment_id UUID := gen_random_uuid();
BEGIN
  INSERT INTO comments (id, post_id, user_id, content, created_at)
  VALUES (v_comment_id, p_post_id, p_user_id, p_content, now());

  UPDATE posts
  SET comment_count = comment_count + 1, updated_at = now()
  WHERE id = p_post_id;

  RETURN QUERY SELECT * FROM comments WHERE id = v_comment_id;
END;
$$;

-- 2. persist_reaction_atomic: INSERT reaction + increment count in one transaction
--    Returns empty set on duplicate (UNIQUE violation) so caller knows to undo Redis INCR.
--    Depends on: increment_reaction_count (defined in migration 0011)
CREATE OR REPLACE FUNCTION public.persist_reaction_atomic(
  p_post_id UUID,
  p_user_id UUID DEFAULT NULL,
  p_guest_session_token TEXT DEFAULT NULL
)
RETURNS SETOF reactions
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  INSERT INTO reactions (id, post_id, user_id, guest_session_token, created_at)
  VALUES (gen_random_uuid(), p_post_id, p_user_id, p_guest_session_token, now());

  -- Only increment if INSERT succeeded (no exception)
  PERFORM increment_reaction_count(p_post_id);

  RETURN QUERY
    SELECT * FROM reactions
    WHERE post_id = p_post_id
      AND (
        (p_user_id IS NOT NULL AND user_id = p_user_id) OR
        (p_guest_session_token IS NOT NULL AND guest_session_token = p_guest_session_token)
      )
    ORDER BY created_at DESC LIMIT 1;

EXCEPTION
  WHEN unique_violation THEN
    -- Duplicate reaction — return empty set (caller decrements Redis)
    RETURN;
END;
$$;

-- 3. handle_checkout_credit_atomic: INSERT ledger + conditional tier upgrade
CREATE OR REPLACE FUNCTION public.handle_checkout_credit_atomic(
  p_user_id UUID,
  p_credits INTEGER,
  p_event_id TEXT,
  p_trial_tier_id UUID,
  p_credit_holder_tier_id UUID
)
RETURNS TABLE(tier_upgraded BOOLEAN)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_current_tier_id UUID;
  v_upgraded BOOLEAN := FALSE;
BEGIN
  -- Insert credit purchase into ledger
  INSERT INTO credit_ledger (id, user_id, delta, type, note, created_at)
  VALUES (gen_random_uuid(), p_user_id, p_credits, 'purchase', 'Stripe event ' || p_event_id, now());

  -- Check current tier
  SELECT tier_id INTO v_current_tier_id
  FROM users WHERE id = p_user_id;

  -- Upgrade from trial to credit_holder if needed
  IF v_current_tier_id = p_trial_tier_id THEN
    UPDATE users
    SET tier_id = p_credit_holder_tier_id,
        updated_at = now()
    WHERE id = p_user_id;
    v_upgraded := TRUE;
  END IF;

  RETURN QUERY SELECT v_upgraded;
END;
$$;


-- DOWN

DROP FUNCTION IF EXISTS public.insert_comment_atomic(UUID, UUID, TEXT);
DROP FUNCTION IF EXISTS public.persist_reaction_atomic(UUID, UUID, TEXT);
DROP FUNCTION IF EXISTS public.handle_checkout_credit_atomic(UUID, INTEGER, TEXT, UUID, UUID);
