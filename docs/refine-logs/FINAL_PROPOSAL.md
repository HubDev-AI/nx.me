# NXME Core Modules Audit: Advisor & Generation

**Date:** 2026-03-19
**Scope:** `app/advisor/` (13 files) and `app/generation/` (11 files)
**Verdict:** Both modules are well-architected but have production-readiness gaps

---

## Executive Summary

The advisor and generation modules form the revenue core of NXME. Both follow clean architectural patterns (adapter/port, separation of concerns, spec-driven implementation). However, both share critical gaps: **zero test coverage**, **race conditions under concurrency**, and **hardcoded operational parameters** that should be configurable.

**Total findings: 38** (8 HIGH, 14 MEDIUM, 16 LOW)

---

## Advisor Module (app/advisor/)

### Architecture

```
Route Layer (app/api/advisor.py)
  ↓ require_feature("advisor_chat")
AdvisorService (service.py)
  ├→ ContentFilter (sanitize input, rate limit, output scan)
  ├→ ConversationManager (create, load history, auto-summarize)
  ├→ MemoryManager (pgvector hybrid retrieval, extraction via Haiku)
  ├→ ContextBuilder (SOUL + user_data + memories + history → messages)
  ├→ LLMPort/AnthropicAdapter (Claude Sonnet/Haiku, OpenAI embeddings)
  └→ AdvisorRepository (persist messages, nudges, memories)
```

### HIGH Severity

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| A-1 | **Race condition on auto-summarization** | service.py:98-112 | Two simultaneous messages can both trigger summarize → duplicate summary rows + message soft-delete corruption. No lock on conversation_id. |
| A-2 | **No transaction atomicity on conversation creation** | service.py:408-410 | Conversation INSERT succeeds but message INSERT fails → orphaned conversation row. Not wrapped in transaction. |
| A-3 | **Hardcoded rate limit window (3600s)** | content_filter.py:97 | Cannot adjust rate limit window without code change. Should be `ADVISOR_CHAT_RATE_LIMIT_WINDOW_SECONDS` config. |
| A-4 | **OpenAI API key fallback to "not-configured"** | anthropic_adapter.py:31-34 | If OPENAI_API_KEY missing, logs warning + uses dummy string. Embedding calls fail at runtime instead of failing fast at startup. |

### MEDIUM Severity

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| A-5 | Duplicate model constants | service.py, nudge_policy.py | `_MODEL_HAIKU` defined in both files; model version change requires 2 edits |
| A-6 | No config for embedding model | anthropic_adapter.py:18 | `text-embedding-3-small` hardcoded; version change requires code edit |
| A-7 | No cursor validation | advisor_repo.py:104-109, 177-184 | Cursor split on "\|" with no try/except; malformed cursor crashes request |
| A-8 | Image ownership check best-effort | memory_manager.py:282-296 | If Supabase is down during ownership check, proceeds anyway with unverified data |
| A-9 | Silent memory extraction failures | service.py:151-167 | Extraction errors caught but no metric/counter logged; invisible accumulation |
| A-10 | Prompt injection patterns incomplete | content_filter.py:36-56 | Missing RTL override (U+202E), zero-width joiners, math alphanumeric variants |
| A-11 | No user ownership verification in routes | api/advisor.py | Delete memory, mark nudge read endpoints don't double-check `user_id == resource.user_id` |

### LOW Severity

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| A-12 | No logging for rate limit hits | content_filter.py:88-103 | Rate limit enforced but no log event; no visibility into per-user throttling |
| A-13 | Rate limit Redis key cleanup missing | content_filter.py:94-102 | No cleanup for deleted users |
| A-14 | Visual trigger keywords hardcoded | context_builder.py:17 | ("look at", "see my", "compare", "photo") not configurable |
| A-15 | Fallback response hardcoded | content_filter.py:119-121 | Single generic fallback for all C-2 violations |
| A-16 | No error codes on LLM failures | service.py:189-209 | Client can't distinguish rate limit vs content violation vs timeout |
| A-17 | Conversation summarization blocks response | service.py:98-111 | Inline await on Haiku call adds ~1s latency; no timeout |
| A-18 | Memory dedup can miss async extractions | memory_manager.py | Extraction is fire-and-forget; out-of-order dedup may fail |

---

## Generation Module (app/generation/)

### Architecture

```
API (/analyses/{analysis_id}/generate)
  ↓ Entitlement Check → Credit Reserve → JobRepository.create()
  ↓ ARQ.enqueue_job() → Queue Lane (premium/credit/trial)
  ↓
process_generation_job (ARQ Worker)
  ├─ _fetch_and_claim_job() [CostTracker checks, atomic QUEUED→PROCESSING]
  ├─ _build_generation_context() [PromptBuilder, signed URLs]
  ├─ _generate_and_validate() [fal.ai → NSFW screen → identity check]
  └─ _finalize_job() [color normalize → upload → credit commit → COMPLETED]

watchdog_stuck_jobs (ARQ Cron, every minute)
  └─ Recovers PROCESSING/FINALIZING jobs beyond timeout
```

### HIGH Severity

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| G-1 | **Fallback models not implemented** | worker.py:382 | Config defines Flux Dev img2img and InstantID as fallbacks, but code fails immediately on timeout. No model cascade. Lost revenue. |
| G-2 | **Concurrent counter can leak** | worker.py:415-416 | Redis INCR in entitlement, DECR in worker finally. Worker crash before finally → counter stuck. User can't generate until 90s watchdog recovery. |
| G-3 | **Orphaned images on storage delete failure** | worker.py:223-226, 292-295 | NSFW/identity failures attempt image delete. If delete fails, exception caught + logged but image exists as orphan. Storage bloat + inconsistency. |
| G-4 | **Identity retry parameters hardcoded** | worker.py:254-262 | id_weight (+0.10, cap 0.95) and guidance_scale (-0.5, floor 3.5) deltas can't be tuned without code change. |

### MEDIUM Severity

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| G-5 | No explicit timeout on httpx calls | worker.py:201-204, 231-234, 271-274 | Falls back to httpx default (5s); provider CDN hang → job hangs until ARQ timeout |
| G-6 | Per-tier identity threshold not implemented | worker.py:243 | Spec mentions per-tier thresholds (Amendment A-5) but code always uses global `IDENTITY_SIMILARITY_THRESHOLD` |
| G-7 | Circuit breaker can flap | cost_tracker.py:243-278 | In HALF_OPEN, one success → close. Next batch fails → reopen. No hysteresis (require 2-3 consecutive successes). |
| G-8 | Color normalization constants hardcoded | color_normalizer.py:20-22 | Brightness threshold (20) and clamp (0.8-1.2) not in config |
| G-9 | URL allowlist doesn't cover fallback providers | worker.py:40 | Only fal.ai domains + GCS. If fallback model uses different CDN, validation fails. |

### LOW Severity

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| G-10 | ArcFace model not pre-loaded in API lifespan | main.py:98-104 | Only pre-loaded in worker; first job may incur load latency |
| G-11 | No logging of generated image dimensions | worker.py:210 | Makes debugging image quality issues harder |
| G-12 | Daily cap uses fixed 86400s vs rolling 25h | cost_tracker.py:159 | Minor inconsistency between daily cap and rolling cost bucket TTL (intentional but undocumented) |

---

## Cross-Cutting Issues

### Zero Test Coverage (CRITICAL)

**Neither module has any tests.** The test directory contains 11 test files, none covering advisor or generation.

| Missing Test Suite | Risk |
|---|---|
| `test_advisor_service.py` | Chat flow, memory extraction, conversation summarization |
| `test_content_filter.py` | Prompt injection detection, rate limiting |
| `test_memory_manager.py` | Hybrid retrieval, dedup, embedding |
| `test_nudge_scheduler.py` | Job dispatch, eligibility queries |
| `test_generation_worker.py` | Job lifecycle (claim, generate, finalize, fail) |
| `test_cost_tracker.py` | Circuit breaker state machine, cost aggregation |
| `test_identity_checker.py` | ArcFace comparison, threshold logic |
| `test_prompt_builder.py` | Prompt assembly, keyword extraction |

### Config Gaps Summary

Both modules have values that should be in `app/config/__init__.py`:

| Current Location | Value | Recommended Config Key |
|---|---|---|
| content_filter.py | 3600 (rate window) | `ADVISOR_CHAT_RATE_LIMIT_WINDOW_SECONDS` |
| anthropic_adapter.py | "text-embedding-3-small" | `ADVISOR_EMBEDDING_MODEL` |
| worker.py | id_weight delta 0.10 | `IDENTITY_RETRY_ID_WEIGHT_DELTA` |
| worker.py | guidance_scale delta 0.5 | `IDENTITY_RETRY_GUIDANCE_DELTA` |
| color_normalizer.py | brightness threshold 20 | `COLOR_NORM_BRIGHTNESS_DELTA` |
| color_normalizer.py | factor clamp 0.8-1.2 | `COLOR_NORM_FACTOR_MIN/MAX` |

---

## Priority Matrix

### Must Fix Before Production

1. **A-1** Race condition on auto-summarization (add Redis lock)
2. **A-2** Transaction atomicity on conversation creation
3. **A-4** Fail fast on missing OPENAI_API_KEY
4. **G-2** Concurrent counter leak recovery (faster cleanup cron)
5. **A-11** User ownership verification in advisor routes

### Should Fix Soon

6. **G-1** Implement fallback model cascade
7. **A-3** Configurable rate limit window
8. **G-3** Don't swallow storage delete exceptions
9. **G-7** Circuit breaker hysteresis
10. **A-10** Expand prompt injection patterns

### Test Coverage (Parallel Track)

11. Start with `test_content_filter.py` (security-critical)
12. Then `test_generation_worker.py` (revenue-critical)
13. Then `test_cost_tracker.py` (circuit breaker state machine)
14. Expand from there

---

## What's Working Well

- **Adapter pattern**: Clean separation between LLM/generation providers and business logic
- **Idempotent job claim**: Conditional UPDATE prevents double-processing
- **Credit ledger atomicity**: Reserve → commit/release pattern is solid
- **Spec-driven development**: Both modules follow their specs closely
- **NSFW pipeline**: Multi-layer safety checks with proper cleanup
- **Concurrent generation limiting**: Lua script atomicity in Redis
- **Memory hybrid scoring**: pgvector + recency + importance weighting
- **Content filter**: 16 prompt injection patterns with normalization
- **Queue priority lanes**: Premium/credit/trial separation
