-- 0017_index_fixes.sql
-- DB-2: Replace usage_events index with partial WHERE status='committed' (ESR)
-- DB-3: Add reactions(created_at, post_id) for reconciliation queries
-- DB-4: Add reports indexes for admin queries
-- DB-5: Replace IVFFlat with HNSW on user_memories embedding
-- DB-6: Drop redundant indexes duplicating UNIQUE constraints
-- DB-7: Add prompt_experiments(job_id) index
-- DB-8: Add decrement_comment_count function (counterpart to increment)

-- UP

-- DB-2: usage_events ESR index (partial on committed status)
DROP INDEX IF EXISTS idx_usage_events_user_action_time;
CREATE INDEX idx_usage_events_committed
  ON usage_events(user_id, action, created_at DESC)
  WHERE status = 'committed';

-- DB-3: reactions created_at index for reconciliation
CREATE INDEX idx_reactions_created ON reactions(created_at, post_id);

-- DB-4: reports table indexes
CREATE INDEX idx_reports_post ON reports(post_id);
CREATE INDEX idx_reports_status ON reports(status, created_at DESC);

-- DB-5: IVFFlat → HNSW on user_memories
DROP INDEX IF EXISTS idx_user_memories_embedding;
CREATE INDEX idx_user_memories_embedding ON user_memories USING hnsw (embedding vector_cosine_ops);

-- DB-6: Drop redundant indexes (UNIQUE constraints already create B-tree indexes)
DROP INDEX IF EXISTS idx_cards_slug;
DROP INDEX IF EXISTS idx_users_username;

-- DB-7: prompt_experiments.job_id index
CREATE INDEX idx_prompt_exp_job ON prompt_experiments(job_id);

-- DB-8: decrement_comment_count function
CREATE OR REPLACE FUNCTION public.decrement_comment_count(p_post_id UUID)
RETURNS VOID
LANGUAGE sql
AS $$
  UPDATE posts
  SET comment_count = GREATEST(comment_count - 1, 0),
      updated_at    = now()
  WHERE id = p_post_id;
$$;

-- DOWN:

-- Restore original usage_events index
DROP INDEX IF EXISTS idx_usage_events_committed;
CREATE INDEX idx_usage_events_user_action_time ON usage_events(user_id, action, created_at DESC);

-- Drop new indexes
DROP INDEX IF EXISTS idx_reactions_created;
DROP INDEX IF EXISTS idx_reports_post;
DROP INDEX IF EXISTS idx_reports_status;

-- Restore IVFFlat
DROP INDEX IF EXISTS idx_user_memories_embedding;
CREATE INDEX idx_user_memories_embedding ON user_memories USING ivfflat (embedding vector_cosine_ops);

-- Restore redundant indexes
CREATE INDEX idx_cards_slug ON shareable_cards(slug);
CREATE INDEX idx_users_username ON users(username);

-- Drop new index
DROP INDEX IF EXISTS idx_prompt_exp_job;

-- Drop function
DROP FUNCTION IF EXISTS public.decrement_comment_count(UUID);
