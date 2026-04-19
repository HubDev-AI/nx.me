-- 0052_signup_grants_issued.sql
--
-- Device-fingerprint registry backing the one-time signup credit grant
-- (R6a). Prevents a user from reinstalling, deleting their account, or
-- creating a fresh account on the same device to re-collect the 300-milli
-- signup grant.
--
-- === SURVIVES `delete_account` BY DESIGN ===
--
-- This is the ONE documented exception to `feedback_delete_account_scope`
-- (every other user-owned row/blob/Redis key must be wiped by the
-- delete-account flow). Legal review has green-lit this table because:
--
--   * the identifier stored is not a direct personal identifier — it is a
--     HMAC+salted hash of a mobile-generated installation UUID (see below),
--   * the business need (grant-abuse prevention) cannot be satisfied by
--     any user-scoped record that gets deleted with the account,
--   * the row is auto-purged 12 months after issuance (nightly ARQ sweep,
--     Unit 9), so retention is bounded.
--
-- === LOOKUP / AT-REST PROTECTION ===
--
-- Two hashes per row, computed app-side before insert:
--
--   * `deterministic_hash = HMAC-SHA256(server_secret, installation_uuid)`
--     — the lookup key. Constant for a given (secret, uuid) pair so we can
--     probe "has this device been granted before?" in one PK select.
--     Rotating `SIGNUP_FINGERPRINT_SERVER_SECRET` invalidates the entire
--     registry (see payments runbook / Unit 6).
--
--   * `protected_hash = SHA256(salt || installation_uuid)` with a fresh
--     32-byte random `salt` per row — the at-rest defense. An attacker
--     who dumps the DB cannot brute-force the 2^122-entry UUID space
--     without also exfiltrating each row's salt, and cannot precompute
--     rainbow tables because each salt is unique.
--
-- === 12-MONTH TTL ===
--
-- `issued_at` is indexed so the nightly purge job (Unit 9) can cheaply
-- `DELETE FROM signup_grants_issued WHERE issued_at < now() - interval
-- '12 months'`.
--
-- === ACCESS CONTROL ===
--
-- RLS is enabled with a deny-all policy for `anon` and `authenticated`.
-- Only the service-role JWT (which bypasses RLS) touches this table —
-- writes via `credit_apply_signup_grant`, reads via the nightly purge
-- job. No user-facing query path exists or should exist.
--
-- Migration runner (`app/migrations/run.py`) wraps this file in its own
-- transaction; no explicit BEGIN/COMMIT needed.

-- UP

CREATE TABLE signup_grants_issued (
    deterministic_hash BYTEA PRIMARY KEY,
    protected_hash     BYTEA        NOT NULL,
    salt               BYTEA        NOT NULL,
    issued_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Supports the nightly TTL sweep (Unit 9): range scan on issued_at.
CREATE INDEX idx_signup_grants_issued_at
    ON signup_grants_issued (issued_at);

-- Service-role only. Any direct anon/authenticated access is rejected.
ALTER TABLE signup_grants_issued ENABLE ROW LEVEL SECURITY;
CREATE POLICY signup_grants_deny_all ON signup_grants_issued
    FOR ALL TO anon, authenticated
    USING (false) WITH CHECK (false);

-- DOWN
DROP TABLE signup_grants_issued;
