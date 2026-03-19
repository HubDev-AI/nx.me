# Architecture & Code Audit — 2026-03-19

Comprehensive audit across backend (Python/FastAPI), mobile (React Native/Expo), and card-web (Next.js). Covers architecture, code quality, AI feature settings, and security.

---

## Summary

| Severity | Count |
|----------|-------|
| Critical | 2 |
| High | 5 |
| Medium | 8 |
| Low | 6 |
| **Total** | **21** |

---

## Critical

### C-1: Ban check DB call on every authenticated request (no caching)

**File:** `app/api/deps.py:77-86`

`get_current_user()` hits Supabase on every request to check `is_banned`. The code even has a comment acknowledging this: *"Consider caching in Redis if this becomes a performance bottleneck."* This is not a "consider" — at scale, every authenticated API call adds a synchronous DB round-trip. With 100 RPM, that's 100 extra queries/min for a column that changes approximately never.

**Fix:** Cache `is_banned` in Redis with a 60s TTL. Invalidate on ban/unban via the admin endpoint.

---

### C-2: Advisor model identifiers are outdated

**File:** `app/config/__init__.py:66,89`

```python
ADVISOR_MODEL_HAIKU: str = "claude-3-haiku-20240307"
ADVISOR_MODEL_SONNET: str = "claude-3-5-sonnet-20241022"
```

These reference old Claude models (March 2024 Haiku, October 2024 Sonnet). The latest models are Claude 4.5/4.6 family (Haiku: `claude-haiku-4-5-20251001`, Sonnet: `claude-sonnet-4-6`). Using outdated model IDs means:
- Higher cost per token (older models are not price-optimized)
- Missing improved instruction following and safety
- Eventual deprecation will break the advisor entirely

**Fix:** Update to latest model IDs: `claude-haiku-4-5-20251001` and `claude-sonnet-4-6`.

---

## High

### H-1: Identity retry uses global threshold instead of per-tier threshold

**File:** `app/generation/worker.py:357`

First identity check correctly looks up per-tier threshold (lines 286-299), but the **retry** identity check on line 357 hardcodes `settings.IDENTITY_SIMILARITY_THRESHOLD` (global 0.80):

```python
retry_identity = await loop.run_in_executor(
    None, check_identity, source_image_bytes, retry_image_bytes,
    settings.IDENTITY_SIMILARITY_THRESHOLD,  # BUG: should use identity_threshold
)
```

A premium user with a 0.70 per-tier threshold could pass the first check but fail the retry with the stricter global 0.80.

**Fix:** Pass `identity_threshold` (the per-tier value already fetched) instead of `settings.IDENTITY_SIMILARITY_THRESHOLD`.

---

### H-2: `StylingModule` instantiated but never used in prompt builder

**File:** `app/generation/prompt_builder.py:183-184`

```python
from app.generation.modules.styling import StylingModule
_module = StylingModule()  # noqa: F841
```

A module is imported, instantiated, and immediately discarded (`noqa: F841` suppresses the unused warning). This is either dead code or a module that should be wired into the prompt building pipeline but isn't.

**Fix:** Remove if dead code, or wire the module's output into the prompt if it should be active.

---

### H-3: `asyncio.create_task` without task reference (fire-and-forget)

**File:** `app/advisor/service.py:182`

```python
asyncio.create_task(_extract_with_logging())
```

The task is created but the reference is discarded. If the task raises an unhandled exception, Python will print a warning to stderr but the error is effectively lost. More importantly, if the application shuts down, in-flight tasks are silently cancelled.

**Fix:** Store the task reference and attach an error callback, or use a structured task group.

---

### H-4: `_select_model` always returns Sonnet — no load degradation implemented

**File:** `app/advisor/service.py:226-232`

The spec says ">50 messages/day → degrade to Haiku" but the implementation is a stub:

```python
def _select_model(self) -> str:
    """Spec Section 10: >50 messages/day → degrade to Haiku.
    For now, always Sonnet (daily count check left for future story)."""
    return _MODEL_SONNET
```

Without the degradation, a single user can drive unlimited Sonnet costs ($0.003/1K input tokens vs $0.00025/1K for Haiku — 12x cost difference).

**Fix:** Implement the daily message count check using the existing Redis rate limit key (`advisor_chat_rate:{user_id}`).

---

### H-5: No NSFW screening in mock adapter mode

**File:** `app/generation/worker.py:263`

```python
if settings.ADAPTER__NSFW_ADAPTER == "rekognition":
    # ... screen output
```

When `ADAPTER__NSFW_ADAPTER` is `"mock"` (the default), NSFW screening is completely skipped. Any development or staging environment running with mock adapters has zero content safety on generated outputs.

**Fix:** The mock NSFW adapter should return a deterministic safe result (not skip entirely). Change to `if settings.ADAPTER__NSFW_ADAPTER != "mock":` or always run screening with the configured adapter.

---

## Medium

### M-1: `import inside function body` pattern used inconsistently

**Files:** `app/generation/worker.py:198,249,403`, `app/api/auth.py:268,459`

Some imports are at module level, others are inside functions (`import httpx`, `import PIL.Image`). The inline imports in worker.py were originally to avoid import-time side effects, but `httpx` and `PIL` have no startup side effects. This makes the dependency graph harder to trace and adds micro-overhead on every call.

**Fix:** Move stable imports (`httpx`, `PIL.Image`) to module level. Keep conditional imports (adapter selection) inline.

---

### M-2: Prompt builder uses `random.choice` — non-deterministic generation

**File:** `app/generation/prompt_builder.py:147,164,205`

Identity phrases, style themes, and lighting keywords are selected randomly. This means identical inputs produce different prompts, making:
- Debugging harder (can't reproduce a generation)
- A/B testing impossible (no control group)
- Identity retry may get a different prompt than the original (changing two variables at once)

**Fix:** Seed `random` with a hash of the analysis ID for reproducibility within a single generation job. Use `random.Random(seed)` instance, not the global `random`.

---

### M-3: `_post_check` sentence counter is imprecise

**File:** `app/advisor/service.py:551-558`

```python
sentence_count = (
    response.count(". ") + response.count("? ") + response.count("! ") + 1
)
```

This fails on: sentences ending at the last character (no trailing space), sentences with "Dr. Smith" (counts as two), abbreviations like "U.S.A.", numbered lists ("1. First"). The check is supposed to enforce "say less" but will trigger false positives on responses containing abbreviations.

**Fix:** Use a simple regex split `re.split(r'[.!?]+\s', text)` or accept the imprecision with a higher threshold.

---

### M-4: Memory dedup fingerprint truncates at 80 chars

**File:** `app/advisor/memory_manager.py:181`

```python
key = str(row.get("content", ""))[:80]
```

Two memories with the same first 80 characters but different endings will be treated as duplicates. This is likely to happen with structured content like analysis insights where the face_shape and symmetry fields come first.

**Fix:** Use a hash of the full content string instead of truncation.

---

### M-5: `content_filter.scan_output` uses substring matching — false positives

**File:** `app/advisor/content_filter.py:121-126`

The term `"hot"` will match "hot dog", "photo", "hotfix". The term `"rating"` will match "operating", "celebrating". These false positives cause unnecessary LLM retries and fallback responses.

**Fix:** Use word-boundary matching: `re.search(r'\bhot\b', lower)` instead of `term in lower`.

---

### M-6: No timeout on Anthropic/OpenAI API calls

**Files:** `app/advisor/adapters/anthropic_adapter.py:74,100`

The Anthropic and OpenAI calls have no explicit timeout. If the API hangs, the request will block until the FastAPI/uvicorn timeout kills it (typically 30-60s), holding a worker thread the entire time.

**Fix:** Pass `timeout=httpx.Timeout(30.0)` to the Anthropic client constructor, and `timeout=15.0` to the OpenAI embeddings call.

---

### M-7: Worker re-instantiates `FalAiAdapter` on every job

**File:** `app/generation/worker.py:68-74`

```python
def _get_generator() -> GlowUpGeneratorPort:
    if settings.ADAPTER__IMAGE_GENERATION_ADAPTER == "falai":
        from app.generation.adapters.falai import FalAiAdapter
        return FalAiAdapter()
    ...
```

Each job creates a new `FalAiAdapter`, which calls `import fal_client` and initializes a new client. The adapter is stateless and safe to reuse.

**Fix:** Cache the adapter instance at module level or in the worker context (`ctx`).

---

### M-8: `_build_user_data` in AdvisorService is sync DB call in async endpoint

**File:** `app/advisor/service.py:131,445-460`

`_build_user_data` calls `self._repo.get_latest_analysis_insight()` and `self._repo.count_analysis_insights()` synchronously. In an async FastAPI endpoint, these block the event loop.

**Fix:** Wrap in `run_sync()` or make the repo methods async-compatible.

---

## Low

### L-1: `GENERATION_OUTPUT_RESOLUTION` config value is set but never used

**File:** `app/config/__init__.py:105`

```python
GENERATION_OUTPUT_RESOLUTION: int = 1024
```

Grep shows this config value is never referenced anywhere in the codebase. The actual output resolution is controlled by `image_size: "square_hd"` in `GenerationOptions` (hardcoded default).

---

### L-2: `max_sequence_length` is typed as `str` instead of `int`

**File:** `app/generation/models.py:62`

```python
max_sequence_length: str = "512"
```

This should be `int = 512`. It works because fal.ai accepts both, but it's semantically wrong and will cause type confusion if used in arithmetic.

---

### L-3: `OPENAI_API_KEY` comment says "falls back to ANTHROPIC_API_KEY" but no fallback exists

**File:** `app/config/__init__.py:37`

```python
OPENAI_API_KEY: str = ""  # For embeddings (advisor memory); falls back to ANTHROPIC_API_KEY
```

There is no fallback logic. `AnthropicAdapter.__init__` raises `ValueError` if `OPENAI_API_KEY` is empty. The comment is misleading.

---

### L-4: Mobile `apiFetch` always sets Content-Type to application/json

**File:** `mobile/lib/api.ts:21-24`

```typescript
const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...options.headers,
};
```

This will cause issues if a future endpoint needs `multipart/form-data` (e.g., file upload). The Content-Type should only be set when the body is JSON.

---

### L-5: `password` field in `RegisterRequest` has no max_length

**File:** `app/api/auth.py:72`

```python
password: str = Field(min_length=8)
```

No `max_length`. A malicious client could send a 10MB password, which Supabase would attempt to hash (bcrypt is CPU-intensive and deliberately slow on long inputs).

**Fix:** Add `max_length=128`.

---

### L-6: Card-web `type-check` script exists but is not run in CI

**File:** `card-web/package.json`

The `type-check` script (`tsc --noEmit`) is defined but not called from any CI workflow or pre-commit hook. TypeScript errors can be merged without detection.

---
