-- 0031_username_changed_at.sql
-- Track when username was last changed (24h cooldown enforcement)

ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS username_changed_at TIMESTAMPTZ;
