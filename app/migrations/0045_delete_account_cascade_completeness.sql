-- 0045_delete_account_cascade_completeness.sql
--
-- Completes the hard-delete cascade chain started in 0044. Rewrites 8 FKs
-- that were still ON DELETE NO ACTION and can block `DELETE FROM users`
-- when the cascade tries to remove rows those FKs point at.
--
-- Root cause found during code review: DELETE FROM users cascades to posts
-- and jobs, but `reports.post_id` / `shareable_cards.post_id` /
-- `prompt_experiments.job_id` / etc. still used NO ACTION. Any row in
-- those tables pointing at the cascaded posts/jobs/credit_reservations/
-- images would raise FK violation mid-cascade. Worst case: auth identity
-- deleted (step 3 of the endpoint), then DB DELETE fails (step 5) — user
-- becomes a permanently locked-out zombie.
--
-- All 8 FKs below become ON DELETE CASCADE — rows in these child tables
-- carry no independent meaning once the parent user's posts/jobs/images/
-- credit_reservations are gone.
--
-- `users.tier_id → tiers(id)` is intentionally left as NO ACTION — tiers
-- must never trigger a user delete.

-- UP

ALTER TABLE posts
    DROP CONSTRAINT posts_before_image_id_fkey,
    ADD CONSTRAINT posts_before_image_id_fkey
        FOREIGN KEY (before_image_id) REFERENCES images(id) ON DELETE CASCADE;

ALTER TABLE posts
    DROP CONSTRAINT posts_after_image_id_fkey,
    ADD CONSTRAINT posts_after_image_id_fkey
        FOREIGN KEY (after_image_id) REFERENCES images(id) ON DELETE CASCADE;

ALTER TABLE posts
    DROP CONSTRAINT posts_glow_up_job_id_fkey,
    ADD CONSTRAINT posts_glow_up_job_id_fkey
        FOREIGN KEY (glow_up_job_id) REFERENCES jobs(id) ON DELETE CASCADE;

ALTER TABLE shareable_cards
    DROP CONSTRAINT shareable_cards_post_id_fkey,
    ADD CONSTRAINT shareable_cards_post_id_fkey
        FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE;

ALTER TABLE reports
    DROP CONSTRAINT reports_post_id_fkey,
    ADD CONSTRAINT reports_post_id_fkey
        FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE;

ALTER TABLE prompt_experiments
    DROP CONSTRAINT prompt_experiments_job_id_fkey,
    ADD CONSTRAINT prompt_experiments_job_id_fkey
        FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE;

-- NB: this constraint was named `fk_credit_reservations_job_id` by
-- migration 0035, not the default `_fkey` pattern Postgres auto-generates.
ALTER TABLE credit_reservations
    DROP CONSTRAINT fk_credit_reservations_job_id,
    ADD CONSTRAINT credit_reservations_job_id_fkey
        FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE;

ALTER TABLE jobs
    DROP CONSTRAINT jobs_credit_reservation_id_fkey,
    ADD CONSTRAINT jobs_credit_reservation_id_fkey
        FOREIGN KEY (credit_reservation_id) REFERENCES credit_reservations(id) ON DELETE CASCADE;

-- DOWN:
DO $$
BEGIN
    RAISE EXCEPTION
        'migration 0045 is destructive and has no down path — use `make nuke` and re-run forward migrations';
END
$$;
