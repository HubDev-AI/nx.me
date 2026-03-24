-- 0030_tiktok_auth.sql
-- Add TikTok identity column to users table for OAuth login.

ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS tiktok_open_id TEXT;

-- Unique constraint + partial index for fast lookup (only non-null values)
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_tiktok_open_id
  ON public.users (tiktok_open_id)
  WHERE tiktok_open_id IS NOT NULL;
