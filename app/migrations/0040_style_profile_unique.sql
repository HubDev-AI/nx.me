-- 0040_style_profile_unique.sql
-- Plan 2026-04-17-003 Unit 7: Stable `style_profile` memory — one row per user,
-- upserted on every successful analysis. Chat user_data and nudge generation
-- read from this row in preference to re-deriving facts from the most recent
-- `analysis_insight`.
--
-- Two changes:
--
-- 1. Extend the `type` CHECK constraint to accept the new 'style_profile'
--    value alongside the existing memory types. The CHECK list was last
--    defined in migration 0007 and has not been altered since, so we drop
--    the anonymous check by name and recreate it with the additional value.
--    The constraint name is stable across Postgres versions because we
--    assigned it explicitly below.
--
-- 2. Add a partial UNIQUE INDEX on (user_id) WHERE type='style_profile' so
--    the repository's upsert semantics are enforced at the database level —
--    at most one style_profile row per user, while still allowing N
--    analysis_insight rows per user. A full UNIQUE(user_id, type) would
--    break the existing per-event analysis_insight model.
--
-- Pre-launch: no row migration needed (no live style_profile data exists).
-- Idempotent: guarded by IF NOT EXISTS / named constraint drop.

-- Extend the memory type enum: drop the anonymous CHECK added by
-- migration 0007 and replace with a named check that includes style_profile.
-- Postgres auto-named the original constraint `user_memories_type_check`;
-- use IF EXISTS for idempotency across environments that may have been
-- manually fixed up.
ALTER TABLE user_memories DROP CONSTRAINT IF EXISTS user_memories_type_check;
ALTER TABLE user_memories
    ADD CONSTRAINT user_memories_type_check
    CHECK (type IN (
        'goal',
        'dismissed_suggestion',
        'accepted_suggestion',
        'user_note',
        'analysis_insight',
        'style_profile'
    ));

-- Partial unique index: at most one style_profile row per user.
-- Does not affect analysis_insight rows (WHERE clause scopes the index).
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_memories_style_profile_unique
    ON user_memories(user_id)
    WHERE type = 'style_profile';

-- DOWN:
DROP INDEX IF EXISTS idx_user_memories_style_profile_unique;
ALTER TABLE user_memories DROP CONSTRAINT IF EXISTS user_memories_type_check;
ALTER TABLE user_memories
    ADD CONSTRAINT user_memories_type_check
    CHECK (type IN (
        'goal',
        'dismissed_suggestion',
        'accepted_suggestion',
        'user_note',
        'analysis_insight'
    ));
