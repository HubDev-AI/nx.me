-- 0038_user_memories_type_index.sql
-- Replace the bare idx_user_memories_user_id with a composite that
-- matches every non-vector access pattern exactly.
--
-- Query shapes served:
--   SELECT ... WHERE user_id = ? AND type = ? ORDER BY created_at DESC, id DESC
--   SELECT ... WHERE user_id = ?              ORDER BY created_at DESC, id DESC
--   SELECT ... WHERE user_id = ? ORDER BY embedding <=> ? LIMIT ?  (match_user_memories RPC)
--
-- The composite's leading `user_id` prefix covers user_id-only lookups,
-- so the bare (user_id) index is pure duplication. Drop it.
-- Pre-launch: no deprecation window, no compat to preserve.

CREATE INDEX IF NOT EXISTS idx_user_memories_user_type_created
  ON user_memories (user_id, type, created_at DESC, id DESC);

DROP INDEX IF EXISTS idx_user_memories_user_id;

-- rollback:
-- CREATE INDEX idx_user_memories_user_id ON user_memories(user_id);
-- DROP INDEX IF EXISTS idx_user_memories_user_type_created;
