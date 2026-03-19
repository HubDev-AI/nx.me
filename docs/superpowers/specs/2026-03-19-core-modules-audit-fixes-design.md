# Core Modules Audit Fixes Design

**Date:** 2026-03-19
**Scope:** Fix all 38 findings from `docs/refine-logs/FINAL_PROPOSAL.md`
**Modules:** `app/advisor/` (18 findings), `app/generation/` (12 findings), `app/config/` (shared config additions)

## Approach

Fix all code findings (no new test suites). Parallel execution by module — advisor and generation are cleanly separated. Config changes are additive (append new fields to Settings class).

## Config Additions (`app/config/__init__.py`)

New fields on `Settings`:

| Field | Type | Default | Source Finding |
|-------|------|---------|---------------|
| `advisor_chat_rate_limit_window_seconds` | int | 3600 | A-3 |
| `advisor_embedding_model` | str | "text-embedding-3-small" | A-6 |
| `advisor_model_haiku` | str | "claude-haiku-4-5-20251001" | A-5 |
| `identity_retry_id_weight_delta` | float | 0.10 | G-4 |
| `identity_retry_id_weight_cap` | float | 0.95 | G-4 |
| `identity_retry_guidance_delta` | float | 0.5 | G-4 |
| `identity_retry_guidance_floor` | float | 3.5 | G-4 |
| `color_norm_brightness_delta` | int | 20 | G-8 |
| `color_norm_factor_min` | float | 0.8 | G-8 |
| `color_norm_factor_max` | float | 1.2 | G-8 |
| `generation_httpx_timeout_seconds` | float | 30.0 | G-5 |

## Advisor Fixes

### HIGH

- **A-1**: Redis distributed lock on `conversation_id` before auto-summarization in `service.py`
- **A-2**: Wrap conversation + first message INSERT in transaction in `service.py`
- **A-3**: Use `settings.advisor_chat_rate_limit_window_seconds` instead of hardcoded 3600
- **A-4**: Raise `ValueError` at adapter init if `OPENAI_API_KEY` missing

### MEDIUM

- **A-5**: Single `advisor_model_haiku` config field, imported in both `service.py` and `nudge_policy.py`
- **A-6**: Use `settings.advisor_embedding_model` instead of hardcoded string
- **A-7**: try/except on cursor split in `advisor_repo.py`, raise HTTPException 400
- **A-8**: Log warning + skip unverified images in `memory_manager.py`
- **A-9**: Structured error logging with counter for memory extraction failures
- **A-10**: Add RTL override (U+202E), zero-width joiners, math alphanumeric variants to content_filter patterns
- **A-11**: Add `user_id` ownership checks in delete memory and mark nudge read routes

### LOW

- **A-12**: `logger.warning` on rate limit hits
- **A-13**: TODO comment for Redis key cleanup on user deletion
- **A-14**: Extract visual trigger keywords to module-level constant
- **A-15**: Violation-type-specific fallback messages
- **A-16**: Structured error codes (RATE_LIMITED, CONTENT_VIOLATION, LLM_TIMEOUT)
- **A-17**: `asyncio.wait_for` timeout on summarization
- **A-18**: Dedup timestamp guard comment

## Generation Fixes

### HIGH

- **G-1**: Implement fallback model cascade (PuLID -> Flux Dev -> InstantID) in `worker.py`
- **G-2**: Ensure DECR in try/finally with TTL-based auto-cleanup for concurrent counter
- **G-3**: Re-raise or queue storage delete failures instead of swallowing
- **G-4**: Extract identity retry parameters to config fields

### MEDIUM

- **G-5**: Explicit `timeout=settings.generation_httpx_timeout_seconds` on all httpx calls
- **G-6**: Read per-tier identity threshold from tier config
- **G-7**: Circuit breaker hysteresis — require 3 consecutive successes to close
- **G-8**: Extract color normalization constants to config
- **G-9**: Expand URL allowlist for fallback provider CDNs

### LOW

- **G-10**: Add ArcFace model pre-load to API lifespan
- **G-11**: Log generated image dimensions
- **G-12**: Document 86400s vs 25h intentional discrepancy

## Execution

1. Add all config fields to `app/config/__init__.py`
2. Fix advisor module (A-1 through A-18) in parallel with generation module (G-1 through G-12)
3. Lint + build check
4. PR and merge to dev
