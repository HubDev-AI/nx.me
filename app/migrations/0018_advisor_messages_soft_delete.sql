-- 0018_advisor_messages_soft_delete.sql
-- LR-13: Soft-delete advisor messages after summarization.
-- Adds summarized_at column so messages are marked rather than hard-deleted,
-- enabling auditing and recovery if a Haiku-generated summary is poor.

-- UP
ALTER TABLE advisor_messages ADD COLUMN IF NOT EXISTS summarized_at TIMESTAMPTZ;

-- DOWN:
-- ALTER TABLE advisor_messages DROP COLUMN IF EXISTS summarized_at;
