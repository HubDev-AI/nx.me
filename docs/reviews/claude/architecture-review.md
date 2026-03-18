# Architecture Review

- Date: 2026-03-17
- Scope: Full system (FastAPI backend, ARQ worker, Supabase/Redis infrastructure)
- Reviewer: Software Architect Agent
- Codebase branch: feature/story-2-2-auth-social-login

---

## Findings

### Critical

**C-1: Synchronous Supabase calls block the async event loop**

60+ `supabase.table(...)` calls across API handlers execute synchronously (the `supabase-py` SDK's `.execute()` is blocking I/O). When these are invoked inside `async def` handlers (e.g., `create_generation`, `get_entitlement`, `stripe_webhook`), they block the entire asyncio event loop for the duration of each HTTP round-trip to Supabase.

The same problem exists in `EntitlementService`, `CreditLedger`, `UsageRepository`, `TierRepository`, and `AdvisorService` -- all use synchronous Supabase calls from async callers.

Affected files (not exhaustive):
- `app/entitlement/service.py` (lines 86-93, 106-113, 312-323)
- `app/entitlement/ledger.py` (lines 44-50, 68-71)
- `app/entitlement/usage_repo.py` (lines 36-46)
- `app/advisor/service.py` (lines 287-294, 325-332, 454-458)
- `app/api/generation.py` (10 occurrences)
- `app/api/auth.py` (10 occurrences)
- `app/api/posts.py` (12 occurrences)
- `app/api/webhooks.py` (11 occurrences)

Some handlers are defined as `def` (not `async def`), which means FastAPI runs them in a threadpool automatically -- this is actually correct for synchronous Supabase calls. The inconsistency is the problem: `async def` handlers that call synchronous Supabase code are the ones that block the loop.

**Impact**: Under concurrent load, a single slow Supabase query stalls all in-flight requests. The generation endpoint is especially vulnerable -- it calls `ent_svc.check()` (which makes 2-3 Supabase calls) before enqueuing.

**Options**:
1. Use `run_in_executor` for all Supabase calls in async contexts (tactical, adds boilerplate).
2. Switch affected handlers to `def` (not `async def`) so FastAPI uses its threadpool (simplest short-term fix, but loses ability to `await` Redis/ARQ calls in the same handler).
3. Adopt an async Supabase client or switch to `asyncpg` + raw SQL for hot paths (strategic).

---

**C-2: Handlers directly access the database -- AC-D1 violated at scale**

The project's own architecture rule (AC-D1) states: "No handler reads credit_ledger or subscriptions directly." Yet 60 direct `supabase.table(...)` calls exist across 10 handler files.

The entitlement module follows AC-D1 well -- it encapsulates credit/tier logic behind `EntitlementService`, `CreditLedger`, `TierRepository`. But the same discipline is not applied elsewhere:

- `app/api/auth.py`: 10 direct DB calls (user creation, username check, tier lookup, email verification).
- `app/api/generation.py`: 10 direct DB calls (analysis lookup, job creation, usage event insert, image queries, job status updates).
- `app/api/posts.py`: 12 direct DB calls (job verification, image lookups, post/comment/report CRUD).
- `app/api/social.py`: 3 direct DB calls (feed queries).
- `app/api/users.py`: 6 direct DB calls (profile, history, update).
- `app/api/webhooks.py`: 11 direct DB calls (idempotency check, subscription/credit handling).

There are no repository classes for `users`, `glow_up_jobs`, `analyses`, `images`, `posts`, `comments`, `reports`, `subscriptions`, or `processed_webhook_events`. Each handler builds its own query inline.

**Impact**: Query logic is duplicated (e.g., "fetch job by id and verify ownership" appears in generation.py and posts.py), changes to table schemas require touching multiple handler files, and testing requires mocking Supabase at the transport level rather than at a repository boundary.

---

### High

**H-1: Duplicate worker settings files**

Two worker settings modules exist:
- `app/worker_settings.py` (the "unified" worker)
- `app/generation/worker_settings.py` (generation-only worker)

Both define `startup`, `shutdown`, and `WorkerSettings` with overlapping functionality. The unified worker includes all generation functions plus social and advisor jobs. The generation-specific one only has `process_generation_job`.

**Risk**: Running the wrong worker entry point in production means jobs silently fail to process. If someone starts `arq app.generation.worker_settings.WorkerSettings`, social reactions and advisor nudges are never consumed.

**Recommendation**: Delete `app/generation/worker_settings.py` and keep only the unified `app/worker_settings.py`. If separate scaling is needed later, extract by queue name, not by duplicating configuration.

---

**H-2: `_ERROR_MESSAGES` dict duplicated across files**

The error message mapping for entitlement codes is defined in two places:
- `app/api/deps.py` (lines 78-86)
- `app/api/generation.py` (lines 63-69)

These will inevitably drift. The generation.py copy is missing `TIER_FEATURE_LOCKED` and `TIER_CONCURRENT_LIMIT` compared to the deps.py version.

**Recommendation**: Define once in `app/entitlement/models.py` and import everywhere.

---

**H-3: Adapter resolution scattered across three locations**

Adapter factory logic (the `if settings.ADAPTER__X == "..." else mock` pattern) appears in:
- `app/api/deps.py` -- `get_payment_adapter()`, `get_llm_adapter()`
- `app/generation/worker.py` -- `_get_generator()`
- `app/advisor/nudge_scheduler.py` -- `_get_llm_adapter()`

The `_get_llm_adapter()` function is literally duplicated between `deps.py` and `nudge_scheduler.py`. There is no unified adapter registry.

**Recommendation**: Create `app/adapters/registry.py` with a single `get_adapter(port_type)` function. Each module calls the registry rather than reimplementing resolution logic.

---

**H-4: `asyncio.create_task` fire-and-forget in advisor without exception handling**

In `app/advisor/service.py` line 136:
```python
asyncio.create_task(
    self._memory_manager.extract_memories_from_turn(...)
)
```

If this task raises, the exception is silently swallowed (Python logs it as "Task exception was never retrieved" only if debug logging is on). There is no error handler attached to the task.

**Recommendation**: Attach a `task.add_done_callback` that logs exceptions, or use a helper like:
```python
task = asyncio.create_task(coro)
task.add_done_callback(_log_task_exception)
```

---

### Medium

**M-1: `content_filter.check_rate_limit` raises `ValueError` for a rate limit -- wrong error type**

In `app/advisor/content_filter.py` line 83, exceeding the chat rate limit raises `ValueError("RATE_LIMIT_EXCEEDED")`. The advisor handler must catch this and convert it to HTTP 429. Using `ValueError` for a business rule violation conflates input validation with rate limiting and makes the caller responsible for knowing the string "RATE_LIMIT_EXCEEDED" is not a real validation error.

**Recommendation**: Define a `RateLimitExceeded` exception in the advisor module. The handler layer maps it to HTTP 429.

---

**M-2: No structured error response for non-entitlement failures**

Entitlement errors return a well-structured `{"error": {"code": ..., "message": ..., "detail": ...}}` envelope. But other endpoints raise `HTTPException(detail=string)` -- a flat string. Clients parsing error responses must handle two different formats.

Examples of flat-string errors:
- `app/api/auth.py`: `"Username is already taken."`, `"Email address is not verified."`
- `app/api/posts.py`: `"Post not found or already deleted."`
- `app/api/generation.py`: `"Analysis not found."`

**Recommendation**: Adopt a single error envelope factory used across all handlers.

---

**M-3: Payment port protocol is missing `construct_webhook_event` return type**

`PaymentPort.construct_webhook_event` returns `dict`, but the Stripe SDK returns a typed `Event` object that gets cast to `dict(event)`. This loses type safety and makes the mock adapter's contract ambiguous (what keys must the dict contain?).

**Recommendation**: Define a `WebhookEvent` dataclass in `app/payment/ports.py` that both adapters return.

---

**M-4: `get_rolling_24h_avg_cost` math is wrong**

In `app/generation/cost_tracker.py` line 66:
```python
return total_cost / max(bucket_count * 10, 1)
```

This divides total cost by `bucket_count * 10`, which assumes 10 generations per hourly bucket -- a hardcoded magic number that has no basis in actual generation volume. This produces an unreliable average that could either over-throttle or under-throttle trial users.

**Recommendation**: Track generation count alongside cost in Redis (separate counter per bucket), then compute `total_cost / total_count`.

---

**M-5: Circuit breaker resets on a single success**

In `app/generation/cost_tracker.py` line 140-141:
```python
async def record_success(self) -> None:
    await self._redis.delete("gen:circuit:failures")
    await self._redis.delete("gen:circuit:open")
```

A single successful generation deletes all failure history and immediately closes the circuit. If fal.ai is flapping (intermittent failures), the breaker opens and closes repeatedly, sending traffic into a failing provider.

**Recommendation**: Use a sliding window or half-open state before fully closing.

---

**M-6: Conversation summarization deletes all messages**

In `app/advisor/service.py` line 461:
```python
self._supabase.table("advisor_messages").delete().eq(
    "conversation_id", conversation_id
).execute()
```

After summarization, every message is hard-deleted. If the summary LLM call produces a poor summary (the LLM is Haiku, which is the cheapest model), all conversation context is irreversibly lost.

**Recommendation**: Soft-delete messages (set a `summarized_at` timestamp) and keep them for a retention period. This also enables auditing.

---

**M-7: Synchronous `def` handlers mixed with async dependencies**

Several handlers are `def` (sync) but depend on services that are async-only:
- `app/api/social.py:69` -- `get_feed` is `def` (correct for sync Supabase)
- `app/api/advisor.py:122` -- `get_advisor_messages` is `def` but `AdvisorService.send_message` is `async`

This inconsistency makes it unclear which handlers can call which services without blocking.

---

### Low

**L-1: `app/generation/worker_settings.py` `redis_settings = None` with no override mechanism**

Both worker settings files set `redis_settings = None` and rely on ARQ's default behavior to pick up the connection from the startup function. This works but is implicit -- there is no documented or enforced contract for how the worker connects to Redis.

---

**L-2: `SOUL.md` loaded at module import time**

`app/advisor/service.py` line 46 reads `SOUL.md` during import:
```python
_SOUL_MD: str = _SOUL_MD_PATH.read_text(encoding="utf-8")
```

This is fine for production but can cause `FileNotFoundError` during test collection if tests import `AdvisorService` without the file present. It also means SOUL.md changes require a process restart.

---

**L-3: `_FORBIDDEN_OUTPUT_TERMS` has a duplicate entry**

`app/advisor/content_filter.py` line 30: `"ranking"` appears twice in the `frozenset`. The `frozenset` deduplicates it, so no functional impact, but it indicates a copy-paste oversight.

---

**L-4: Magic number `_AVG_SECONDS_PER_JOB = 15` in generation.py**

Line 60 of `app/api/generation.py` defines a hardcoded constant for wait estimation. Per coding conventions, this should be in `app/config` as a configurable value.

---

**L-5: `get_fallback_response()` returns a single hardcoded string**

The advisor fallback response in `content_filter.py` is a single string. For a better user experience, this could rotate among a few options to avoid the bot feeling mechanical on repeated violations.

---

## Dependency Map Issues

### Correct dependency direction (handlers -> services -> repos -> models)

The following modules follow the intended layering:

```
app/api/deps.py          -> app/entitlement/service.py     (handler -> service)
app/entitlement/service.py -> app/entitlement/ledger.py    (service -> repo)
app/entitlement/service.py -> app/entitlement/tier_repo.py (service -> repo)
app/entitlement/service.py -> app/entitlement/usage_repo.py(service -> repo)
app/entitlement/service.py -> app/entitlement/models.py    (service -> model)
app/advisor/service.py     -> app/advisor/memory_manager.py(service -> service)
app/advisor/service.py     -> app/advisor/content_filter.py(service -> utility)
```

### Broken dependency direction (handler -> database directly)

```
app/api/auth.py         -> supabase.table("users")     (HANDLER -> DB, skips service/repo)
app/api/auth.py         -> supabase.table("tiers")     (HANDLER -> DB, skips TierRepository)
app/api/generation.py   -> supabase.table("analyses")  (HANDLER -> DB, no analysis repo)
app/api/generation.py   -> supabase.table("glow_up_jobs") (HANDLER -> DB, no job repo)
app/api/generation.py   -> supabase.table("images")    (HANDLER -> DB, no image repo)
app/api/generation.py   -> supabase.table("usage_events") (HANDLER -> DB, no usage service)
app/api/posts.py        -> supabase.table("posts")     (HANDLER -> DB, no post repo)
app/api/posts.py        -> supabase.table("comments")  (HANDLER -> DB, no comment repo)
app/api/social.py       -> supabase.table("posts")     (HANDLER -> DB, no feed repo)
app/api/webhooks.py     -> supabase.table("subscriptions") (HANDLER -> DB, skips service)
app/api/webhooks.py     -> CreditLedger directly       (HANDLER -> REPO, skips service)
app/api/users.py        -> supabase.table("users")     (HANDLER -> DB, no user repo)
```

### Cross-module coupling

- `app/api/generation.py` imports from `app/constants/tiers.py` (tier slug constants) -- acceptable given Amendment A-4.
- `app/worker_settings.py` imports `persist_reaction` and `reconcile_reaction_counts` from `app/api/social.py` -- a **worker importing from an API handler module**. These functions should live in a service or worker module, not in the API layer.
- `app/generation/worker.py` imports from `app/face_analysis/models.py` and `app/entitlement/ledger.py` directly -- acceptable within the worker context, but the inline data reconstruction of `AnalysisResult` (lines 116-130) suggests the analysis repo should provide this.

---

## Scalability Concerns

### 1. Event loop starvation (Critical -- see C-1)

All synchronous Supabase calls in `async def` handlers block the single-threaded event loop. At 50+ concurrent users, this creates a cascading latency problem where healthy Redis/ARQ operations wait behind slow Supabase queries.

### 2. N+1 query in `get_rolling_24h_avg_cost`

`CostTracker.get_rolling_24h_avg_cost()` issues 24 sequential Redis `GET` commands (one per hourly bucket). This should use `MGET` to fetch all 24 keys in a single round-trip.

### 3. Entitlement check makes 2-3 DB calls per request

`EntitlementService.check()` calls `_get_tier()` (1 DB query for user, 1 for tier with Redis cache), then either `_ledger.balance()` (1 RPC call) or `_usage.count_in_window()` (1 DB query). Every generation request makes 2-3 sequential Supabase calls before the job is even enqueued.

With tier caching, the happy path is 2 calls (user lookup + usage count). Consider caching the user's `tier_id` in Redis alongside the session token to eliminate the user lookup.

### 4. Single ARQ worker processes all queues

The unified `WorkerSettings` handles generation jobs, social reactions, advisor nudges, and cron jobs in one process with `max_jobs = 10`. A surge in generation jobs (the slowest task type at ~15s each) could starve reaction persistence and nudge generation.

**Recommendation**: Run separate worker processes per queue category, or at minimum ensure reaction and nudge jobs have lower timeouts and are in the `default` queue which is read alongside generation lanes.

### 5. No connection pooling for Supabase

`get_supabase_service()` creates a single `Client` instance shared across all requests. The `supabase-py` SDK uses `httpx` under the hood, which has a default connection pool. This works for moderate load, but under high concurrency the synchronous calls become the bottleneck before the pool is exhausted.

### 6. Queue depth check queries all three lanes sequentially

`CostTracker.check_queue_depth()` calls `self._redis.llen()` three times sequentially. Use a pipeline.

---

## Summary

**Architecture strengths**:
- Clean port/adapter pattern for external services (fal.ai, Stripe, Anthropic, NSFW screening). Protocol-based interfaces (`GlowUpGeneratorPort`, `PaymentPort`, `LLMPort`) enable testability.
- Entitlement module is well-isolated with proper layering (service -> ledger/tier_repo/usage_repo -> models). Credit operations use atomic RPCs. This is the module most worth emulating.
- Config-driven adapter selection with mock/local blocklist in non-development environments (lifespan safety check).
- Priority queue lanes for generation jobs with cost tracking and circuit breaker.
- Redis-cached tier lookups avoid per-request DB hits for the most common query.

**Architecture weaknesses**:
- The biggest systemic risk is synchronous Supabase SDK calls inside async handlers (C-1). This must be addressed before production load testing.
- Handlers bypass the service/repository layer for most domains outside entitlement (C-2). The codebase has good architectural intent (AC-D1, adapter pattern) but inconsistent application.
- Duplicated code across files (H-2 error messages, H-3 adapter resolution, H-1 worker settings) will cause drift as the system grows.
- Error handling is inconsistent: structured envelopes for entitlement, flat strings elsewhere (M-2).

**Recommended priority**:
1. Address C-1 (sync-in-async) -- this is a production blocker.
2. Extract repositories for `users`, `glow_up_jobs`, `analyses`, `images`, `posts` to enforce dependency direction (C-2).
3. Consolidate duplicated code (H-1, H-2, H-3).
4. Fix the circuit breaker reset behavior (M-5) before it causes production incidents.
5. Standardize error response format across all endpoints (M-2).
