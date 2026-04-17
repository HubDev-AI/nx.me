-- 0041_advisor_nudges_observation.sql
-- Plan 2026-04-17-003 Unit 8: vision-grounded post-generation nudges.
--
-- Adds a model-authored ``observation_tag`` column to ``advisor_nudges``.
-- The column is a short (1-3 word) descriptor the model emits alongside
-- each nudge body so future nudges can see what prior ones focused on
-- and naturally steer elsewhere. Server never interprets, filters, or
-- rotates on it — it is context for the model, not routing logic. Do
-- NOT add a fixed topic taxonomy or a ``focus`` column; the earlier
-- deterministic rotation was the bug this migration addresses.
--
-- NULL is allowed and represents "no tag" — rows written before this
-- migration are treated as such by the prompt renderer for graceful
-- forward-compat.
--
-- Idempotent: guarded by IF NOT EXISTS.
-- Pre-launch: no row migration required.

ALTER TABLE advisor_nudges
    ADD COLUMN IF NOT EXISTS observation_tag TEXT;

-- DOWN:
-- ALTER TABLE advisor_nudges DROP COLUMN IF EXISTS observation_tag;
