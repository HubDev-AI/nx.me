-- 0037_advisor_embedding_dim_768.sql
-- Migrate user_memories.embedding from vector(1536) to vector(768) so the
-- advisor can use embedding backends that natively output 768-dim vectors
-- (Ollama nomic-embed-text). OpenAI text-embedding-3-small still works
-- via Matryoshka with `dimensions=768`.
--
-- pgvector cannot ALTER COLUMN TYPE between vector dimensions, so we drop
-- + re-add the column. Existing memories lose their embeddings; the
-- backend recomputes on next read/write. This is acceptable for current
-- deployments (no production user memories) but is a BREAKING change
-- for any environment that already has populated user_memories rows —
-- those rows will need a backfill pass before pgvector RPCs return them.
--
-- The match_user_memories RPC's signature also changes (vector(1536) →
-- vector(768)) so it must be dropped + recreated.

-- Drop dependent index first (PG won't drop a column with an index in some configs).
DROP INDEX IF EXISTS idx_user_memories_embedding;

-- Drop the RPC that references the old column type.
DROP FUNCTION IF EXISTS match_user_memories(UUID, vector, INT);

-- Swap the column type by dropping and re-adding (pgvector limitation).
ALTER TABLE user_memories DROP COLUMN embedding;
ALTER TABLE user_memories ADD COLUMN embedding vector(768);

-- Recreate the index for the new dimension.
CREATE INDEX idx_user_memories_embedding ON user_memories USING ivfflat (embedding vector_cosine_ops);

-- Recreate the RPC with the new dimension.
CREATE FUNCTION match_user_memories(p_user_id UUID, p_embedding vector(768), p_limit INT)
RETURNS TABLE (id UUID, type TEXT, content JSONB, similarity FLOAT, created_at TIMESTAMPTZ)
AS $$
    SELECT id, type, content, 1 - (embedding <=> p_embedding), created_at
    FROM user_memories WHERE user_id = p_user_id
    ORDER BY embedding <=> p_embedding LIMIT p_limit;
$$ LANGUAGE sql STABLE;

-- DOWN: revert to 1536 (also drops embeddings — symmetrical to the up).
-- DROP INDEX IF EXISTS idx_user_memories_embedding;
-- DROP FUNCTION IF EXISTS match_user_memories(UUID, vector, INT);
-- ALTER TABLE user_memories DROP COLUMN embedding;
-- ALTER TABLE user_memories ADD COLUMN embedding vector(1536);
-- CREATE INDEX idx_user_memories_embedding ON user_memories USING ivfflat (embedding vector_cosine_ops);
-- CREATE FUNCTION match_user_memories(p_user_id UUID, p_embedding vector(1536), p_limit INT) ...
