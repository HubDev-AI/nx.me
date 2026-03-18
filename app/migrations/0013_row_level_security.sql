-- 0013_row_level_security.sql
-- Enable Row-Level Security on all 16 user-scoped tables.
-- Policy: authenticated users can only access their own rows.
-- Service role bypasses RLS (used by backend RPCs and webhooks).
-- Posts and comments get read-only public access (WHERE NOT is_deleted).

-- UP

-- Helper: all 16 user-scoped tables
-- users, images, analyses, credit_reservations, glow_up_jobs, credit_ledger,
-- subscriptions, posts, reactions, comments, reports, usage_events,
-- user_memories, advisor_conversations, advisor_messages, advisor_nudges

-- 1. Enable RLS + FORCE on all tables
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;
ALTER TABLE images ENABLE ROW LEVEL SECURITY;
ALTER TABLE images FORCE ROW LEVEL SECURITY;
ALTER TABLE analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE analyses FORCE ROW LEVEL SECURITY;
ALTER TABLE credit_reservations ENABLE ROW LEVEL SECURITY;
ALTER TABLE credit_reservations FORCE ROW LEVEL SECURITY;
ALTER TABLE glow_up_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE glow_up_jobs FORCE ROW LEVEL SECURITY;
ALTER TABLE credit_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE credit_ledger FORCE ROW LEVEL SECURITY;
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions FORCE ROW LEVEL SECURITY;
ALTER TABLE posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE posts FORCE ROW LEVEL SECURITY;
ALTER TABLE reactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE reactions FORCE ROW LEVEL SECURITY;
ALTER TABLE comments ENABLE ROW LEVEL SECURITY;
ALTER TABLE comments FORCE ROW LEVEL SECURITY;
ALTER TABLE reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports FORCE ROW LEVEL SECURITY;
ALTER TABLE usage_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_events FORCE ROW LEVEL SECURITY;
ALTER TABLE user_memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_memories FORCE ROW LEVEL SECURITY;
ALTER TABLE advisor_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE advisor_conversations FORCE ROW LEVEL SECURITY;
ALTER TABLE advisor_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE advisor_messages FORCE ROW LEVEL SECURITY;
ALTER TABLE advisor_nudges ENABLE ROW LEVEL SECURITY;
ALTER TABLE advisor_nudges FORCE ROW LEVEL SECURITY;

-- 2. Owner policies: users can CRUD their own rows
-- "users" table: user_id is "id" column
CREATE POLICY users_own ON users
  FOR ALL
  TO authenticated
  USING (id = auth.uid())
  WITH CHECK (id = auth.uid());

-- Standard user_id-based tables
CREATE POLICY images_own ON images
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

CREATE POLICY analyses_own ON analyses
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

CREATE POLICY credit_reservations_own ON credit_reservations
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

CREATE POLICY glow_up_jobs_own ON glow_up_jobs
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

CREATE POLICY credit_ledger_own ON credit_ledger
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

CREATE POLICY subscriptions_own ON subscriptions
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

CREATE POLICY reports_own ON reports
  FOR ALL TO authenticated
  USING (reporter_user_id = auth.uid())
  WITH CHECK (reporter_user_id = auth.uid());

CREATE POLICY usage_events_own ON usage_events
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

CREATE POLICY user_memories_own ON user_memories
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

CREATE POLICY advisor_conversations_own ON advisor_conversations
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

CREATE POLICY advisor_nudges_own ON advisor_nudges
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- advisor_messages: user owns messages via conversation ownership
CREATE POLICY advisor_messages_own ON advisor_messages
  FOR ALL TO authenticated
  USING (
    conversation_id IN (
      SELECT id FROM advisor_conversations WHERE user_id = auth.uid()
    )
  )
  WITH CHECK (
    conversation_id IN (
      SELECT id FROM advisor_conversations WHERE user_id = auth.uid()
    )
  );

-- 3. Posts: owner full access + public read for non-deleted
CREATE POLICY posts_own ON posts
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

CREATE POLICY posts_public_read ON posts
  FOR SELECT TO anon, authenticated
  USING (NOT is_deleted);

-- 4. Comments: owner full access + public read for non-deleted
CREATE POLICY comments_own ON comments
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

CREATE POLICY comments_public_read ON comments
  FOR SELECT TO anon, authenticated
  USING (NOT is_deleted);

-- 5. Reactions: authenticated users can insert their own + read all
CREATE POLICY reactions_own ON reactions
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- Guest reactions (via guest_session_token) are handled by service role RPCs
-- Anon users can read reaction counts via posts table, not reactions directly
CREATE POLICY reactions_read ON reactions
  FOR SELECT TO authenticated
  USING (true);


-- DOWN

-- Drop all policies
DROP POLICY IF EXISTS users_own ON users;
DROP POLICY IF EXISTS images_own ON images;
DROP POLICY IF EXISTS analyses_own ON analyses;
DROP POLICY IF EXISTS credit_reservations_own ON credit_reservations;
DROP POLICY IF EXISTS glow_up_jobs_own ON glow_up_jobs;
DROP POLICY IF EXISTS credit_ledger_own ON credit_ledger;
DROP POLICY IF EXISTS subscriptions_own ON subscriptions;
DROP POLICY IF EXISTS posts_own ON posts;
DROP POLICY IF EXISTS posts_public_read ON posts;
DROP POLICY IF EXISTS reactions_own ON reactions;
DROP POLICY IF EXISTS reactions_read ON reactions;
DROP POLICY IF EXISTS comments_own ON comments;
DROP POLICY IF EXISTS comments_public_read ON comments;
DROP POLICY IF EXISTS reports_own ON reports;
DROP POLICY IF EXISTS usage_events_own ON usage_events;
DROP POLICY IF EXISTS user_memories_own ON user_memories;
DROP POLICY IF EXISTS advisor_conversations_own ON advisor_conversations;
DROP POLICY IF EXISTS advisor_messages_own ON advisor_messages;
DROP POLICY IF EXISTS advisor_nudges_own ON advisor_nudges;

-- Disable RLS on all tables
ALTER TABLE users DISABLE ROW LEVEL SECURITY;
ALTER TABLE images DISABLE ROW LEVEL SECURITY;
ALTER TABLE analyses DISABLE ROW LEVEL SECURITY;
ALTER TABLE credit_reservations DISABLE ROW LEVEL SECURITY;
ALTER TABLE glow_up_jobs DISABLE ROW LEVEL SECURITY;
ALTER TABLE credit_ledger DISABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions DISABLE ROW LEVEL SECURITY;
ALTER TABLE posts DISABLE ROW LEVEL SECURITY;
ALTER TABLE reactions DISABLE ROW LEVEL SECURITY;
ALTER TABLE comments DISABLE ROW LEVEL SECURITY;
ALTER TABLE reports DISABLE ROW LEVEL SECURITY;
ALTER TABLE usage_events DISABLE ROW LEVEL SECURITY;
ALTER TABLE user_memories DISABLE ROW LEVEL SECURITY;
ALTER TABLE advisor_conversations DISABLE ROW LEVEL SECURITY;
ALTER TABLE advisor_messages DISABLE ROW LEVEL SECURITY;
ALTER TABLE advisor_nudges DISABLE ROW LEVEL SECURITY;
