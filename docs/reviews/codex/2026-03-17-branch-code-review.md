# Code Review

- Target: `feature/story-2-2-auth-social-login` vs `origin/dev`
- Date: `2026-03-17`
- Skills used: `workflows-review`, `security-sentinel`, `architecture-strategist`, `code-simplicity-reviewer`

## Findings

### P1

1. `glow_up_jobs` is created twice with incompatible schemas, so a fresh migration run will fail before the branch can boot.
   Evidence: `app/migrations/0001_initial.sql:68-93` already creates `glow_up_jobs` with `before_image_id` / `after_image_id`. `app/migrations/0006_glow_up_jobs.sql:4-39` tries to create the table again with `original_image_id` / `generated_image_id`. `app/migrations/run.py:217-219` applies every numbered SQL file in order, so `0006` will hit `CREATE TABLE glow_up_jobs` on an existing table.
   Impact: fresh environments cannot apply the branch schema, and the runtime code is now coupled to column names that do not match the table created by `0001_initial.sql`.
   Recommendation: turn `0006_glow_up_jobs.sql` into an additive migration (`ALTER TABLE ...`) or remove the duplicate table definition, then align the runtime code and schema on one canonical column set.

2. Background jobs queued on `default` are never consumed by any registered ARQ worker.
   Evidence: `app/api/social.py:396-400` enqueues `persist_reaction` on `_queue_name="default"`. `app/api/analyses.py:127-130` enqueues `schedule_post_analysis_nudge` on the same queue. The only worker config in `app/generation/worker_settings.py:51-65` registers `functions = [process_generation_job]` and listens only to `generation:premium`, `generation:credit`, and `generation:trial`.
   Impact: reactions never get persisted to Postgres, optimistic Redis counts decay after TTL, and post-analysis nudges never fire.
   Recommendation: either register these functions in a worker that reads `default`, or move them onto a queue that an existing worker actually consumes.

3. Cancelled generation jobs can still execute after the API reports success to the user.
   Evidence: `app/api/generation.py:526-550` marks the job `cancelled`, releases the reservation, and returns success immediately. But `app/generation/worker.py:81-163` unconditionally flips any dequeued job to `processing` and starts generation without checking whether the row was already cancelled.
   Impact: a user can cancel, get a refund, and still have GPU work continue in the background; status can be overwritten from `cancelled` to `completed`/`failed`, and credit-release/commit races become possible.
   Recommendation: make the worker claim the job with a conditional update (`WHERE status = 'queued'`) or re-read and abort immediately when the persisted status is already terminal.

### P2

4. Posts persist expiring signed Supabase URLs, so feed and share-card images rot after one hour.
   Evidence: `app/config.py:57` sets `SIGNED_URL_EXPIRY_SECONDS = 3600`. `app/api/posts.py:123-139` creates signed URLs and stores them directly in `posts.before_image_url` / `posts.after_image_url`. Later reads in `app/api/social.py:103-104` and `app/api/public.py:146-147` return those stored URLs verbatim.
   Impact: older posts will start returning broken images in the feed and public cards as soon as the stored signatures expire.
   Recommendation: store stable storage keys in the database and mint fresh signed URLs at read time, or move post assets to a public/CDN-backed path that does not require per-request signatures.

5. Social login can succeed while leaving the user without a corresponding `users` row.
   Evidence: `app/api/auth.py:448-451` derives the username from the email prefix, so two different social accounts like `alice@gmail.com` and `alice@company.com` both collapse to `alice`. The subsequent `upsert` only conflicts on `id` (`app/api/auth.py:456-468`), and any insert failure is logged but treated as non-fatal (`app/api/auth.py:469-476`).
   Impact: the client receives a valid session for an account that may have no profile row, no default tier row, and no usable state for downstream endpoints.
   Recommendation: guarantee unique usernames during social provisioning and fail login if profile provisioning does not complete.

6. Credit reservations leak when the worker aborts in its pre-flight guard rails.
   Evidence: `app/generation/worker.py:62-79` handles emergency-stop and circuit-open cases by marking the job failed and returning early. Those paths run before `job_data` is loaded and never call `_fail_job`, so `credit_reservation_id` is never released.
   Impact: credit-based users can permanently lose a reservation whenever the worker refuses to start work because of an operational circuit-breaker condition.
   Recommendation: fetch the job first and funnel all failure exits through a single helper that releases reservations and updates `usage_events` consistently.

## Verification

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q`
- Result: `12 skipped`, `0 failed`
- Note: plain `pytest -q` in this workspace loads unrelated global plugins and fails before reaching this repo's tests.
