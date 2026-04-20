-- 0056_remove_guest_artifacts.sql
--
-- Pre-launch destructive removal of guest-mode DB surface.
-- Code-side guest endpoint, dep, and repo modules are deleted in the same PR.
--
-- Surface removed:
--   1. merge_guest_ledger() RPC (guest→user credit transfer).
--   2. credit_ledger.type enum narrows — drop 'guest_merge_non_pack' and
--      'guest_merge_truncated'.
--   3. users.is_guest column + its partial index.
--   4. users.guest_session_token column + its partial index.
--   5. users.guest_install_uuid_hash column (only reader was merge_guest_ledger).
--   6. reactions.guest_session_token column + its dual-identity CHECK + its
--      per-guest UNIQUE constraint.

-- 1) Drop merge RPC. Its signature reads `users.guest_install_uuid_hash`, so
--    this must come before the column drop. Signature is (UUID, UUID, INT, BYTEA)
--    per migration 0050 — the 3-arg drop previously here was a silent no-op that
--    left the function alive, blocking the guest_install_uuid_hash column drop.
DROP FUNCTION IF EXISTS public.merge_guest_ledger(UUID, UUID, INT, BYTEA);

-- 2) Narrow credit_ledger.type CHECK enum — drop guest_merge_* entries.
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
        -- Phase A credits-only engine (0048).
        'signup_grant',
        'signup_grant_suppressed_by_fingerprint',
        'weekly_free_grant',
        'monthly_allotment',
        'credit_pack_purchase',
        'ada_message',
        'dispute_compensation'
    ));

-- 3) Drop users guest columns + indexes.
DROP INDEX IF EXISTS idx_users_guest_token;
ALTER TABLE users DROP COLUMN IF EXISTS is_guest;
ALTER TABLE users DROP COLUMN IF EXISTS guest_session_token;
ALTER TABLE users DROP COLUMN IF EXISTS guest_install_uuid_hash;

-- 4) Drop persist_reaction_atomic RPC (0015) — its signature references the
--    guest_session_token column being dropped. Re-create without the guest
--    param so the reaction worker can persist JWT-authenticated reactions only.
DROP FUNCTION IF EXISTS public.persist_reaction_atomic(UUID, UUID, TEXT);

-- 5) Drop reactions guest column + its constraints.
-- The dual-identity CHECK ((user_id IS NOT NULL) <> (guest_session_token IS NOT NULL))
-- is implicitly dropped when its column goes; the UNIQUE index on
-- (post_id, guest_session_token) is also dropped.
ALTER TABLE reactions DROP CONSTRAINT IF EXISTS reactions_unique_guest;
ALTER TABLE reactions DROP COLUMN IF EXISTS guest_session_token;

-- After the column drop there are no rows where user_id is null (guest reactions
-- are gone). Enforce user_id NOT NULL so future rows must carry a real user.
ALTER TABLE reactions ALTER COLUMN user_id SET NOT NULL;

-- 6) Recreate persist_reaction_atomic with a user-only signature. The original
--    (0015) returned the existing reaction on UNIQUE violation via the guest
--    token fallback; with guests gone, user_id is the only identity and the
--    duplicate branch just returns an empty set.
CREATE OR REPLACE FUNCTION public.persist_reaction_atomic(
  p_post_id UUID,
  p_user_id UUID
)
RETURNS SETOF reactions
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  INSERT INTO reactions (id, post_id, user_id, created_at)
  VALUES (gen_random_uuid(), p_post_id, p_user_id, now());

  -- Only increment if INSERT succeeded (no exception)
  PERFORM increment_reaction_count(p_post_id);

  RETURN QUERY
    SELECT * FROM reactions
    WHERE post_id = p_post_id
      AND user_id = p_user_id
    ORDER BY created_at DESC LIMIT 1;

EXCEPTION
  WHEN unique_violation THEN
    -- Duplicate reaction — return empty set (caller decrements Redis)
    RETURN;
END;
$$;
