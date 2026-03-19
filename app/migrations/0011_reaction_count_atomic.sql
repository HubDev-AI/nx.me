-- Atomic increment/decrement for posts.reaction_count to prevent race conditions.
-- Replaces the full-recount pattern in persist_reaction with O(1) updates.
-- Reconciliation replaced with a single bulk UPDATE statement.

CREATE OR REPLACE FUNCTION public.increment_reaction_count(p_post_id UUID)
RETURNS VOID
LANGUAGE sql
AS $$
  UPDATE posts
  SET reaction_count = reaction_count + 1,
      updated_at    = now()
  WHERE id = p_post_id;
$$;

CREATE OR REPLACE FUNCTION public.decrement_reaction_count(p_post_id UUID)
RETURNS VOID
LANGUAGE sql
AS $$
  UPDATE posts
  SET reaction_count = GREATEST(reaction_count - 1, 0),
      updated_at    = now()
  WHERE id = p_post_id;
$$;

-- Bulk reconciliation: single statement, no per-post loop.
-- Called via supabase.rpc('reconcile_reaction_counts', {'cutoff_iso': ...})
CREATE OR REPLACE FUNCTION public.reconcile_reaction_counts(cutoff_iso TIMESTAMPTZ)
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
  row_count INT;
BEGIN
  WITH actual AS (
    SELECT post_id, COUNT(*) AS cnt
    FROM reactions
    WHERE post_id IN (
      SELECT DISTINCT post_id FROM reactions WHERE created_at >= cutoff_iso
    )
    GROUP BY post_id
  )
  UPDATE posts
  SET reaction_count = actual.cnt,
      updated_at     = now()
  FROM actual
  WHERE posts.id = actual.post_id
    AND posts.reaction_count IS DISTINCT FROM actual.cnt;
  GET DIAGNOSTICS row_count = ROW_COUNT;
  RETURN row_count;
END;
$$;

-- DOWN:
DROP FUNCTION IF EXISTS public.reconcile_reaction_counts(TIMESTAMPTZ);
DROP FUNCTION IF EXISTS public.decrement_reaction_count(UUID);
DROP FUNCTION IF EXISTS public.increment_reaction_count(UUID);
