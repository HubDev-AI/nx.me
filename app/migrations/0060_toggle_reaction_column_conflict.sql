-- 0060_toggle_reaction_column_conflict.sql
-- Fix the 42702 "column reference reaction_count is ambiguous" crash shipped
-- in 0059. In PL/pgSQL a RETURNS TABLE column becomes an implicit variable,
-- so `UPDATE posts SET reaction_count = reaction_count + 1` couldn't tell
-- the table column from the OUT variable. Resolve by adding the
-- `#variable_conflict use_column` directive so column names always win
-- inside SQL statements; the OUT columns are still assigned via the final
-- RETURN QUERY.

-- UP

DROP FUNCTION IF EXISTS public.toggle_reaction_atomic(UUID, UUID);

CREATE OR REPLACE FUNCTION public.toggle_reaction_atomic(
  p_post_id UUID,
  p_user_id UUID
)
RETURNS TABLE (reaction_count INT, has_reacted BOOLEAN)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
#variable_conflict use_column
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
