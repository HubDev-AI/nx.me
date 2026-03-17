# Skipped Review Findings — Prioritization Backlog

Generated: 2026-03-17
Source: 8 review files in `docs/reviews/claude/`
Status: All items below were NOT fixed in the review sweep. Grouped by effort/category for prioritization.

---

## Quick Fixes (Trivial — under 30 minutes each)

### QF-1: DELETE /posts returns 200 instead of 204
- **Source:** API Design Review, F-SC1 (Moderate)
- **File:** `app/api/posts.py:177`
- **Detail:** `@router.delete("/posts/{post_id}", status_code=status.HTTP_200_OK)` returns 200 with `{"status": "deleted"}`. A successful deletion with no meaningful body should return 204. The "already deleted" case returns 200 with `{"status": "already_deleted"}` — should be 409 Conflict, consistent with how `DELETE /auth/account` handles the same scenario.
- **Fix:** Change `status_code=200` to `status_code=204`, return `Response(status_code=204)` on success, return 409 for already-deleted case.

### QF-2: POST /credits/purchase returns 200 instead of 201
- **Source:** API Design Review, F-SC2 (Moderate)
- **File:** `app/api/entitlement.py:135`
- **Detail:** The endpoint creates a checkout session (a resource) but returns 200. Should return 201 Created. Same issue applies to `POST /v1/subscriptions` when it creates a checkout session.
- **Fix:** Add `status_code=status.HTTP_201_CREATED` to the decorator.

### QF-3: POST /jobs/{id}/cancel missing explicit status_code
- **Source:** API Design Review, F-SC5 (Minor)
- **File:** `app/api/generation.py:472`
- **Detail:** The `@router.post` decorator has no explicit `status_code`. FastAPI defaults to 200 (correct here), but the missing annotation reduces explicitness and OpenAPI documentation quality.
- **Fix:** Add `status_code=status.HTTP_200_OK` to the decorator.

### QF-4: Empty SubscriptionRequest model
- **Source:** API Design Review, F-M1 (Moderate)
- **File:** `app/api/entitlement.py:185-186`
- **Detail:** `class SubscriptionRequest(BaseModel): pass` is vestigial. The endpoint takes no body. Either it needs fields or should be removed entirely.
- **Fix:** Remove the class and remove the body parameter from the endpoint if it references this model.

### QF-5: _SOUL_MD read at import time with no error guard
- **Source:** Python Review, LOW-1; Architecture Review, L-2
- **File:** `app/advisor/service.py:48`
- **Detail:** `_SOUL_MD: str = _SOUL_MD_PATH.read_text(encoding="utf-8")` at module level. If the file doesn't exist, it crashes with `FileNotFoundError` during import — no clear error message. Tests importing `AdvisorService` without the file present will also fail.
- **Fix:** Wrap in try/except with a clear `RuntimeError("SOUL.md not found at {path}")` message, or validate in a startup health check.

### QF-6: Logout 502 response uses non-standard error shape
- **Source:** Security Review, M-1
- **File:** `app/api/auth.py:523-527`
- **Detail:** The 502 response on revocation failure uses `{"error": {"code": "REVOCATION_FAILED", "message": "..."}}` nested inside FastAPI's `detail` key, creating `{"detail": {"error": {...}}}`. Other endpoints use plain string `detail`. The inconsistency confuses client error handling.
- **Fix:** Normalize to match the rest of the API's error format.

### QF-7: ValueError raised for rate limit instead of custom exception
- **Source:** Architecture Review, M-1
- **File:** `app/advisor/content_filter.py:85`
- **Detail:** `raise ValueError("RATE_LIMIT_EXCEEDED")` for a business rule. The handler must catch this and convert to HTTP 429. Using `ValueError` conflates input validation with rate limiting and makes the caller responsible for knowing this string is not a real validation error.
- **Fix:** Define `class RateLimitExceeded(Exception): pass` in the advisor module. Raise that instead. Handler maps it to 429.

### QF-8: display_name accepts HTML characters
- **Source:** Security Review, L-1
- **File:** `app/api/auth.py:57`
- **Detail:** `display_name: str = Field(min_length=1, max_length=50)` accepts arbitrary Unicode including `<`, `>`, `"`. Currently harmless for mobile-only rendering, but the `/public/cards/{username}` endpoint returns `display_name` in JSON consumed by the Next.js card-web. If display names are ever interpolated into HTML without escaping, this becomes XSS.
- **Fix:** Add a Pydantic validator that strips or rejects `<`, `>`, `"` characters. Easier to enforce early than retroactively clean stored data.

### QF-9: TypingIndicator animation ignores reduced motion
- **Source:** UI/UX Review, AN-3 (Minor)
- **File:** `mobile/components/advisor/TypingIndicator.tsx:17-40`
- **Detail:** The bouncing dot animation runs in a loop unconditionally. Should display a static "..." when `AccessibilityInfo.isReduceMotionEnabled()` is true.
- **Fix:** Add reduced-motion check. When enabled, render static dots instead of animated ones.

---

## Low Effort (1–3 hours each)

### LE-1: 429 responses missing Retry-After headers
- **Source:** API Design Review, F-R1 (Moderate)
- **Files:** `app/api/social.py` (reaction rate limit), `app/api/auth.py` (registration/login rate limit), `app/advisor/content_filter.py` (advisor rate limit)
- **Detail:** None of the 429 responses include `Retry-After` or `X-RateLimit-*` headers. RFC 6585 recommends `Retry-After` on 429 responses. Clients have no machine-readable signal for when to retry.
- **Fix:** Calculate remaining TTL from Redis key expiry. Add `Retry-After: {seconds}` header to all 429 responses.

### LE-2: Timestamp-only cursor collision risk
- **Source:** API Design Review, F-P1 (Moderate)
- **Files:** `app/api/posts.py` (comments endpoint ~line 316), `app/api/users.py` (history endpoint)
- **Detail:** Comments and history endpoints use a single `created_at` ISO timestamp as the cursor. If two records share the same timestamp, the cursor will skip or repeat records. The trending feed correctly uses composite cursors (`value|created_at|id`). The same `created_at|id` composite should apply here.
- **Fix:** Change cursor format to `{created_at}|{id}`, parse both components, add `id` to the ORDER BY and WHERE clause.

### LE-3: Default tier query duplicated in auth.py
- **Source:** Code Quality Review, D-4 (Medium)
- **File:** `app/api/auth.py:161-176, 430-446`
- **Detail:** The query `supabase.table("tiers").select("id").eq("is_default", True).eq("is_active", True).single().execute()` appears twice — in `register()` and `social_login()`. The `TierRepository.get_default()` method already exists for this.
- **Fix:** Import and use `TierRepository.get_default()`, or extract a shared `_fetch_default_tier_id(supabase)` helper.

### LE-4: Redis reaction counter SET-then-INCR drift
- **Source:** Python Review, HIGH-4
- **File:** `app/api/social.py:296-299`
- **Detail:** On cache miss, the code does `SET` (seeding from DB) then `INCR`. Between SET and INCR, a concurrent request can INCR on the freshly-set value. The nightly reconciliation corrects this, but counters can drift for up to 48h. Also, popular posts' keys can live indefinitely with accumulating drift if `persist_reaction` ARQ jobs fail.
- **Fix:** Use `INCR` exclusively (no `SET` for warm-up). On cache miss, use `SET NX` to avoid overwriting an existing counter.

### LE-5: Login rate limit shares registration tuning constants
- **Source:** Security Review, L-3
- **File:** `app/services/rate_limiter.py:73-76`
- **Detail:** `check_login_rate_limit` reuses `REGISTRATION_IP_LIMIT` (4) and `REGISTRATION_IP_WINDOW_SECONDS` (3600). Login may need a tighter window (e.g., 10 attempts per 15 minutes for credential-stuffing resistance) but cannot be tuned independently.
- **Fix:** Add `LOGIN_IP_LIMIT` and `LOGIN_IP_WINDOW_SECONDS` settings with independent defaults.

### LE-6: `prompts/keyword_allowlist.py` imported as top-level package
- **Source:** Python Review, LOW-7
- **File:** `app/generation/prompt_builder.py:110, 159`
- **Detail:** `from prompts.keyword_allowlist import HAIR_KEYWORDS` uses a top-level `prompts` package (relative to working directory), not `app.prompts`. Breaks if working directory isn't repo root. Imports are inside functions (deferred), masking breakage until generation time.
- **Fix:** Move imports to module top (fail fast). Move `prompts/` under `app/`, or add repo root to `sys.path` in worker entry.

### LE-7: Rolling average cost math is wrong
- **Source:** Architecture Review, M-4
- **File:** `app/generation/cost_tracker.py:71`
- **Detail:** `return total_cost / max(bucket_count * 10, 1)` divides by `bucket_count * 10`, assuming 10 generations per hourly bucket — a magic number with no basis in actual volume. Produces unreliable averages that can over-throttle or under-throttle trial users.
- **Fix:** Track generation count alongside cost in Redis (separate counter per bucket). Compute `total_cost / total_count`.

### LE-8: Weak advisor repetition detection
- **Source:** Python Review, MEDIUM-9
- **File:** `app/advisor/service.py:483-485`
- **Detail:** `_post_check` compares only the first 3 words of the latest response against the last advisor message. Two completely different messages can share a 3-word opener (e.g., "I think you"). Only checks against the most recent message, not a sliding window.
- **Fix:** Use a more robust signal — e.g., compare first sentence, or check cosine similarity of the full message against the last N responses.

### LE-9: ESLint missing @typescript-eslint/strict
- **Source:** Next.js Review, M-2
- **File:** `card-web/.eslintrc.json`
- **Detail:** Extends only `next/core-web-vitals` and `next/typescript`. Per project rules, `@typescript-eslint/strict` should also be included. Missing rules allow unsafe `any` casts, unconstrained generics, and non-null assertions. `eslint-plugin-import` is also absent.
- **Fix:** Add `@typescript-eslint/strict` to extends. Install and configure `eslint-plugin-import`.

### LE-10: Inter font not loaded via next/font
- **Source:** Next.js Review, M-8
- **File:** `card-web/src/app/globals.css:11`, `card-web/tailwind.config.ts:60`
- **Detail:** `--font-inter: 'Inter', system-ui, sans-serif` is a plain CSS variable. No Google Fonts `<link>`, no `next/font/google` import, no self-hosted font. Inter will not load — browser falls back to system-ui. If Inter is the brand font, it must be loaded via `next/font/google` (zero CLS, auto size-adjust).
- **Fix:** Use `next/font/google` to import Inter, or remove the CSS variable if system-ui fallback is intentional.

### LE-11: Advisor screen not reachable from tab bar
- **Source:** UI/UX Review, N-4 (Moderate)
- **File:** `mobile/app/advisor/index.tsx`, `mobile/app/(tabs)/_layout.tsx`
- **Detail:** The advisor screen exists at route `/advisor` but there is no tab bar item, profile link, or other visible navigation to reach it. Users can only navigate via deep link or programmatic push.
- **Fix:** Either add a navigation entry point, or document as intentionally hidden behind a feature gate.

---

## Medium Effort (half-day each)

### ME-1: Inconsistent error response format across all endpoints
- **Source:** API Design Review, F-E1 (Significant); Architecture Review, M-2; Code Quality Review, I-3
- **Files:** All handler files in `app/api/`
- **Detail:** The codebase uses 3 error formats:
  - Format A — raw string: `"Analysis not found"` (analyses, posts, users)
  - Format B — structured: `{"error": {"code": "...", "message": "..."}}` (generation, entitlement, advisor)
  - Format C — structured inside `detail`: `{"detail": {"error": {...}}}`
  Clients must handle two response shapes for errors. FastAPI's `HTTPException` wraps `detail` under a `"detail"` key, creating `{"detail": "string"}` vs `{"detail": {"error": {...}}}`.
- **Fix:** Create a custom exception handler that normalizes all `HTTPException` and `RequestValidationError` into `{"error": {"code": "...", "message": "..."}}`. Use a `raise_api_error(code, message, status_code)` helper across all endpoints.

### ME-2: SubscriptionResponse overloaded between create/cancel
- **Source:** API Design Review, F-M2 (Moderate)
- **File:** `app/api/entitlement.py:189-192`
- **Detail:** `POST /subscriptions` and `DELETE /subscriptions` both return `SubscriptionResponse` with three optional fields: `checkout_url`, `status`, `message`. Create populates `checkout_url`; delete populates `status` + `message`. These are semantically different and should be separate models.
- **Fix:** Split into `CreateSubscriptionResponse(checkout_url: str)` and `CancelSubscriptionResponse(status: str, message: str)`.

### ME-3: recommendations typed as list[dict]
- **Source:** API Design Review, F-M3 (Moderate)
- **Files:** `app/api/public.py:36`, `app/api/users.py:48,111`
- **Detail:** `CardResponse.recommendations` and `HistoryEntry.recommendations` are `list[dict]`. OpenAPI schema generates `array of object` with no structure. Clients cannot know what fields to expect.
- **Fix:** Define a typed `RecommendationItem` model with the actual fields and use `list[RecommendationItem]`.

### ME-4: CreditLedger instantiated ad-hoc in 7+ places
- **Source:** Code Quality Review, D-5 (Low)
- **Files:** `app/api/auth.py:567`, `app/api/generation.py:277,537`, `app/generation/worker.py:304,347`, `app/api/webhooks.py:244`
- **Detail:** `CreditLedger(supabase)` is constructed fresh in 7 locations. `EntitlementService` already holds a `_ledger` instance.
- **Fix:** For API endpoints, inject via the `EntitlementService` dependency. For the worker, construct once in startup context.

### ME-5: Idempotency key in request body, not header
- **Source:** API Design Review, F-I1 (Moderate)
- **File:** `app/api/generation.py:68`
- **Detail:** `idempotency_key` field is in `GenerateRequest` body. Industry standard (Stripe, PayPal, Adyen) uses `Idempotency-Key` request header. This separates business payload from retry semantics and allows middleware/proxies to handle idempotency transparently.
- **Fix:** Accept `Idempotency-Key` header (read via `request.headers.get("Idempotency-Key")`). Keep body field for backward compatibility during migration.

### ME-6: find_milestone_eligible fetches ALL analysis_insight rows
- **Source:** Code Quality Review, S-2 (Medium)
- **File:** `app/advisor/nudge_eligibility.py:82-89`
- **Detail:** Fetches all `user_memories` of type `analysis_insight` for every milestone count in the loop. For a large user base, this is an unbounded full-table scan run daily via cron.
- **Fix:** Use a `COUNT ... GROUP BY user_id` query via Supabase RPC instead of client-side counting.

---

## Database Migrations Needed (dedicated migration work)

### DB-1: usage_events FK references auth.users instead of public.users
- **Source:** Database Review, H4 (High)
- **File:** `app/migrations/0003_usage_events.sql:7`
- **Detail:** `user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE`. Every other table references `public.users(id)`. ON DELETE CASCADE fires when the auth user is deleted, not the application user.
- **Fix:** Migration to DROP and re-ADD the FK constraint referencing `public.users(id)`.

### DB-2: usage_events index missing status column (ESR violation)
- **Source:** Database Review, M1 (Medium)
- **File:** Migration needed
- **Detail:** `idx_usage_events_user_action_time` is `(user_id, action, created_at DESC)` but queries filter on `status='committed'` too. Postgres must filter (not index scan) on `status` for every matched row.
- **Fix:** New migration:
  ```sql
  DROP INDEX idx_usage_events_user_action_time;
  CREATE INDEX idx_usage_events_committed
    ON usage_events(user_id, action, created_at DESC)
    WHERE status = 'committed';
  ```

### DB-3: reactions(created_at) index missing for reconciliation
- **Source:** Database Review, M3 (Medium)
- **Detail:** `reconcile_reaction_counts` does `SELECT DISTINCT post_id FROM reactions WHERE created_at >= cutoff_iso` — sequential scan at scale.
- **Fix:** Migration: `CREATE INDEX idx_reactions_created ON reactions(created_at, post_id);`

### DB-4: reports table has zero indexes
- **Source:** Database Review, M4 (Medium)
- **File:** `app/migrations/0001_initial.sql:187-195`
- **Detail:** No index on `post_id`, `reporter_user_id`, or `status`. Admin queries require sequential scans.
- **Fix:** Migration:
  ```sql
  CREATE INDEX idx_reports_post ON reports(post_id);
  CREATE INDEX idx_reports_status ON reports(status, created_at DESC);
  ```

### DB-5: IVFFlat index on empty table (ineffective clusters)
- **Source:** Database Review, M7 (Medium)
- **File:** `app/migrations/0007_advisor_tables.sql:21`
- **Detail:** IVFFlat requires pre-existing data for meaningful clusters. Created on empty `user_memories` table — produces useless clusters. Must be rebuilt after 1000+ rows.
- **Fix:** Migration to replace with HNSW: `DROP INDEX idx_user_memories_embedding; CREATE INDEX idx_user_memories_embedding ON user_memories USING hnsw (embedding vector_cosine_ops);`

### DB-6: Redundant indexes (UNIQUE constraint already creates B-tree)
- **Source:** Database Review, L1, L2 (Low)
- **Detail:** `idx_cards_slug` duplicates the UNIQUE constraint on `shareable_cards.slug`. `idx_users_username` duplicates the UNIQUE constraint on `users.username`.
- **Fix:** Migration: `DROP INDEX idx_cards_slug; DROP INDEX idx_users_username;`

### DB-7: prompt_experiments.job_id missing index
- **Source:** Database Review, L4 (Low)
- **Detail:** FK column `job_id` has no index. Queries joining or filtering by job_id will seq-scan.
- **Fix:** Migration: `CREATE INDEX idx_prompt_exp_job ON prompt_experiments(job_id);`

### DB-8: decrement_comment_count function missing
- **Source:** Database Review, L5 (Low)
- **Detail:** `increment_comment_count` exists (migration 0008) but no corresponding `decrement_comment_count`. Soft-deleting a comment never decrements `posts.comment_count`. Only fixable via manual SQL.
- **Fix:** Migration creating `decrement_comment_count(p_post_id UUID)` function. Call it from comment soft-delete logic.

### DB-9: Migrations 0008, 0009, 0011 missing DOWN/rollback sections
- **Source:** Database Review, L6 (Low)
- **Detail:** Project convention (database-patterns.md) requires every UP migration to have a corresponding DOWN. These three have none.
- **Fix:** Add rollback SQL to each migration file.

---

## Large Refactors (multi-day effort)

### LR-1: Sync Supabase SDK calls block async event loop
- **Source:** Architecture Review, C-1 (Critical)
- **Files:** 60+ `supabase.table(...)` calls across 10+ handler files
- **Detail:** The `supabase-py` SDK's `.execute()` is blocking I/O. When called inside `async def` handlers, it blocks the entire asyncio event loop. At 50+ concurrent users, a single slow Supabase query stalls all in-flight requests.
- **Options:**
  1. `run_in_executor` for all Supabase calls in async contexts (tactical, adds boilerplate)
  2. Switch affected handlers to `def` (simplest — loses ability to `await` Redis/ARQ in same handler)
  3. Adopt async Supabase client or `asyncpg` for hot paths (strategic)

### LR-2: Handlers directly access database — no repository layer
- **Source:** Architecture Review, C-2 (Critical)
- **Files:** `app/api/auth.py` (10 calls), `generation.py` (10), `posts.py` (12), `social.py` (3), `users.py` (6), `webhooks.py` (11)
- **Detail:** No repository classes for `users`, `glow_up_jobs`, `analyses`, `images`, `posts`, `comments`, `reports`, `subscriptions`, `processed_webhook_events`. Each handler builds its own query inline. Query logic is duplicated, schema changes require touching multiple files, testing requires mocking Supabase at transport level.
- **Fix:** Extract repositories per domain: `UserRepository`, `JobRepository`, `AnalysisRepository`, `PostRepository`, `ImageRepository`.

### LR-3: No Row-Level Security (RLS) on any table
- **Source:** Database Review, C1 (Critical)
- **Files:** All 12 migrations
- **Detail:** Zero `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` statements. Without RLS, any client with the Supabase anon key can read/write ALL rows in ALL tables directly via PostgREST. This is a data breach vector.
- **Fix:** Create migration 0013 with RLS + FORCE RLS on every user-scoped table, with `USING (auth.uid() = user_id)` policies, service role bypass, and read-only public access for posts/comments.

### LR-4: Missing credit ledger RPCs (credit system non-functional on fresh deploy)
- **Source:** Database Review, C2 (Critical)
- **Files:** `app/entitlement/ledger.py` references `sum_credit_balance`, `credit_reserve`, `credit_release`, `credit_commit` — none exist in any migration.
- **Fix:** Create migration with four `CREATE FUNCTION` statements. Must be `SECURITY DEFINER` functions operating atomically.

### LR-5: Non-transactional multi-step DB writes
- **Source:** Database Review, H1 (reactions), H2 (comments), H3 (webhooks)
- **Detail:**
  - `persist_reaction`: INSERT + `increment_reaction_count` RPC as two separate calls. Counter drifts on failure.
  - `create_comment`: INSERT + `increment_comment_count` as two calls. Same issue.
  - `_handle_checkout_completed`: INSERT credit_ledger + SELECT user + UPDATE tier as three calls. Partial failure leaves inconsistent state.
- **Fix:** Combine each into a single Postgres function (RPC) executing in one transaction, or use DB triggers.

### LR-6: process_generation_job is 290 lines
- **Source:** Code Quality Review, CX-1 (Critical)
- **File:** `app/generation/worker.py:44-333`
- **Detail:** Handles job fetch, cancellation check, pre-flight, claim, concurrent guard, analysis deserialization, prompt building, URL signing, generation, cost tracking, download, storage write, NSFW screening, identity check, retry, color normalization, image creation, credit commit, job status update, and error handling — all in one function.
- **Fix:** Break into: `_fetch_and_claim_job()`, `_build_generation_context()`, `_generate_and_validate()`, `_finalize_job()`.

### LR-7: create_generation endpoint is 215 lines
- **Source:** Code Quality Review, CX-2 (High)
- **File:** `app/api/generation.py:118-341`
- **Detail:** Inline entitlement checking, idempotency, tier lookup, queue depth check, credit reservation, and ARQ enqueue.
- **Fix:** Extract into `_check_entitlement()`, `_validate_analysis()`, `_preflight_checks()`, `_enqueue_job()`.

### LR-8: Guest reaction tokens are client-generated with no server registry
- **Source:** Security Review, H-2 (High)
- **File:** `app/api/social.py:239-247`
- **Detail:** The server validates only the format (64-char hex). Any client can fabricate tokens and spam reactions. IP-based rate limiting is the only throttle, trivially bypassed by distributing across IPs.
- **Fix:** Option A (lower effort): generate CSPRNG tokens server-side via `POST /guest-sessions`, store hash in `guest_sessions` table with TTL. Option B: keep client-generated but register on first use via Redis with TTL.

### LR-9: Social login button styling duplicated in 3 files
- **Source:** UI/UX Review, S-4 (Moderate)
- **Files:** `mobile/app/(auth)/login.tsx:374-408`, `signup.tsx:580-614`, `components/auth/SocialLoginButtons.tsx:97-131`
- **Detail:** Social button styles defined identically in three files. `SocialLoginButtons` component exists but is NOT used by login.tsx or signup.tsx.
- **Fix:** Refactor login.tsx and signup.tsx to use the existing `SocialLoginButtons` component. Eliminates ~70 lines of duplication.

### LR-10: FlatList nested in ScrollView kills virtualization
- **Source:** UI/UX Review, P-3 (Moderate)
- **Files:** `mobile/components/profile/GlowUpGrid.tsx:118`, `mobile/app/(tabs)/profile.tsx:161-187`
- **Detail:** `GlowUpGrid` uses a `FlatList` with `scrollEnabled={false}` inside a `ScrollView`. Disables virtualization — all items rendered at once. For large histories, causes performance degradation.
- **Fix:** Replace outer `ScrollView` with a single `FlatList` using `ListHeaderComponent` for the profile header.

### LR-11: Modal focus management for screen readers
- **Source:** UI/UX Review, A-9, A-10 (Serious)
- **Files:** `mobile/components/paywall/PaywallModal.tsx`, `CommentsSheet.tsx`, `EditProfileSheet.tsx`
- **Detail:** Modals don't programmatically move focus on open or return focus on close. VoiceOver/TalkBack users may lose their place in the interface.
- **Fix:** Use `AccessibilityInfo.announceForAccessibility()` on open. Set focus to close button via ref. On close, restore focus to trigger element.

### LR-12: Circuit breaker resets on single success
- **Source:** Architecture Review, M-5
- **File:** `app/generation/cost_tracker.py:140-141`
- **Detail:** A single successful generation deletes all failure history and closes the circuit immediately. If fal.ai is flapping, the breaker opens and closes repeatedly, sending traffic into a failing provider.
- **Fix:** Implement a sliding window or half-open state before fully closing.

### LR-13: Conversation summarization hard-deletes all messages
- **Source:** Architecture Review, M-6
- **File:** `app/advisor/service.py:461`
- **Detail:** After summarization, every message is hard-deleted. If the summary (generated by Haiku, cheapest model) is poor, all conversation context is irreversibly lost.
- **Fix:** Soft-delete messages (set `summarized_at` timestamp). Keep for a retention period. Enables auditing.

---

## Feature Work (new capabilities, not bug fixes)

### FW-1: No pagination on advisor messages, nudges, or memories
- **Source:** API Design Review, F-P2, F-P3, F-P4 (Minor)
- **Files:** `app/api/advisor.py`
- **Detail:** `GET /v1/advisor/messages`, `GET /v1/advisor/nudges`, `GET /v1/memories` return all records with no limit or cursor. Long conversations or many memories could cause large payloads.

### FW-2: No sitemap.ts or robots.ts for card-web
- **Source:** Next.js Review, M-5 (Medium)
- **Detail:** No `robots.txt`, no sitemap. Card URLs are only discoverable through backlinks. For a shareable-card SEO use case, both should be present.

### FW-3: No Content-Security-Policy header
- **Source:** Next.js Review, M-6 (Medium); Security Review, M-2
- **Detail:** No CSP on card-web (Next.js) or the FastAPI backend. CSP would mitigate XSS impact. The FastAPI app also lacks HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy.

### FW-4: No JSON-LD structured data on card page
- **Source:** Next.js Review, L-5 (Low)
- **Detail:** Card page has SEO metadata but no `application/ld+json`. A Person + ImageObject schema would enable rich Google results.

### FW-5: No test script or test files in card-web
- **Source:** Next.js Review, L-6 (Low)
- **Detail:** `package.json` has no `test` entry. Zero test files. A smoke test for `getCardData` parser and `detectPlatform` would catch regressions.

### FW-6: API path naming uses verbs (breaking change to fix)
- **Source:** API Design Review, F-N1, F-N2, F-N5 (Moderate)
- **Detail:**
  - `POST /posts/{id}/react` → should be `POST /posts/{id}/reactions`
  - `POST /advisor/nudges/{id}/read` → should be `PATCH /advisor/nudges/{id}`
  - `POST /credits/purchase` → should be `POST /credit-purchases`
- **Note:** Fixing these requires mobile client changes. Schedule for a versioned API migration.

### FW-7: No Location header on 201 responses
- **Source:** API Design Review, F-H2 (Minor)
- **Detail:** `POST /analyses`, `POST /posts`, `POST /advisor/messages` should include `Location: /v1/{resource}/{id}` header per REST convention.

### FW-8: No sort parameter on comments
- **Source:** API Design Review, F-Q1 (Minor)
- **Detail:** Comments are returned in ascending `created_at` with no sort option. A `sort=newest/oldest` would be consistent with the feed.

### FW-9: No filtering on nudges
- **Source:** API Design Review, F-Q2 (Minor)
- **Detail:** Nudge feed returns both read and unread. A `?unread=true` filter would reduce payload and client-side filtering.

### FW-10: PaymentPort.construct_webhook_event returns dict, not typed
- **Source:** Architecture Review, M-3
- **File:** `app/payment/ports.py`
- **Detail:** Returns `dict` losing type safety. A `WebhookEvent` dataclass should be defined in ports.py.

### FW-11: No deprecation markers or sunset headers on endpoints
- **Source:** API Design Review, F-V2 (Minor)
- **Detail:** No `deprecated=True` in OpenAPI metadata or `Sunset` response headers. Infrastructure to signal deprecation should be established before needed.

### FW-12: Async webhook handlers with sync Supabase calls
- **Source:** Python Review, HIGH-3
- **File:** `app/api/webhooks.py:102+`
- **Detail:** `_handle_checkout_completed` is `async def` but contains only blocking sync Supabase calls with no `await`. Misleads readers, prevents event loop from scheduling other work during I/O.

---

## Informational / No Action Required

### INFO-1: F-N3 — `/jobs/{id}/cancel` uses a verb
Acceptable for state transitions with unique side effects (credit release). Minor note, not a defect.

### INFO-2: F-N4 — `entitlement` is singular
Correct. Singleton resource scoped to authenticated user.

### INFO-3: F-SC4 — POST /auth/login returns 200 instead of 201
Pragmatic choice for an auth endpoint. First-time logins (upsert) could return 201 but 200 is acceptable.

### INFO-4: F-SC3 — DELETE /subscriptions returns 200 with body
Cancellation at period end is a state mutation, not immediate deletion. 200 with body is acceptable.

### INFO-5: F-P5 — Default page sizes differ between endpoints
Variance is reasonable (feed 10/50, comments 20/100, history 20/100). Document as intentional.

### INFO-6: F-M5 — Inconsistent ID field naming
Some models use `analysis_id`, others use `id`. Cosmetic inconsistency, not a bug.

### INFO-7: F-M4 — MemoryResponse.content typed as dict
Low-risk given limited memory types. Would benefit from typed union but not urgent.

### INFO-8: F-V1 — /api/public/cards outside /v1 prefix
Intentional design exception for public shareable cards with no versioning need.

### INFO-9: DB M2 — Redundant idx_images_cleared index
PK index already handles the join; partial index adds no benefit. Not harmful, just dead weight.

### INFO-10: DB M5 — Idempotency key index observation
UNIQUE on `idempotency_key` alone is efficient. Adding `user_id` to the filter is defensive. No action needed.

### INFO-11: DB M6 — Trending feed CTE cannot use indexes for computed score
7-day window bounds the dataset. Monitor. If 7-day window exceeds 50K posts, consider materialized view.

### INFO-12: Python I-2 — Sync vs async handler inconsistency
Not a bug — FastAPI handles both via threadpool. Readability concern only.

### INFO-13: Python I-5 — `now_utc` variable name used for ISO string
Minor naming issue. `now_utc` reads as a datetime object but holds an ISO string.

### INFO-14: Mobile L-1 (Layout) — Root layout without SafeAreaView
Acceptable pattern with Expo Router. Individual screens handle safe areas correctly.
