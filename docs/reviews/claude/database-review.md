# Database Review

- Date: 2026-03-17
- Scope: migrations (0001-0012), queries, indexes, RLS, Supabase usage
- Reviewer: Database Optimizer agent
- Files reviewed:
  - `app/migrations/0001_initial.sql` through `0012_drop_legacy_image_columns.sql`
  - `app/entitlement/ledger.py`
  - `app/entitlement/tier_repo.py`
  - `app/entitlement/usage_repo.py`
  - `app/api/social.py`
  - `app/api/posts.py`
  - `app/api/generation.py`
  - `app/generation/worker.py`
  - `app/api/webhooks.py`

---

## Schema Analysis

**Tables (15):** users, tiers, images, analyses, credit_reservations, glow_up_jobs, credit_ledger, subscriptions, posts, reactions, comments, shareable_cards, reports, processed_webhook_events, usage_events, prompt_experiments, user_memories, advisor_conversations, advisor_messages, advisor_nudges.

**Conventions observed:**
- UUID primary keys with `gen_random_uuid()` -- good.
- `TIMESTAMPTZ` used throughout -- good.
- Soft deletes via `is_deleted` (posts, comments) and `deleted_at` (users) -- good.
- `created_at` / `updated_at` audit columns present on most tables -- good.
- CHECK constraints on status/type enums -- good.
- Foreign keys present on all relationships -- good.

**Conventions missing:**
- `updated_at` missing from: images, credit_ledger (append-only, acceptable), reactions, comments, reports, processed_webhook_events, usage_events, prompt_experiments. For append-only tables (credit_ledger, usage_events, processed_webhook_events) this is fine. For others (images, reports) it should be added.
- No trigger for auto-updating `updated_at` on any table. Application code sets it manually, which is error-prone.

---

## Index Coverage

### Indexes Present (26 total)

| Table | Index | Columns | Type |
|---|---|---|---|
| users | idx_users_username | (username) | B-tree |
| users | idx_users_guest_token | (guest_session_token) WHERE NOT NULL | Partial B-tree |
| users | idx_users_username_reserved | (username, deleted_at, username_reserved_until) WHERE deleted_at IS NOT NULL | Partial B-tree |
| images | idx_images_user_status | (user_id, status) | B-tree |
| images | idx_images_moderation | (status) WHERE status IN ('pending','quarantined') | Partial B-tree |
| images | idx_images_cleared | (id) WHERE status = 'cleared' | Partial B-tree |
| analyses | idx_analyses_user_id | (user_id, created_at DESC) | B-tree |
| credit_reservations | idx_reservations_user_status | (user_id, status) | B-tree |
| glow_up_jobs | idx_jobs_user_id | (user_id, created_at DESC) | B-tree |
| glow_up_jobs | idx_jobs_status | (status) WHERE status IN ('pending','queued','processing') | Partial B-tree |
| glow_up_jobs | idx_jobs_watchdog | (updated_at) WHERE status = 'processing' | Partial B-tree |
| glow_up_jobs | idx_glow_up_jobs_queue_lane | (queue_lane, created_at DESC) WHERE status IN ('pending','queued') | Partial B-tree |
| credit_ledger | idx_ledger_user_id | (user_id, created_at DESC) | B-tree |
| subscriptions | idx_subscriptions_user | (user_id) WHERE status = 'active' | Partial B-tree |
| posts | idx_posts_user | (user_id, created_at DESC) WHERE NOT is_deleted | Partial B-tree |
| posts | idx_posts_feed_newest | (created_at DESC) WHERE NOT is_deleted | Partial B-tree |
| posts | idx_posts_feed_trending | (reaction_count DESC, created_at DESC) WHERE NOT is_deleted | Partial B-tree |
| comments | idx_comments_post | (post_id, created_at ASC) WHERE NOT is_deleted | Partial B-tree |
| shareable_cards | idx_cards_slug | (slug) | B-tree |
| usage_events | idx_usage_events_job_id | (job_id) WHERE job_id IS NOT NULL | Partial unique |
| usage_events | idx_usage_events_user_action_time | (user_id, action, created_at DESC) | B-tree |
| prompt_experiments | idx_prompt_exp_mode | (prompt_mode, created_at DESC) | B-tree |
| user_memories | idx_user_memories_user_id | (user_id) | B-tree |
| user_memories | idx_user_memories_embedding | USING ivfflat (embedding vector_cosine_ops) | IVFFlat |
| advisor_conversations | idx_advisor_conversations_user | (user_id, created_at DESC) | B-tree |
| advisor_messages | idx_advisor_messages_conv | (conversation_id, created_at ASC) | B-tree |
| advisor_nudges | idx_advisor_nudges_user | (user_id, created_at DESC) | B-tree |

---

## Query Patterns

### Feed Queries (social.py)
- **Newest**: `v_feed_posts` view + `ORDER BY created_at DESC` + cursor. Uses `idx_posts_feed_newest`. Good.
- **Trending**: `feed_trending()` RPC. CTE with 7-day filter + HN-decay score. Acceptable for moderate volume.
- **Biggest improvements**: `feed_biggest_improvements()` RPC. Uses `idx_posts_feed_trending`. Good.

### Comment Listing (posts.py)
- `comments` table with foreign join `users(display_name, avatar_storage_key)`. Uses `idx_comments_post`. Good -- single query with Supabase join, no N+1.

### Usage Counting (usage_repo.py)
- `count_in_window()`: filters on (user_id, action, status, created_at >= cutoff). Index `idx_usage_events_user_action_time` covers (user_id, action, created_at) but `status` is not in the index.

### Credit Balance (ledger.py)
- `sum_credit_balance` RPC -- SUM(delta) over credit_ledger WHERE user_id = ?. Uses `idx_ledger_user_id`. Good.

### Job Status Polling (generation.py)
- Single-row fetch by PK (`id`). Fine.
- Completed jobs fetch 2 extra image rows by PK. Fine for single-job polling.

### Webhook Idempotency (webhooks.py)
- INSERT into `processed_webhook_events` with UNIQUE(provider, event_id). Catches duplicate on constraint violation. Correct pattern.

### Worker (worker.py)
- Conditional UPDATE `WHERE status = 'queued'` for job claim -- prevents double-processing. Good.
- Watchdog: `WHERE status = 'processing' AND updated_at < threshold`. Uses `idx_jobs_watchdog`. Good.

---

## Findings

### Critical

**C1. No Row-Level Security (RLS) on any table.**

Zero `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` statements exist across all 12 migrations. Per the project's own `database-patterns.md` rule: "Always enable RLS for multi-tenant tables. No exceptions."

Tables that store user-scoped data and MUST have RLS:
- `users`, `images`, `analyses`, `credit_reservations`, `glow_up_jobs`, `credit_ledger`, `subscriptions`, `posts`, `reactions`, `comments`, `reports`, `usage_events`, `user_memories`, `advisor_conversations`, `advisor_messages`, `advisor_nudges`

Without RLS, any client with the Supabase anon key can read/write ALL rows in ALL tables directly via PostgREST. This is a data breach vector.

**Impact:** Any user can read any other user's credit balance, generation jobs, private messages, and PII. Any user can modify any other user's data.

**Fix:** Create migration 0013 that enables RLS + FORCE RLS on every user-scoped table, with policies:
- `USING (auth.uid() = user_id)` for user-owned tables
- Service role bypass for backend RPCs/webhooks
- Read-only public access for `posts` (WHERE NOT is_deleted) and `comments` (WHERE NOT is_deleted)

---

**C2. Credit ledger RPCs (`sum_credit_balance`, `credit_reserve`, `credit_release`, `credit_commit`) are referenced in code but have no migration.**

`app/entitlement/ledger.py` calls four RPCs:
- `sum_credit_balance` (line 45)
- `credit_reserve` (line 68)
- `credit_release` (line 87)
- `credit_commit` (line 109)

None of these functions exist in any migration file. A grep for these names across all `.sql` files returns zero results.

**Impact:** The credit system is non-functional in any fresh deployment. `ledger.reserve()`, `ledger.release()`, `ledger.commit()`, and `ledger.balance()` will all throw runtime errors.

**Fix:** Create a migration with the four `CREATE FUNCTION` statements. These must be `SECURITY DEFINER` functions that operate atomically (single transaction for multi-table writes).

---

### High

**H1. `persist_reaction` in social.py is not transactional -- INSERT + RPC are two separate calls.**

`persist_reaction()` (line 330-334) does:
1. `INSERT INTO reactions` (Supabase client call)
2. `increment_reaction_count` RPC (separate call)

If step 2 fails, the reaction row exists but the counter is never incremented. The reconciliation job (`reconcile_reaction_counts`) runs nightly, so the counter can be stale for up to 48 hours.

**Impact:** Under load or transient failures, `posts.reaction_count` drifts from actual count. Feed ranking (trending, biggest_improvements) uses this cached counter, so rankings become inaccurate.

**Fix:** Combine the INSERT and counter increment into a single RPC that does both in one transaction. Or add a database trigger on `reactions` INSERT that auto-increments `posts.reaction_count`.

---

**H2. `create_comment` in posts.py has the same two-call non-transactional pattern.**

`create_comment()` (lines 242-252) does:
1. `INSERT INTO comments`
2. `increment_comment_count` RPC

Same issue as H1. If step 2 fails, `posts.comment_count` is stale.

**Fix:** Same approach -- combine into a single RPC or use a trigger.

---

**H3. Webhook handler `_handle_checkout_completed` does non-transactional multi-table writes.**

Lines 126-138 in `webhooks.py`:
1. INSERT into `credit_ledger` (credit purchase)
2. SELECT user's `tier_id`
3. UPDATE user's `tier_id` to CREDIT_HOLDER

Three separate Supabase calls with no transaction. A failure between step 1 and step 3 means credits are granted but the tier is not upgraded. Similarly, `_handle_subscription_deleted` does:
1. SELECT subscription
2. UPDATE subscription status
3. Compute balance
4. UPDATE user tier

Four separate calls. A partial failure leaves the system in an inconsistent state.

**Impact:** Tier/credit inconsistency on transient errors. User gets credits but stays on free tier, or subscription expires but tier is not downgraded.

**Fix:** Wrap each handler's multi-step logic in a single Postgres function (RPC) that executes in one transaction.

---

**H4. `usage_events` references `auth.users(id)` instead of `public.users(id)`.**

Migration 0003 (line 8):
```sql
user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
```

Every other table references `public.users(id)`. This creates an inconsistency: `usage_events` is FK-constrained to Supabase Auth's internal `auth.users` table, while the rest of the schema uses the application's `public.users` table.

**Impact:** If a user exists in `public.users` but has been deleted from `auth.users` (or vice versa), FK constraints behave differently for `usage_events` vs. all other tables. This also means the ON DELETE CASCADE on `usage_events` fires when the auth user is deleted, not when the application user record is deleted.

**Fix:** Change to `REFERENCES users(id) ON DELETE CASCADE` (referencing `public.users`) for consistency. Requires a migration to drop and re-add the constraint.

---

### Medium

**M1. `usage_events` index does not cover the `status` filter used in queries.**

`usage_repo.py` filters on `(user_id, action, status='committed', created_at >= cutoff)`.
The index `idx_usage_events_user_action_time` is `(user_id, action, created_at DESC)`.

The `status` column is not in the index, so Postgres must do a filter (not an index scan) on `status` for every row matched by the first three columns. With high usage volume, this degrades.

**Fix (ESR rule):** Replace with a composite index following Equality-Sort-Range:
```sql
CREATE INDEX idx_usage_events_user_action_status_time
  ON usage_events(user_id, action, status, created_at DESC);
```
Or add a partial index:
```sql
CREATE INDEX idx_usage_events_committed
  ON usage_events(user_id, action, created_at DESC)
  WHERE status = 'committed';
```

---

**M2. `v_feed_posts` view joins `images` twice by PK but the `idx_images_cleared` index is on `(id) WHERE status = 'cleared'`.**

The view (0010, lines 8-23):
```sql
JOIN images bi ON bi.id = p.before_image_id AND bi.status = 'cleared'
JOIN images ai ON ai.id = p.after_image_id AND ai.status = 'cleared'
```

This is a PK lookup (`images.id` is the PK) plus a filter on `status`. The PK index already gives O(1) lookup, and the `WHERE status = 'cleared'` partial index on `id` is redundant for this pattern (PK lookup is already fast). The partial index is not harmful but provides no benefit for this join pattern.

**Impact:** Minor -- no performance issue, just a dead index consuming storage and write overhead.

**Fix:** Consider dropping `idx_images_cleared` if no other query benefits from it. The PK index handles the join; the status filter is a cheap post-fetch check on a single row.

---

**M3. `reactions` table has no index on `post_id` alone (only UNIQUE constraints).**

The `reactions` table has:
- `UNIQUE (post_id, user_id)` -- creates an implicit index
- `UNIQUE (post_id, guest_session_token)` -- creates an implicit index

The `reconcile_reaction_counts` function (0011) does:
```sql
SELECT post_id, COUNT(*) FROM reactions WHERE post_id IN (...) GROUP BY post_id
```

The two UNIQUE indexes both have `post_id` as the leading column, so this query can use either. This is adequate.

However, `reactions` has no explicit index for `WHERE created_at >= cutoff_iso` (used in the subquery of `reconcile_reaction_counts`). At scale, this subquery does a sequential scan:
```sql
SELECT DISTINCT post_id FROM reactions WHERE created_at >= cutoff_iso
```

**Fix:** Add an index on `reactions(created_at)` or `reactions(created_at, post_id)` to support the reconciliation subquery.

---

**M4. `reports` table has no indexes at all.**

No index on `post_id`, `reporter_user_id`, or `status`. Admin queries to find reports by post or by status will require sequential scans.

**Fix:**
```sql
CREATE INDEX idx_reports_post ON reports(post_id);
CREATE INDEX idx_reports_status ON reports(status, created_at DESC);
```

---

**M5. `glow_up_jobs.idempotency_key` UNIQUE index exists (from UNIQUE constraint) but the idempotency lookup in `generation.py` filters on BOTH `idempotency_key` AND `user_id`.**

Line 253-258 in `generation.py`:
```python
.eq("idempotency_key", body.idempotency_key)
.eq("user_id", user_id_str)
```

The UNIQUE constraint is only on `idempotency_key` alone. Adding `user_id` to the filter is defensive (good), but since the UNIQUE index is on `idempotency_key` alone, the index scan is efficient. No action needed -- noted for completeness.

---

**M6. `idx_posts_feed_trending` partial index does not match the `feed_trending()` function's 7-day filter.**

The index is: `(reaction_count DESC, created_at DESC) WHERE NOT is_deleted`

The `feed_trending()` function filters: `WHERE fp.created_at >= NOW() - INTERVAL '7 days'` (via `v_feed_posts` which also filters `NOT is_deleted`).

The function's 7-day window means it scans a subset of the partial index, which is fine. But the ORDER BY is `trending_score DESC, created_at DESC, id ASC` -- a computed column that cannot use any existing index. The CTE computes `trending_score` for ALL posts in the 7-day window, then sorts.

**Impact:** At 10K+ posts per week, the CTE materializes all scored rows before applying the LIMIT. Postgres cannot push the LIMIT into the CTE.

**Fix:** For now, the 7-day window bounds the dataset. Monitor. If the 7-day window grows beyond 50K posts, consider a materialized view refreshed periodically, or a `trending_score` column maintained by a trigger/cron.

---

**M7. IVFFlat index on `user_memories.embedding` created before data exists.**

Migration 0007 creates an IVFFlat index:
```sql
CREATE INDEX idx_user_memories_embedding ON user_memories USING ivfflat (embedding vector_cosine_ops);
```

IVFFlat indexes require data to build meaningful cluster centroids. Creating the index on an empty table produces an index with no useful clusters. The index must be rebuilt after sufficient data exists (typically 1000+ rows).

**Fix:** Either:
1. Use HNSW instead of IVFFlat (`USING hnsw`) -- HNSW does not require pre-existing data.
2. Document that the IVFFlat index must be `REINDEX`ed after the first 1000+ rows are inserted.

---

### Low

**L1. `shareable_cards.slug` has both a UNIQUE constraint (from table def) and a separate B-tree index `idx_cards_slug`.**

The UNIQUE constraint already creates an implicit B-tree index. The explicit `idx_cards_slug` is redundant.

**Fix:** Drop `idx_cards_slug`.

---

**L2. `users.username` has both a UNIQUE constraint and `idx_users_username`.**

Same issue as L1. The UNIQUE constraint already creates an implicit index.

**Fix:** Drop `idx_users_username`.

---

**L3. Migration 0006 DOWN section is commented out.**

The rollback SQL for migration 0006 (glow_up_jobs extensions) is entirely in SQL comments (lines 82-109). While the project convention includes DOWN sections, having it commented out means automated rollback tooling cannot parse it.

**Fix:** Ensure the rollback runner can parse commented-down sections, or move the DOWN SQL into a separate file or a clearly delimited block.

---

**L4. `prompt_experiments.job_id` FK has no index.**

`prompt_experiments` has `job_id UUID NOT NULL REFERENCES glow_up_jobs(id)` but no index on `job_id`. Queries that join from `glow_up_jobs` to `prompt_experiments` or filter by `job_id` will seq-scan.

**Fix:**
```sql
CREATE INDEX idx_prompt_exp_job ON prompt_experiments(job_id);
```

---

**L5. No `decrement_comment_count` function exists.**

`increment_comment_count` exists (migration 0008) but there is no corresponding `decrement_comment_count`. If a comment is soft-deleted, the `comment_count` on the post is never decremented. The only way to correct it is manual SQL.

**Fix:** Create a `decrement_comment_count` function and call it when soft-deleting comments. Or add a reconciliation function similar to `reconcile_reaction_counts`.

---

**L6. `subscriptions` table lookup by `provider_subscription_id` has no explicit index.**

Multiple webhook handlers query:
```python
.eq("provider_subscription_id", sub_id)
```

The column has a UNIQUE constraint (`provider_subscription_id TEXT UNIQUE NOT NULL`), which creates an implicit index. This is fine. Noted for completeness only.

---

## Migration Safety

| Migration | Additive | Reversible (DOWN) | Table lock risk | Notes |
|---|---|---|---|---|
| 0001 | Yes (CREATE TABLE) | Yes | None (new tables) | Good |
| 0002 | Yes (CREATE TABLE + ALTER ADD COLUMN) | Yes | Minimal (ADD COLUMN) | Good |
| 0003 | Yes (CREATE TABLE) | Yes | None | FK references `auth.users` -- see H4 |
| 0004 | Data + ALTER | Partial | ALTER SET NOT NULL acquires ACCESS EXCLUSIVE lock | Lock on `users` table -- brief if table is small |
| 0005 | Yes (ADD COLUMN + CREATE INDEX) | Yes | Minimal | Good |
| 0006 | Yes (ADD COLUMNS + CREATE INDEX) | Commented out | Minimal | See L3 |
| 0007 | Yes (CREATE TABLE + EXTENSION + FUNCTION) | Yes | None | IVFFlat on empty table -- see M7 |
| 0008 | Yes (CREATE FUNCTION) | No DOWN | None | No rollback defined |
| 0009 | Yes (CREATE FUNCTION) | No DOWN | None | No rollback defined |
| 0010 | Yes (CREATE VIEW + FUNCTIONS + INDEX) | Commented out | None | Good design |
| 0011 | Yes (CREATE FUNCTIONS) | No DOWN | None | No rollback defined |
| 0012 | Destructive (DROP COLUMN) | Commented out | ACCESS EXCLUSIVE lock | Drops columns -- needs code deploy first |

**Concern:** Migrations 0008, 0009, 0011 have no DOWN/rollback section at all. This violates the project's own database-patterns rule: "Always include down/rollback -- every up migration has a corresponding down."

---

## Summary

**Critical (2):**
1. **No RLS anywhere** -- the entire database is unprotected against direct client access via Supabase anon key. This is the single highest-priority fix.
2. **Missing credit ledger RPCs** -- four functions called by application code do not exist in any migration. The credit system cannot function on a fresh deployment.

**High (4):**
1. Non-transactional reaction persist (INSERT + RPC as two calls)
2. Non-transactional comment insert + counter increment
3. Non-transactional webhook multi-table writes (credit purchase, subscription lifecycle)
4. `usage_events` FK references `auth.users` instead of `public.users`

**Medium (7):**
1. `usage_events` index missing `status` column (violates ESR rule)
2. Redundant `idx_images_cleared` index
3. Missing `reactions(created_at)` index for reconciliation
4. `reports` table has zero indexes
5. Trending feed CTE cannot use indexes for computed score
6. IVFFlat index created on empty table (ineffective clusters)
7. Idempotency key index observation (no action needed)

**Low (6):**
1. Redundant `idx_cards_slug` (UNIQUE already indexes)
2. Redundant `idx_users_username` (UNIQUE already indexes)
3. Migration 0006 DOWN commented out
4. `prompt_experiments.job_id` missing index
5. No `decrement_comment_count` function
6. Migrations 0008/0009/0011 missing DOWN sections

**Overall assessment:** The schema design is solid -- good use of partial indexes, appropriate constraints, and well-designed feed functions. The two critical gaps (no RLS, missing credit RPCs) are deployment blockers. The transactional safety issues (H1-H3) will cause data inconsistency under load and should be addressed before scaling beyond a few hundred concurrent users.
