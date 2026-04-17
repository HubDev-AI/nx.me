-- 0043_match_user_memories_authored_by.sql
-- Plan 2026-04-18 follow-up: expose authored_by in pgvector RPC results.
--
-- Why: ``search_memories`` renders each retrieved row through
-- ``_format_memory_line`` which stamps ``(user)`` on rows where
-- ``authored_by='user'``. The RPC signature created in migration 0007
-- (resized in 0037) doesn't include ``authored_by`` in its RETURNS TABLE,
-- so the marker never surfaces in production despite the Python tests
-- passing (test stubs return the full row shape). This migration drops
-- and re-creates the RPC with the extra column.
--
-- The ``match_user_memories_by_type`` RPC added in 0042 is write-side
-- (semantic dedup before insert) and doesn't feed the renderer, so it
-- is intentionally left alone.

DROP FUNCTION IF EXISTS match_user_memories(UUID, vector(768), INT);

CREATE FUNCTION match_user_memories(
    p_user_id UUID,
    p_embedding vector(768),
    p_limit INT
)
RETURNS TABLE (
    id UUID,
    type TEXT,
    content JSONB,
    similarity FLOAT,
    created_at TIMESTAMPTZ,
    authored_by TEXT
)
AS $$
    SELECT id, type, content, 1 - (embedding <=> p_embedding), created_at, authored_by
    FROM user_memories
    WHERE user_id = p_user_id
    ORDER BY embedding <=> p_embedding
    LIMIT p_limit;
$$ LANGUAGE sql STABLE;

-- DOWN:
-- DROP FUNCTION IF EXISTS match_user_memories(UUID, vector(768), INT);
-- CREATE FUNCTION match_user_memories(p_user_id UUID, p_embedding vector(768), p_limit INT)
-- RETURNS TABLE (id UUID, type TEXT, content JSONB, similarity FLOAT, created_at TIMESTAMPTZ)
-- AS $$
--     SELECT id, type, content, 1 - (embedding <=> p_embedding), created_at
--     FROM user_memories WHERE user_id = p_user_id
--     ORDER BY embedding <=> p_embedding LIMIT p_limit;
-- $$ LANGUAGE sql STABLE;
