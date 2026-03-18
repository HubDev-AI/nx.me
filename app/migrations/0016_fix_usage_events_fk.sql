-- 0016_fix_usage_events_fk.sql
-- Fix: usage_events.user_id references auth.users(id) instead of public.users(id).
-- Every other table references public.users. ON DELETE CASCADE should fire when
-- the application user is deleted, not the auth identity.

-- UP

ALTER TABLE usage_events
  DROP CONSTRAINT IF EXISTS usage_events_user_id_fkey;

ALTER TABLE usage_events
  ADD CONSTRAINT usage_events_user_id_fkey
  FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- DOWN

ALTER TABLE usage_events
  DROP CONSTRAINT IF EXISTS usage_events_user_id_fkey;

ALTER TABLE usage_events
  ADD CONSTRAINT usage_events_user_id_fkey
  FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
