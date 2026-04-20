-- 0059_toggle_reaction.sql
-- Replace insert-only `persist_reaction_atomic` with `toggle_reaction_atomic`:
-- a second press from the same user unlikes the post. Pre-launch, so we drop
-- the old RPC outright instead of keeping a deprecation shim.

-- UP

DROP FUNCTION IF EXISTS public.persist_reaction_atomic(UUID, UUID);

CREATE OR REPLACE FUNCTION public.toggle_reaction_atomic(
  p_post_id UUID,
  p_user_id UUID
)
RETURNS TABLE (reaction_count INT, has_reacted BOOLEAN)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_deleted INT;
  v_count   INT;
  v_has     BOOLEAN;
BEGIN
  DELETE FROM reactions
  WHERE post_id = p_post_id
    AND user_id = p_user_id;
  GET DIAGNOSTICS v_deleted = ROW_COUNT;

  IF v_deleted > 0 THEN
    UPDATE posts
    SET reaction_count = GREATEST(reaction_count - 1, 0),
        updated_at     = now()
    WHERE id = p_post_id
    RETURNING posts.reaction_count INTO v_count;
    v_has := FALSE;
  ELSE
    BEGIN
      INSERT INTO reactions (id, post_id, user_id, created_at)
      VALUES (gen_random_uuid(), p_post_id, p_user_id, now());

      UPDATE posts
      SET reaction_count = reaction_count + 1,
          updated_at     = now()
      WHERE id = p_post_id
      RETURNING posts.reaction_count INTO v_count;
    EXCEPTION
      WHEN unique_violation THEN
        -- Concurrent toggle from the same user inserted first; the row
        -- already exists, so report the current post count as truth and
        -- avoid a double-increment.
        SELECT posts.reaction_count
          INTO v_count
          FROM posts
         WHERE id = p_post_id;
    END;
    v_has := TRUE;
  END IF;

  RETURN QUERY SELECT v_count, v_has;
END;
$$;

-- DOWN:
DROP FUNCTION IF EXISTS public.toggle_reaction_atomic(UUID, UUID);
