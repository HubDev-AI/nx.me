# Codebase Concerns

**Analysis Date:** 2026-03-17

## Tech Debt

**Swallowed Exception in Anthropic Adapter (Lines 32-37):**
- Issue: `AnthropicAdapter.__init__` catches broad `Exception` and silently passes when OpenAI client initialization fails. Real import error or missing API key goes unnoticed.
- Files: `app/advisor/adapters/anthropic_adapter.py:32-37`
- Impact: If `OPENAI_API_KEY` is missing but should be set, the fallback silently uses `ANTHROPIC_API_KEY` instead. Embeddings may fail later with unclear origin.
- Fix approach: Log the exception at warn level; if `OPENAI_API_KEY` was explicitly set, raise instead of passing. Document the fallback behavior explicitly.

**Bare Exception Catches Throughout Worker and Scheduler:**
- Issue: Multiple `except Exception as exc:` catches in critical paths log at error/warning but silently return, masking bugs.
- Files: `app/advisor/nudge_scheduler.py:122, 151, 166, 278, 338, 393`; `app/generation/worker.py:305-308`
- Impact: Transient network failures, malformed responses, or application bugs all treated identically. Hard to distinguish between retryable vs. permanent failures.
- Fix approach: Create domain-specific exception hierarchy (NetworkError, ValidationError, ProviderError); catch by type; retry only retryable types. Log full tracebacks.

**Migration Runner Generic Exception Handling (Lines 117-120, 139-142):**
- Issue: `app/migrations/run.py` catches bare `Exception` on migration apply/revert. Does not distinguish database constraint violations from syntax errors or permission issues.
- Files: `app/migrations/run.py:104-142`
- Impact: A missing FK reference or unique constraint violation is reported the same as a typo in SQL. Operator cannot easily diagnose rollback requirements.
- Fix approach: Catch `psycopg2.DatabaseError` subtypes explicitly; log the SQLSTATE error code and constraint name; provide actionable guidance.

## Known Bugs

**Missing Username in Auth Context (Story 2-2):**
- Symptoms: Profile screen loads profile via `loadProfile("me")`, but no explicit auth context provides the logged-in username. Falls back to hardcoded `"me"` endpoint parameter.
- Files: `mobile/app/(tabs)/profile.tsx:74` (TODO comment)
- Trigger: Mobile app navigates to profile tab; auth user info available via JWT but not exposed to React context.
- Workaround: Endpoint `GET /users/me` resolves the username from JWT claims server-side. Works but requires extra roundtrip.
- Fix approach: Extract `sub` (user UUID) from JWT and store in React Context at login time; profile hook can fetch `/users/{uuid}` instead of `"me"`.

**Concurrent Generation Counter Not Reset on Worker Crash:**
- Symptoms: If ARQ worker process dies mid-job, the Redis `concurrent:{user_id}` INCR is never DECR'd. User's limit appears exhausted forever (or until Redis key expires).
- Files: `app/generation/worker.py:100-103, 310-312`
- Trigger: Kill worker process, user attempts new generation immediately.
- Workaround: Redis key expires after `GENERATION_TIMEOUT_SECONDS + 60`. User blocked temporarily but recovers.
- Fix approach: Add watchdog cron job (`watchdog_stuck_jobs` already in `worker.py` but does not clean concurrent counters) to scan `glow_up_jobs` with status PROCESSING and created_at > timeout, then DECR corresponding `concurrent:*` keys.

**Job Data Fetch May Return None Before Assignment (Line 63-66):**
- Symptoms: `job_data` is fetched from database. Code checks `if not job_data:` and logs error, but then later at line 308 uses `if 'job_data' in locals()` as a fallback. Fragile and hard to follow.
- Files: `app/generation/worker.py:62-66, 305-308`
- Trigger: Race condition: job row deleted by external process between fetch and claim.
- Workaround: Fallback catch-all on line 308 passes empty dict `{}` to `_fail_job`, which then tries to release a non-existent credit_reservation_id.
- Fix approach: Fetch job at start, hard-fail if missing (do not proceed). Only catch exceptions in the `try` block from lines 96-303. Remove the locals() fallback.

## Security Considerations

**X-Forwarded-For Not Validated (Story 2-2):**
- Risk: Rate limiting uses `request.client.host` (good), but code comments acknowledge `X-Forwarded-For` is attacker-controlled. If proxy header validation middleware is misconfigured, attacker can spoof IPs.
- Files: `app/api/auth.py:94-96, 379-381` (comments acknowledge; implementation correct)
- Current mitigation: Uses `request.client.host` from uvicorn's internal TCP peer, not header. Correct approach for most deployments. However, if deployed behind load balancer with `--proxy-headers` and no validation middleware, vulnerability exists.
- Recommendations: Document deployment requirement: either (1) disable `--proxy-headers` on uvicorn, or (2) add explicit proxy middleware that validates X-Forwarded-For against a whitelist of trusted proxy IPs. Add tests that verify spoofing attempts fail.

**Bare `except Exception` in Auth Rollback (Line 218-219):**
- Risk: If `supabase.auth.admin.delete_user()` fails, the exception is silently swallowed. Auth user remains after `users` table insert fails, creating orphaned account.
- Files: `app/api/auth.py:216-219`
- Current mitigation: Logs the failure at exception level with context. User sees a 500 error and can retry, which may clean up the orphan.
- Recommendations: Make rollback failure a fatal error. Re-raise after logging so the operator knows a manual cleanup is needed. Or implement an async cleanup job that scans for orphaned auth users weekly.

**Mock Adapters Bypass Real Validation (Lines 84-90 nudge_scheduler, Lines 35-41 worker):**
- Risk: In `ADAPTER__LLM_ADAPTER=mock` or `ADAPTER__IMAGE_GENERATION_ADAPTER=mock` mode, all validations in real adapters are bypassed (cost checking, rate limits, model availability). Staging/dev may not catch issues found only in production.
- Files: `app/advisor/nudge_scheduler.py:84-90`; `app/generation/worker.py:35-41`
- Current mitigation: Environment config controls adapter selection. Dev/staging can use mock; production must use real adapters.
- Recommendations: Add a config setting `MOCK_MODE` that gates mock adapters and logs a warning on startup. Disallow mock adapters if `APP_ENV=production`. Add integration tests that exercise real adapters in staging pipeline (e.g., call real fal.ai with test image).

## Performance Bottlenecks

**Image Processing in Worker Done Synchronously (Lines 249-269):**
- Problem: JPEG encode, color normalization, and upload are all blocking calls in async context. If image is large (8192px), encoding can take 5-10 seconds, blocking the entire job.
- Files: `app/generation/worker.py:249-269`
- Cause: PIL image operations are CPU-bound and not awaitable. Using `asyncio.to_thread` or `loop.run_in_executor` would free up the event loop.
- Improvement path: Wrap `PIL.Image.save()` and color normalization in `loop.run_in_executor(None, func)` to parallelize across CPU threads. Set thread pool size in ARQ config.

**Identity Check Retried Sequentially (Lines 208-247):**
- Problem: If identity check fails, a second attempt is made with adjusted parameters. Both checks are synchronous and sequential, adding 10-30s latency per job.
- Files: `app/generation/worker.py:208-247`
- Cause: ArcFace inference is CPU-intensive and must wait for image download from remote URL before checking.
- Improvement path: Pre-download both images in parallel before first identity check. If first check fails, retry immediately with new generation params without waiting for a fresh download.

**Conversations Auto-Summary Not Rate-Limited (Lines 92-94):**
- Problem: If user spams messages quickly, `check_nudge_eligibility` cron runs daily and may enqueue multiple summary jobs for the same conversation. Not a hard performance issue but inefficient.
- Files: `app/advisor/service.py:92-94`
- Cause: No lock or flag to prevent concurrent summarization of the same conversation.
- Improvement path: Add a `conversation_summarizing` flag or lock in Redis. Set it when summary job starts; check it before enqueuing.

**Tier Repository Caches Tiers in Redis Without Invalidation:**
- Problem: Tiers are cached in Redis with no explicit invalidation. If a tier is updated via admin API, cached data stale until TTL expires (default 1 hour or more).
- Files: `app/entitlement/tier_repo.py` (not reviewed but napkin mentions cache)
- Cause: Cache-aside pattern without cache-busting event.
- Improvement path: Emit cache invalidation event to Redis when tier is updated (e.g., `SET tier_cache_version:v2` to bump all key names). Or use short TTL (5 minutes) for dev and accept staleness.

## Fragile Areas

**Credit Reservation and Commit Lifecycle (Two-Phase Pattern):**
- Files: `app/generation/worker.py:44-313`; `app/entitlement/ledger.py`; `app/api/generation.py:150-250`
- Why fragile: Three separate systems must coordinate: (1) entitlement check + reserve credit, (2) generate + commit, (3) refund on failure. If any step fails to release reserved credits, user's balance becomes inconsistent.
- Safe modification: Always use the `CreditLedger` interface (not direct INSERT). Wrap reserve + job creation in a transaction. Test the full lifecycle: reserve → generate → fail → release. Verify `credit_ledger` entries always sum to user's available balance.
- Test coverage: Single test file `tests/test_credit_ledger_invariants.py` exists. Verify it covers all failure modes (job cancelled mid-processing, network timeout on commit, concurrent operations).

**Job Status State Machine (QUEUED → PROCESSING → COMPLETED/FAILED):**
- Files: `app/generation/worker.py:69-90` (conditional update for QUEUED → PROCESSING); `app/api/generation.py:200-250` (enqueue after reserve)
- Why fragile: Race conditions if job is claimed by two workers or cancelled while processing. The conditional update at line 87-90 uses `.eq("status", JobStatus.QUEUED)` to prevent double-claiming, but if that fails silently, the job is skipped.
- Safe modification: Always check claim result and log at info level if already claimed. Test concurrent worker instances claiming the same job. Verify only one succeeds.
- Test coverage: No visible integration tests for multi-worker scenarios. Add a test that spins up two workers and enqueues a job; verify only one completes it.

**Advisor Memory Extraction (Async Haiku Call in Fireground):**
- Files: `app/advisor/service.py:67-100+`, `app/advisor/memory_manager.py` (async `get_relevant_memories`)
- Why fragile: Memory extraction is async but called from the main chat response path. If Haiku times out or fails, the entire message response is delayed or failed. No fallback to skip memory extraction.
- Safe modification: Add timeout to memory extraction; on timeout, continue with chat but skip memory update. Or move memory extraction to background job and return chat response immediately.
- Test coverage: No visible tests for timeout scenarios. Add test that mocks LLM timeout and verifies chat still returns.

**Usage Event Tracking (Async Fire-and-Forget):**
- Files: `app/api/analyses.py`, `app/api/generation.py` — presumably logs usage events async but code not fully visible.
- Why fragile: If usage event insert fails silently, entitlement counts become inconsistent. User may bypass limits or be incorrectly rate-limited.
- Safe modification: Log usage events synchronously or verify async task completes before responding. Add a reconciliation cron job that scans `glow_up_jobs` and ensures matching `usage_events` rows.
- Test coverage: No visible tests for event logging failures.

## Scaling Limits

**Max Queue Depth (15,000 jobs):**
- Current capacity: `MAX_QUEUE_DEPTH=15000` in config (line 74).
- Limit: If queue depth exceeds 15k, enqueue fails or job is rejected. ARQ can handle ~100 jobs/sec on a single worker, so 15k jobs = ~2.5 minutes of work at full capacity.
- Scaling path: Increase workers (ARQ spawns more task consumers), or increase `MAX_QUEUE_DEPTH` and monitor Redis memory. Add alerting when queue depth > 10k.

**Concurrent Generations Per User (3):**
- Current capacity: `MAX_CONCURRENT_GENERATIONS_PER_USER=3` guards against users submitting 100+ jobs in parallel.
- Limit: Hard limit enforced via Redis INCR + expire. User blocked if counter >= 3.
- Scaling path: Make this per-tier config (A-4). Premium tier could allow 5+.

**Identity Check CPU Threads:**
- Current capacity: Unclear. ArcFace inference is CPU-bound. If 10 workers are checking identity in parallel, that's 10 threads on a single machine.
- Limit: If worker machine is CPU-constrained (e.g., 4 CPU cores), identity checks will starve other async operations.
- Scaling path: Offload identity checks to a dedicated GPU service or batch them. Or use `max_workers` in executor pool.

**Advisor Conversation Auto-Summary:**
- Current capacity: Haiku is called inline during message response if conversation hits SUMMARY_THRESHOLD (30 messages). Summary can take 10+ seconds.
- Limit: If 10 users simultaneously hit the threshold, 10 Haiku calls block the app.
- Scaling path: Move summary to background job; return chat response immediately. Mark conversation as "summarizing" to prevent concurrent summaries.

## Dependencies at Risk

**Stripe SDK Version (14.4.1):**
- Risk: Pinned to 14.4.1. Newer versions (14.4.2+) may have security fixes or API changes.
- Impact: Webhook signature validation, payment intent handling, or subscription API calls may break if Stripe changes endpoint behavior.
- Migration plan: Monitor Stripe SDK releases; test new versions in staging. Pin to latest stable patch version only (e.g., `stripe==14.4.*`), not exact version.

**Anthropic SDK (No Version Pinned):**
- Risk: `anthropic` and `openai` packages are lazy-imported in adapters (lines 26-27 of anthropic_adapter.py), so version not specified in requirements.txt. Pip installs latest, which may break if API changes.
- Impact: Message format, model names, or response structure may change; code expects specific Anthropic response shape.
- Migration plan: Add `anthropic>=1.0.0,<2.0.0` and `openai>=1.0.0,<2.0.0` to requirements.txt. Pin major versions. Test model calls on version upgrades.

**MediaPipe (0.10.32):**
- Risk: MediaPipe is actively developed. Version 0.11+ may have different landmark detection output or require different initialization.
- Impact: Face analysis accuracy or landmark extraction may degrade.
- Migration plan: Add integration test that benchmarks accuracy of landmark extraction on test images. Compare results when upgrading MediaPipe version.

## Missing Critical Features

**No Explicit Retry Policy for Failed Jobs:**
- Problem: Jobs can fail (FAILURE_PROVIDER, FAILURE_IDENTITY, FAILURE_NSFW). No explicit retry queue or SLA.
- Blocks: Users cannot retry a failed generation without re-uploading an image and re-creating the job. Premium users may expect automatic retries or refunds.
- Fix approach: Add `retry_count` and `max_retries` columns to `glow_up_jobs`. Enqueue a retry job if count < max_retries and failure is retryable (not FAILURE_IDENTITY). Or offer a manual "retry with different params" endpoint.

**No Rate Limiting on Image Upload (AC-2):**
- Problem: `POST /analyses` accepts an image but has no per-user upload rate limit. User could submit 100 images/sec and exhaust storage quota or API rate limits.
- Blocks: API can be DoS'd by a user submitting many large images.
- Fix approach: Add `ANALYSIS_UPLOAD_LIMIT_PER_HOUR` config. Check per-user limit on image upload endpoint.

**No Mechanism to Pause Advisor Nudges During Holidays:**
- Problem: Nudge scheduler runs daily regardless of holidays. User may receive nudge on Christmas or during vacation.
- Blocks: Premium users expect customizable nudge frequency/timing.
- Fix approach: Add `advisor_nudge_pause_until` timestamp to users table. Check before enqueuing.

## Test Coverage Gaps

**No Test for Race Condition in Job Claiming (Story 4-3):**
- What's not tested: Two workers claim the same job simultaneously; second worker processes empty update.
- Files: `app/generation/worker.py:87-90` (conditional claim)
- Risk: Race condition may go unnoticed until production load spikes. Job may be dropped silently.
- Priority: High — affects core generation flow.

**No Test for Credit Release on All Failure Paths (Story 4-3):**
- What's not tested: FAILURE_TIMEOUT, FAILURE_NSFW, network errors during image upload, storage upload failure — all must release credits. Current code has multiple exit points with no verification.
- Files: `app/generation/worker.py` (entire worker function)
- Risk: Credits may be lost if a failure path misses the release call.
- Priority: High — directly impacts user entitlement consistency.

**No Test for Advisor Async Memory Extraction Timeout (Story 7-2):**
- What's not tested: If `memory_manager.get_relevant_memories()` times out, chat response is blocked. No timeout or fallback tested.
- Files: `app/advisor/service.py:97`
- Risk: LLM latency or embedding service failure can cascade to user timeout.
- Priority: Medium.

**No Test for Concurrent User Limit Enforcement (Story 4-3):**
- What's not tested: User hits `MAX_CONCURRENT_GENERATIONS_PER_USER=3`, fourth job is rejected. Test that only exactly 3 jobs can run in parallel.
- Files: `app/generation/worker.py:100-103, 310-312`; `app/api/generation.py:210-220`
- Risk: Limit may be enforced inconsistently if concurrent counter is not properly managed.
- Priority: Medium.

**No Test for Tier-Based Limits (Story 4-1):**
- What's not tested: TRIAL tier has 2 analyses/month, CREDIT_HOLDER has 100/month. Verify user cannot exceed tier limit. Verify tier upgrade takes effect.
- Files: `app/entitlement/service.py` (entire service)
- Risk: Tier limits may not be enforced or may be stale due to cache.
- Priority: High — monetization depends on this.

**No Test for Social Login Callback Handling (Story 2-2):**
- What's not tested: Google/Apple id_token validation, email extraction, user creation for social users, session persistence.
- Files: `app/api/social.py`, `mobile/app/(auth)/signup.tsx`
- Risk: Social login may silently fail or create duplicate accounts.
- Priority: High — affects user acquisition.

**No Test for Username Reservation Logic (Story 2-1):**
- What's not tested: Deleted user's username is reserved for 180 days. New user cannot register with reserved username. Reservation expires after 180 days.
- Files: `app/api/auth.py:127-151` (check username availability)
- Risk: Reservation enforcement may be missing or time calculation may be wrong.
- Priority: Medium.

---

*Concerns audit: 2026-03-17*
