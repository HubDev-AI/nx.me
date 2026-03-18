-- 0007_advisor_tables.sql
-- Story 7-1: Advisor memory, conversation, and nudge tables + pgvector.
-- Requires pgvector extension (enabled in Supabase by default).

-- Enable pgvector if not already enabled
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. user_memories (advisor memory system)
CREATE TABLE user_memories (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type       TEXT NOT NULL CHECK (type IN (
                 'goal', 'dismissed_suggestion', 'accepted_suggestion',
                 'user_note', 'analysis_insight')),
    content    JSONB NOT NULL,
    embedding  vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_user_memories_user_id ON user_memories(user_id);
CREATE INDEX idx_user_memories_embedding ON user_memories USING ivfflat (embedding vector_cosine_ops);

-- 2. advisor_conversations
CREATE TABLE advisor_conversations (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    summarised_at TIMESTAMPTZ,
    summary       TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_advisor_conversations_user ON advisor_conversations(user_id, created_at DESC);

-- 3. advisor_messages
CREATE TABLE advisor_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES advisor_conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'advisor')),
    content         TEXT NOT NULL,
    token_count     INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_advisor_messages_conv ON advisor_messages(conversation_id, created_at ASC);

-- 4. advisor_nudges
CREATE TABLE advisor_nudges (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    trigger    TEXT NOT NULL,
    content    TEXT NOT NULL,
    read_at    TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_advisor_nudges_user ON advisor_nudges(user_id, created_at DESC);

-- 5. RPC: match_user_memories (pgvector cosine similarity search)
CREATE FUNCTION match_user_memories(p_user_id UUID, p_embedding vector(1536), p_limit INT)
RETURNS TABLE (id UUID, type TEXT, content JSONB, similarity FLOAT, created_at TIMESTAMPTZ)
AS $$
    SELECT id, type, content, 1 - (embedding <=> p_embedding), created_at
    FROM user_memories WHERE user_id = p_user_id
    ORDER BY embedding <=> p_embedding LIMIT p_limit;
$$ LANGUAGE sql STABLE;

-- DOWN:
DROP FUNCTION IF EXISTS match_user_memories;
DROP TABLE IF EXISTS advisor_nudges CASCADE;
DROP TABLE IF EXISTS advisor_messages CASCADE;
DROP TABLE IF EXISTS advisor_conversations CASCADE;
DROP TABLE IF EXISTS user_memories CASCADE;
