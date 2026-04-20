-- 0057: app_kill_switches — generic hot-toggle table for cron/worker jobs.
--
-- Operators flip `enabled` via SQL to start/stop background jobs without a
-- redeploy. Read at job fire-time by `app.runtime_flags.is_kill_switch_enabled`.
-- Missing row ⇒ treated as ENABLED (fail-open: a forgotten seed must not
-- silently disable a production job).
--
-- RLS: deny-all to anon/authenticated; only service_role touches this table.

CREATE TABLE IF NOT EXISTS app_kill_switches (
    key TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    note TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE app_kill_switches ENABLE ROW LEVEL SECURITY;
CREATE POLICY app_kill_switches_deny_all ON app_kill_switches
    FOR ALL TO anon, authenticated USING (false) WITH CHECK (false);

-- Seed row for the weekly free-credit grant cron. Flip to FALSE to pause:
--   UPDATE app_kill_switches SET enabled = FALSE, note = 'reason', updated_at = now()
--   WHERE key = 'weekly_free_grant';
INSERT INTO app_kill_switches (key, enabled, note)
VALUES ('weekly_free_grant', TRUE, 'Monday 02:30 UTC weekly free-credit grant')
ON CONFLICT (key) DO NOTHING;
