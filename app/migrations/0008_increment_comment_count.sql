-- Atomic increment for posts.comment_count to prevent race conditions.
-- Called via supabase.rpc('increment_comment_count', {'post_id': ...})

CREATE OR REPLACE FUNCTION public.increment_comment_count(p_post_id UUID)
RETURNS VOID
LANGUAGE sql
AS $$
  UPDATE posts
  SET comment_count = comment_count + 1,
      updated_at    = now()
  WHERE id = p_post_id;
$$;
