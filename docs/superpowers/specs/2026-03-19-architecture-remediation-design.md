# Architecture Remediation Design Spec

**Date:** 2026-03-19
**Source:** `docs/architecture-audit-2026-03-19.md` (21 findings)
**Approach:** Domain-grouped waves — 3 PRs, each touching one coherent domain

---

## Wave 1 — Generation Pipeline (6 findings)

### H-1: Fix identity retry threshold

**File:** `app/generation/worker.py`

The first identity check uses the per-tier `identity_threshold` variable (fetched from DB on lines 286-299). The retry on line 357 incorrectly uses `settings.IDENTITY_SIMILARITY_THRESHOLD` (global 0.80). A premium user with a per-tier threshold of 0.70 could pass the first check but fail the retry.

**Changes:**
- Pass `identity_threshold` to the retry `check_identity` call instead of `settings.IDENTITY_SIMILARITY_THRESHOLD` (line 357)
- Also fix the log message on line 318 which displays `settings.IDENTITY_SIMILARITY_THRESHOLD` instead of the per-tier `identity_threshold` — misleading when debugging premium users

### H-2: Refactor prompt builder to use module registry

**Files:** `app/generation/prompt_builder.py`, `app/generation/modules/styling.py`

The prompt builder reimplements keyword extraction, template loading, and parameter computation inline — duplicating what `StylingModule` already does. The module registry (`registry.py`) exists but is never called.

**Changes:**

1. `build_prompt(analysis_result, analysis_id)` becomes a compositor:
   - Parses `settings.ENABLED_TRANSFORMATION_MODULES` into slugs
   - Calls `registry.get_active_modules(analysis_result, enabled_slugs)`
   - Iterates modules, calling `module.build_output(analysis_result, mode)`
   - Composes the `TransformationOutput` fragments into the final prompt
   - Applies identity phrase and returns `(prompt, negative, adaptive_params)`

2. Move inline logic into `StylingModule`:
   - `prepare_keywords()` (hair-first ordering, style theme injection, cap) → `StylingModule.build_output()`
   - `select_lighting_keyword()` → `StylingModule.build_output()` (styling concern)
   - `compute_adaptive_params()` → `StylingModule.adjust_params()`

3. Identity phrase selection stays in prompt builder (cross-module, not styling-specific)

4. Remove dead `_module = StylingModule()` line and `noqa: F841`

5. `prompt_builder.py` shrinks to: mode selection, identity phrase, module composition, template validation. Future modules (teeth, eyes) implement the Protocol, auto-register, add slug to config — zero changes to prompt_builder.

### H-5: Always run NSFW screening

**File:** `app/generation/worker.py`

Currently NSFW screening is skipped entirely when `ADAPTER__NSFW_ADAPTER != "rekognition"`. The mock adapter path has zero content safety.

**Change:** Add a `_get_nsfw_screener()` factory (same pattern as `_get_generator()`):
- `"rekognition"` → `RekognitionAdapter`
- `"mock"` or any other value → `MockNsfwAdapter`

`MockNsfwAdapter` returns `NsfwResult(is_explicit=False)` — deterministic safe, but the code path is always exercised. Replace the `if adapter == "rekognition"` conditional with a call through the factory.

Note: config documents `sightengine` as a valid option but no adapter exists. The factory should log a warning if an unrecognized adapter name is configured and fall back to mock. Sightengine support is deferred.

### M-1: Hoist stable imports to module level

**File:** `app/generation/worker.py`

Move `import httpx` and `import PIL.Image` to module level. Keep conditional adapter imports (`from app.generation.adapters.falai import FalAiAdapter`) inline since those are gated by config.

### M-2: Deterministic prompt building

**File:** `app/generation/prompt_builder.py`

Add `analysis_id: str` parameter to `build_prompt()`. Create a `random.Random(hash(analysis_id))` instance. Pass it to style theme selection, lighting keyword selection, and identity phrase selection. The global `random` is never used — each generation is reproducible given the same `analysis_id`. The caller in `worker.py` passes `job_data["analysis_id"]`.

Note: `worker.py` is the sole caller of `build_prompt()` (confirmed via grep). The signature change only affects one call site (line 152).

### M-7: Cache adapter in worker context

**File:** `app/generation/worker.py`

In `process_generation_job`, `ctx` is the arq `WorkerContext` dict (passed as the first parameter, see line 457). Check `ctx.get("generator")` before calling `_get_generator()`. Store on first use: `ctx["generator"] = _get_generator()`. The adapter is stateless and thread-safe. Current call site is line 476.

---

## Wave 2 — AI/Advisor System (8 findings)

### C-2: Update Claude model identifiers

**File:** `app/config/__init__.py`

Change:
- `ADVISOR_MODEL_HAIKU` from `"claude-3-haiku-20240307"` to `"claude-haiku-4-5-20251001"`
- `ADVISOR_MODEL_SONNET` from `"claude-3-5-sonnet-20241022"` to `"claude-sonnet-4-6"`

**New file:** `tests/test_advisor_smoke.py`

Smoke test that sends 3-4 canned messages through `AdvisorService.send_message` using the mock LLM adapter:
- No C-2 violations in responses
- Response length within `_MAX_TOKENS_CHAT`
- Fallback responses not triggered on clean input

Tests the advisor pipeline end-to-end (sanitization, context building, post-check, content filter), not the model itself.

### H-3: Fix fire-and-forget asyncio task

**File:** `app/advisor/service.py`

Store task reference in a module-level `WeakSet` to prevent garbage collection. Add a `done_callback` that logs exceptions at ERROR level:

```python
_background_tasks: weakref.WeakSet[asyncio.Task] = weakref.WeakSet()

# In send_message:
task = asyncio.create_task(_extract_with_logging())
_background_tasks.add(task)
```

The `done_callback` pattern:
```python
def _task_done(t: asyncio.Task) -> None:
    if t.cancelled():
        return
    exc = t.exception()
    if exc:
        logger.error("Background task failed: %s", exc, exc_info=exc)

task.add_done_callback(_task_done)
```

### H-4: Implement model cost degradation

**Files:** `app/advisor/service.py`, `app/config/__init__.py`

`_select_model()` checks daily message volume. The existing `advisor_chat_rate:{user_id}` key uses a 1-hour window (not daily), so we need a separate counter: `advisor_daily_msgs:{user_id}:{YYYYMMDD}` with 86400s TTL, incremented alongside the rate limit key in `content_filter.check_rate_limit`. If count > threshold, return Haiku.

Add `ADVISOR_DEGRADATION_THRESHOLD: int = 50` to config (per-day, not per-hour). `_select_model` becomes async (needs Redis access via `self._redis`). Update the call site in `_call_llm_with_check` (line 194) from `self._select_model()` to `await self._select_model()`.

### M-3: Fix sentence counter

**File:** `app/advisor/service.py`

Replace:
```python
sentence_count = response.count(". ") + response.count("? ") + response.count("! ") + 1
```

With:
```python
sentence_count = len(re.split(r'(?<=[.!?])\s+', text.strip()))
```

Handles abbreviations better (no space after "Dr.Smith" → not split) and end-of-string sentences.

### M-4: Fix memory dedup fingerprint

**File:** `app/advisor/memory_manager.py`

Replace `str(row.get("content", ""))[:80]` with `hashlib.md5(str(row.get("content", "")).encode()).hexdigest()`. Full content comparison, constant-size key, no false collisions on structured data with shared prefixes.

### M-5: Rethink content filter

**File:** `app/advisor/content_filter.py`

Two changes:

1. Switch from `term in lower` to `re.search(rf'\b{re.escape(term)}\b', lower)` for word-boundary matching.

2. Rework the forbidden terms list. Curation principle: **block terms that rate/judge the person, not terms that describe aesthetics.**

   **Remove** (legitimate style vocabulary): `"hot"`, `"pretty"`, `"beautiful"`, `"gorgeous"`, `"attractive"`

   **Keep** (always judgmental): `"ugly"`, `"hideous"`, `"unattractive"`, `"beauty score"`, `"out of ten"`, `"/10"`, `"ranking"`, `"rating"`

   Add a comment documenting the curation principle so future additions follow the same logic.

### M-6: Add LLM timeouts

**Files:** `app/advisor/adapters/anthropic_adapter.py`, `app/config/__init__.py`

Add to config:
- `ADVISOR_LLM_TIMEOUT_SECONDS: float = 30.0`
- `ADVISOR_EMBEDDING_TIMEOUT_SECONDS: float = 15.0`

Pass `timeout=httpx.Timeout(settings.ADVISOR_LLM_TIMEOUT_SECONDS)` to `anthropic.AsyncAnthropic()` constructor. Pass `timeout=settings.ADVISOR_EMBEDDING_TIMEOUT_SECONDS` to `openai.AsyncOpenAI()`.

### M-8: Wrap sync DB calls in async advisor

**File:** `app/advisor/service.py`

Wrap these sync calls with `run_sync()` (from `app.db.async_helpers`, already used throughout the codebase):
- `self._get_or_create_conversation(user_id)` → `await run_sync(...)` (line 89, and line 240/262)
- `self._load_conversation_history(conversation_id)` → `await run_sync(...)` (line 93, and second call at line 121 after summarization)
- `self._save_message(conversation_id, role, content)` → `await run_sync(...)` (lines 158-159)
- `self._build_user_data(user_id)` → `await run_sync(...)` (line 131)
- `self._repo.update_conversation_timestamp(conversation_id)` → `await run_sync(...)` (line 162)
- `self._fetch_vision_content(user_id)` → `await run_sync(...)` (line 136) — calls `self._repo.get_cleared_images()` and `self._repo.create_signed_url()`, both sync

The repo methods stay synchronous. `run_sync` runs them in the default executor to avoid blocking the event loop.

---

## Wave 3 — Auth + Cleanup (7 findings)

### C-1: Cache ban check in Redis

**File:** `app/api/deps.py`

Add `get_redis` as a dependency to `get_current_user`. Replace the inline Supabase query with a caching helper:

1. Check Redis key `ban:{user_id}` first
2. On cache miss → query Supabase, cache result with 60s TTL (`ban:{user_id}` = `"0"` or `"1"`)
3. On cache hit `"1"` → raise 403

Invalidation: in the admin ban/unban endpoint (`app/api/admin.py`), delete `ban:{user_id}` after the DB write. This ensures the ban takes effect within 60s passively, or immediately if the admin endpoint triggers invalidation.

### L-5: Password max_length

**File:** `app/api/auth.py`

Add `max_length=128` to `RegisterRequest.password`. Prevents bcrypt DoS on oversized inputs.

### L-1: Remove dead config

**File:** `app/config/__init__.py`

Delete `GENERATION_OUTPUT_RESOLUTION: int = 1024`. Zero references in codebase.

### L-2: Fix type

**Files:** `app/generation/models.py`, `app/generation/adapters/falai.py`

Change `max_sequence_length: str = "512"` to `max_sequence_length: int = 512` in `GenerationOptions`. Update `_build_pulid_request` to pass it as-is.

### L-3: Fix misleading comment

**File:** `app/config/__init__.py`

Change `OPENAI_API_KEY` comment from "falls back to ANTHROPIC_API_KEY" to "Required when ADAPTER__LLM_ADAPTER=anthropic (used for embeddings via OpenAI API)".

### L-4: Conditional Content-Type in mobile

**File:** `mobile/lib/api.ts`

Only set `Content-Type: application/json` when `options.body` is present:

```typescript
const headers: Record<string, string> = {
    ...options.headers,
};
if (options.body) {
    headers["Content-Type"] ??= "application/json";
}
```

### L-6: Card-web type-check in CI

Depends on CI setup. If GitHub Actions workflow exists, add `npm run type-check` step after `npm run lint`. If no CI exists, skip — not worth creating an entire pipeline for one check pre-launch.

---

## Testing Strategy

Each wave includes its own verification:

**Wave 1:** Run existing Python test suite. For the H-2 module refactor, verify output equivalence: create a test that calls `build_prompt()` with 3 fixed `AnalysisResult` inputs and a deterministic seed, asserting the returned `(prompt, negative, adaptive_params)` tuple matches expected values. This serves as both a refactor safety net and a regression test going forward.

**Wave 2:** New `tests/test_advisor_smoke.py` (C-2). Run existing tests. Content filter changes can be verified by running the existing test suite — any test using forbidden terms will catch regressions.

**Wave 3:** Run existing tests. Mobile TypeScript check (`npx tsc --noEmit`). Card-web lint + test.

---

## Execution Order

```
Wave 1 (generation pipeline) → Wave 2 (advisor) → Wave 3 (auth + cleanup)
```

Each wave is a single branch + PR + merge. No cross-wave dependencies.

**Intra-wave ordering (Wave 2):** Commit C-2 (model identifier update) before H-4 (model selection logic), since H-4 references `_MODEL_HAIKU` which uses the constant updated by C-2.
