-- 0044_hard_delete_account.sql
-- Hard-delete account support (plan 2026-04-18).
--
-- Pre-launch, destructive DB refactor. Replaces soft-delete on users
-- (deleted_at + username_reserved_until) with:
--   * reservations in a dedicated `username_reservations` table,
--   * FKs rewritten so `DELETE FROM users WHERE id=...` cascades (or
--     null-outs the reporter/blocker refs that must survive for audit).
--
-- The migration runner (app/migrations/run.py) wraps every file in its
-- own transaction, so we do not add a redundant BEGIN/COMMIT here.
--
-- Live schema verified before writing:
--   - RLS policy `users_public_read` references users.deleted_at.
--   - View `v_feed_posts` references users.deleted_at.
--   - Partial index `idx_users_username_reserved` references deleted_at.
--   - 11 FKs pointing at users are ON DELETE NO ACTION; the other 6 are
--     already CASCADE and do not need rewriting.

-- UP

-- 1. Drop dependents of users.deleted_at so DROP COLUMN can succeed.
--    The view is joined by feed functions, so CASCADE re-creates them
--    in step 5 along with the view itself. (Feed functions fall with it
--    and are recreated below.)
DROP POLICY IF EXISTS users_public_read ON users;
DROP VIEW IF EXISTS v_feed_posts CASCADE;
DROP INDEX IF EXISTS idx_users_username_reserved;

-- 2. Username reservation table (replaces users.username_reserved_until).
CREATE TABLE username_reservations (
    username       TEXT PRIMARY KEY,
    reserved_until TIMESTAMPTZ NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_username_reservations_expiry
    ON username_reservations (reserved_until);
CREATE UNIQUE INDEX idx_username_reservations_username_lower
    ON username_reservations (lower(username));

-- 3. Drop soft-delete columns.
ALTER TABLE users
    DROP COLUMN deleted_at,
    DROP COLUMN username_reserved_until;

-- 4. Rewrite FKs so account deletion is a real DELETE.
--    Verified names via pg_constraint; all follow {table}_{column}_fkey.

-- 4a. CASCADE: rows belong to the user and should die with them.
ALTER TABLE images
    DROP CONSTRAINT IF EXISTS images_user_id_fkey,
    ADD CONSTRAINT images_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE credit_reservations
    DROP CONSTRAINT IF EXISTS credit_reservations_user_id_fkey,
    ADD CONSTRAINT credit_reservations_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE credit_ledger
    DROP CONSTRAINT IF EXISTS credit_ledger_user_id_fkey,
    ADD CONSTRAINT credit_ledger_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE subscriptions
    DROP CONSTRAINT IF EXISTS subscriptions_user_id_fkey,
    ADD CONSTRAINT subscriptions_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE posts
    DROP CONSTRAINT IF EXISTS posts_user_id_fkey,
    ADD CONSTRAINT posts_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE reactions
    DROP CONSTRAINT IF EXISTS reactions_user_id_fkey,
    ADD CONSTRAINT reactions_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE comments
    DROP CONSTRAINT IF EXISTS comments_user_id_fkey,
    ADD CONSTRAINT comments_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE shareable_cards
    DROP CONSTRAINT IF EXISTS shareable_cards_user_id_fkey,
    ADD CONSTRAINT shareable_cards_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

-- 4b. SET NULL: audit rows survive deletion with an anonymized reference.
ALTER TABLE reports
    ALTER COLUMN reporter_user_id DROP NOT NULL,
    DROP CONSTRAINT IF EXISTS reports_reporter_user_id_fkey,
    ADD CONSTRAINT reports_reporter_user_id_fkey
        FOREIGN KEY (reporter_user_id) REFERENCES users(id) ON DELETE SET NULL;

ALTER TABLE blocked_users
    ALTER COLUMN blocker_id DROP NOT NULL,
    ALTER COLUMN blocked_id DROP NOT NULL,
    DROP CONSTRAINT IF EXISTS blocked_users_blocker_id_fkey,
    ADD CONSTRAINT blocked_users_blocker_id_fkey
        FOREIGN KEY (blocker_id) REFERENCES users(id) ON DELETE SET NULL,
    DROP CONSTRAINT IF EXISTS blocked_users_blocked_id_fkey,
    ADD CONSTRAINT blocked_users_blocked_id_fkey
        FOREIGN KEY (blocked_id) REFERENCES users(id) ON DELETE SET NULL;

-- 5. Re-create the RLS policy and view without the tombstone filter.
--    Hard delete means a row is either present (active user) or gone;
--    there is no "exists but deleted" state to hide from readers.
CREATE POLICY users_public_read ON users
    FOR SELECT TO anon, authenticated
    USING (true);

CREATE OR REPLACE VIEW v_feed_posts AS
SELECT
    p.id,
    p.user_id,
    p.caption,
    p.before_image_url,
    p.after_image_url,
    p.reaction_count,
    p.comment_count,
    p.created_at,
    p.before_image_id,
    p.after_image_id,
    u.username,
    u.display_name,
    u.avatar_storage_key
FROM posts p
JOIN images bi ON bi.id = p.before_image_id AND bi.status = 'cleared'
JOIN images ai ON ai.id = p.after_image_id AND ai.status = 'cleared'
JOIN users u  ON u.id = p.user_id
WHERE NOT p.is_deleted
  AND NOT p.is_hidden;

-- Recreate feed functions that depended on v_feed_posts (dropped via CASCADE
-- in step 1). Bodies match the 0028 definitions that live in production
-- since no later migration touched them.
DROP FUNCTION IF EXISTS feed_trending(double precision, timestamptz, uuid, int);
CREATE OR REPLACE FUNCTION feed_trending(
    p_cursor_score  DOUBLE PRECISION DEFAULT NULL,
    p_cursor_created TIMESTAMPTZ      DEFAULT NULL,
    p_cursor_id      UUID             DEFAULT NULL,
    p_limit          INT              DEFAULT 11
)
RETURNS TABLE (
    id               UUID,
    user_id          UUID,
    caption          TEXT,
    before_image_url TEXT,
    after_image_url  TEXT,
    reaction_count   INT,
    comment_count    INT,
    created_at       TIMESTAMPTZ,
    before_image_id  UUID,
    after_image_id   UUID,
    username         TEXT,
    display_name     TEXT,
    avatar_storage_key TEXT,
    trending_score   DOUBLE PRECISION
)
LANGUAGE sql STABLE
AS $$
    WITH scored AS (
        SELECT
            fp.*,
            fp.reaction_count::double precision
              / POWER(EXTRACT(EPOCH FROM (NOW() - fp.created_at)) / 3600.0 + 2, 1.5)
              AS trending_score
        FROM v_feed_posts fp
        WHERE fp.created_at >= NOW() - INTERVAL '7 days'
    )
    SELECT s.*
    FROM scored s
    WHERE (p_cursor_score IS NULL)
       OR (s.trending_score < p_cursor_score)
       OR (s.trending_score = p_cursor_score AND s.created_at < p_cursor_created)
       OR (s.trending_score = p_cursor_score AND s.created_at = p_cursor_created AND s.id > p_cursor_id)
    ORDER BY s.trending_score DESC, s.created_at DESC, s.id ASC
    LIMIT p_limit;
$$;

DROP FUNCTION IF EXISTS feed_biggest_improvements(int, timestamptz, uuid, int);
CREATE OR REPLACE FUNCTION feed_biggest_improvements(
    p_cursor_reactions INT         DEFAULT NULL,
    p_cursor_created   TIMESTAMPTZ DEFAULT NULL,
    p_cursor_id        UUID        DEFAULT NULL,
    p_limit            INT         DEFAULT 11
)
RETURNS TABLE (
    id               UUID,
    user_id          UUID,
    caption          TEXT,
    before_image_url TEXT,
    after_image_url  TEXT,
    reaction_count   INT,
    comment_count    INT,
    created_at       TIMESTAMPTZ,
    before_image_id  UUID,
    after_image_id   UUID,
    username         TEXT,
    display_name     TEXT,
    avatar_storage_key TEXT
)
LANGUAGE sql STABLE
AS $$
    SELECT fp.*
    FROM v_feed_posts fp
    WHERE (p_cursor_reactions IS NULL)
       OR (fp.reaction_count < p_cursor_reactions)
       OR (fp.reaction_count = p_cursor_reactions AND fp.created_at < p_cursor_created)
       OR (fp.reaction_count = p_cursor_reactions AND fp.created_at = p_cursor_created AND fp.id > p_cursor_id)
    ORDER BY fp.reaction_count DESC, fp.created_at DESC, fp.id ASC
    LIMIT p_limit;
$$;

-- 6. RLS on username_reservations. Deny all direct access — only the
--    service role (which bypasses RLS) touches this table.
ALTER TABLE username_reservations ENABLE ROW LEVEL SECURITY;
CREATE POLICY username_reservations_deny_all ON username_reservations
    FOR ALL TO anon, authenticated
    USING (false) WITH CHECK (false);

-- DOWN:
-- Pre-launch, destructive schema refactor. No reverse path is provided;
-- re-establishing soft-delete semantics would require back-filling
-- deleted_at/username_reserved_until from the reservations table and
-- reverting every FK one-by-one. Use `make nuke` + re-run migrations
-- if you need to start over locally.
