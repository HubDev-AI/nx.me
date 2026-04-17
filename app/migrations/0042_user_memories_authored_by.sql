-- 0042_user_memories_authored_by.sql
-- Plan 2026-04-18: split user-typed memories from RAG-only memories.
--
-- Context: user_memories stored everything (user-typed goal/note, Haiku-
-- extracted accepted/dismissed, analysis-pipeline insight/profile) with no
-- provenance. Consequences:
--   1. Haiku-inferred goals/notes leaked into the UI's Goals/Notes tabs.
--   2. Could not distinguish user intent from machine inference for the
--      retrieval ranker.
--   3. Cap eviction (delete_oldest_memory_excluding_types) had no way to
--      protect user-typed rows over machine-inferred ones.
--
-- This migration introduces an ``authored_by`` column with three values:
--   * ``user``      — POST /v1/memories from the Goals/Notes UI.
--   * ``model``     — Ada calling the save_memory MCP tool mid-chat.
--   * ``analysis``  — face-analysis pipeline (style_profile, insight).
--
-- The prior Haiku post-turn extraction path is being deleted in the same
-- PR, so no ``extraction`` value is ever needed in the enum.
--
-- Pre-launch destructive truncate is intentional — there is no production
-- memory data worth preserving and the new column is NOT NULL without a
-- default. Per project rule ``feedback_pre_launch_destructive_ok``.
--
-- Index rationale: the UI list path filters by user_id + type +
-- authored_by='user'. The retrieval / eviction paths filter by user_id +
-- authored_by. A covering index on (user_id, authored_by) serves both
-- without being redundant with the existing (user_id) index, because
-- Postgres can use the leading column for the type-only existing queries.

TRUNCATE TABLE user_memories;

ALTER TABLE user_memories
    ADD COLUMN authored_by TEXT NOT NULL
    CHECK (authored_by IN ('user', 'model', 'analysis'));

-- Content fingerprint for exact-duplicate dedup. Written by the app as
-- SHA-256 of the canonical JSON representation (json.dumps with
-- sort_keys=True) so two semantically-identical dicts produce the same
-- hash regardless of Python dict insertion order or JSONB's unordered
-- storage. NULL is permitted for rows that do not participate in dedup
-- (e.g. ``style_profile`` which is singleton-guarded separately).
ALTER TABLE user_memories ADD COLUMN content_hash TEXT;

CREATE INDEX idx_user_memories_user_authored ON user_memories(user_id, authored_by);

-- Atomic dedup guard. Two concurrent writes for the same
-- (user_id, type, content_hash) cannot both land — the second
-- ``insert_memory`` raises a unique-violation and ``write_memory``
-- falls back to the existing row. Partial on ``content_hash IS NOT NULL``
-- so the style_profile path (which sets content_hash=NULL) is unaffected.
CREATE UNIQUE INDEX idx_user_memories_content_hash_unique
    ON user_memories(user_id, type, content_hash)
    WHERE content_hash IS NOT NULL;

-- Semantic-dedup RPC: like match_user_memories but filtered to a single
-- type. Called from MemoryManager.write_memory's second dedup stage —
-- a user's new goal should only be compared against their other goals,
-- not against accepted_suggestions that happen to embed near "grow my
-- hair out". Returns the single nearest neighbor; the Python caller
-- gates on the similarity threshold.
CREATE FUNCTION match_user_memories_by_type(
    p_user_id UUID,
    p_embedding vector(768),
    p_type TEXT,
    p_limit INT
)
RETURNS TABLE (
    id UUID,
    type TEXT,
    content JSONB,
    similarity FLOAT,
    created_at TIMESTAMPTZ
)
AS $$
    SELECT id, type, content, 1 - (embedding <=> p_embedding), created_at
    FROM user_memories
    WHERE user_id = p_user_id AND type = p_type
    ORDER BY embedding <=> p_embedding
    LIMIT p_limit;
$$ LANGUAGE sql STABLE;

-- DOWN:
-- DROP FUNCTION IF EXISTS match_user_memories_by_type(UUID, vector, TEXT, INT);
-- DROP INDEX IF EXISTS idx_user_memories_content_hash_unique;
-- DROP INDEX IF EXISTS idx_user_memories_user_authored;
-- ALTER TABLE user_memories DROP COLUMN IF EXISTS content_hash;
-- ALTER TABLE user_memories DROP COLUMN IF EXISTS authored_by;
