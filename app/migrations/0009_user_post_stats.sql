-- Aggregate post stats for a user (count + total reactions) in a single query.
-- Called via supabase.rpc('user_post_stats', {'p_user_id': ...})

CREATE OR REPLACE FUNCTION public.user_post_stats(p_user_id UUID)
RETURNS TABLE(post_count BIGINT, total_reactions BIGINT)
LANGUAGE sql
STABLE
AS $$
  SELECT
    COUNT(*)::BIGINT            AS post_count,
    COALESCE(SUM(reaction_count), 0)::BIGINT AS total_reactions
  FROM posts
  WHERE user_id = p_user_id
    AND is_deleted = false;
$$;

-- DOWN:
DROP FUNCTION IF EXISTS public.user_post_stats(UUID);
