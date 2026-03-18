# Code Quality Review

- Date: 2026-03-17
- Scope: app/**/*.py
- Reviewer: code-reviewer agent

---

## Findings

### Duplication

#### D-1: `_SLUG_TO_TIER_NAME` dict defined identically in two files (HIGH)

The exact same mapping `{"free": TRIAL, "credits": CREDIT_HOLDER, "premium": PREMIUM}` is defined in both `app/api/generation.py:53` and `app/api/entitlement.py:29`. Both import from `app/constants/tiers.py`.

**Fix:** Extract to `app/constants/tiers.py` as `SLUG_TO_TIER_NAME` and import from there.

#### D-2: `_ERROR_MESSAGES` dict for entitlement failures defined in two files (HIGH)

The same error-code-to-message mapping exists in both `app/api/deps.py:78` and `app/api/generation.py:63`. The generation.py copy is a subset (missing `TIER_FEATURE_LOCKED` and `TIER_CONCURRENT_LIMIT`) but all overlapping entries are identical.

**Fix:** Define once in `app/entitlement/models.py` alongside the error code constants, and import.

#### D-3: LLM adapter factory duplicated (MEDIUM)

`app/api/deps.py:get_llm_adapter()` and `app/advisor/nudge_scheduler.py:_get_llm_adapter()` contain identical logic: check `settings.ADAPTER__LLM_ADAPTER == "anthropic"`, return `AnthropicAdapter` or `MockLLMAdapter`.

**Fix:** Consolidate into `app/api/deps.py:get_llm_adapter()` and import from there, or move to a shared `app/advisor/deps.py`.

#### D-4: Default tier fetch duplicated in auth.py (MEDIUM)

The query `supabase.table("tiers").select("id").eq("is_default", True).eq("is_active", True).single().execute()` appears twice in `app/api/auth.py` (lines 162-169 and 432-446) -- once in `register()` and once in `social_login()`. The `TierRepository.get_default()` method in `app/entitlement/tier_repo.py` already exists for this purpose.

**Fix:** Use `TierRepository.get_default()` or extract a shared `_fetch_default_tier_id(supabase)` helper in auth.py.

#### D-5: CreditLedger instantiation scattered (LOW)

`CreditLedger(supabase)` is constructed ad-hoc in 5 locations: `app/api/auth.py:567`, `app/api/generation.py:277,537`, `app/generation/worker.py:304,347`, and `app/api/webhooks.py:244`. EntitlementService already holds a `_ledger` instance.

**Fix:** For API endpoints, inject via the `EntitlementService` dependency. For the worker, construct once in startup context. Eliminates repeated construction.

#### D-6: `process_generation_job` function is 290 lines (HIGH -- see Complexity section)

Within it, the httpx download-from-provider pattern (`async with httpx.AsyncClient() as client: resp = await client.get(url); bytes = resp.content`) is repeated 3 times (lines 174-176, 205-207, 241-243).

**Fix:** Extract to a `async def _download_image(url: str) -> bytes` helper.

#### D-7: Duplicate worker settings files (MEDIUM)

`app/generation/worker_settings.py` and `app/worker_settings.py` both define `WorkerSettings` with identical startup/shutdown logic. The unified `app/worker_settings.py` is a superset.

**Fix:** Delete `app/generation/worker_settings.py` if the unified worker is the intended entry point. If both are needed, extract shared startup logic into a common function.

#### D-8: Signed URL generation inline in generation.py (LOW)

`app/api/generation.py:410-440` builds signed URLs for before/after images by looking up image rows then calling `supabase.storage.from_(bucket).create_signed_url(...)`. The same pattern exists in `app/api/users.py:242-259`. `app/services/public_url.py` already provides `build_avatar_url` as a signed-URL helper but nothing for general image signing.

**Fix:** Add a `build_signed_image_url(supabase, image_id, bucket_fallback) -> str | None` helper to `app/services/public_url.py`.

---

### Dead Code

#### DC-1: Unused import `slugify` in auth.py when not in social login path (FALSE POSITIVE -- used)

`from slugify import slugify` at line 29 is used in `social_login()` (line 451). Not dead.

#### DC-2: `app/generation/worker_settings.py` is likely dead (MEDIUM)

The unified `app/worker_settings.py` includes all functions from the generation worker settings. Unless the generation-only worker is run independently, this file is unused.

**Action:** Verify deployment scripts. If only `app.worker_settings.WorkerSettings` is referenced, remove `app/generation/worker_settings.py`.

#### DC-3: `Literal` import unused in `app/generation/models.py` (LOW)

Line 6: `from typing import Literal` is imported but never used in the file.

#### DC-4: `hashlib` import unused in `app/generation/prompt_builder.py` (LOW)

Line 8: `import hashlib` is imported but never used.

#### DC-5: `timedelta` import unused in `app/generation/prompt_builder.py` (LOW)

Line 10: `from datetime import timedelta` is imported but never used.

#### DC-6: `os` import unused in `app/generation/modules/styling.py` (LOW)

Line 8: `import os` is imported but never used.

#### DC-7: `ImageFilter` import unused in `app/generation/face_cropper.py` (LOW)

Line 12: `from PIL import ImageFilter` is imported but never used.

#### DC-8: `GenerationOptions` import unused in `app/generation/prompt_builder.py` (LOW)

Line 13: `from app.generation.models import GenerationOptions` is imported but never used in the file.

---

### Complexity

#### CX-1: `process_generation_job` is ~290 lines (CRITICAL -- exceeds 50-line threshold by 480%)

`app/generation/worker.py:44-333` is the largest function in the codebase. It handles: job fetch, cancellation check, pre-flight checks, claim, concurrent guard, analysis fetch/deserialization, prompt building, source image URL signing, generation, cost tracking, provider download, storage write, NSFW screening, identity checking, retry with tighter params, color normalization, image row creation, credit commit, job status update, and error handling.

**Fix:** Break into composable steps:
1. `_fetch_and_claim_job(supabase, job_id) -> JobData | None`
2. `_build_generation_context(supabase, job_data) -> GenerationContext`
3. `_generate_and_validate(generator, ctx, source_bytes) -> ValidatedOutput`
4. `_finalize_job(supabase, job_id, output) -> None`

#### CX-2: `create_generation` endpoint is ~215 lines (HIGH)

`app/api/generation.py:118-341`. Inline entitlement checking (instead of the `require_entitlement` dependency) plus idempotency, tier lookup, queue depth check, credit reservation, and ARQ enqueue makes this handler overly complex.

**Fix:** Extract pre-generation checks into a `GenerationPreflightService` or at least break the handler into `_check_entitlement()`, `_validate_analysis()`, `_preflight_checks()`, and `_enqueue_job()` private helpers.

#### CX-3: `get_user_history` endpoint is ~150 lines (MEDIUM)

`app/api/users.py:139-295`. The batch-fetch-and-sign logic is well-structured but the function is long. The signing loop and entry assembly could be extracted.

**Fix:** Extract `_build_history_entries(analyses, supabase, settings) -> list[HistoryEntry]` helper.

#### CX-4: `get_job` endpoint is ~120 lines (MEDIUM)

`app/api/generation.py:356-474`. Three distinct status branches (queued/processing, completed, failed/cancelled) with different response construction.

**Fix:** Extract per-status builders: `_build_queued_response()`, `_build_completed_response()`, `_build_failed_response()`.

---

### Reuse Opportunities

#### R-1: Timestamp helper (LOW)

`datetime.now(tz=timezone.utc).isoformat()` appears 20+ times across the codebase. While individually trivial, a `utc_now_iso() -> str` utility function in `app/services/` or `app/utils.py` would reduce import noise and centralize any future format changes.

#### R-2: "Fetch-or-404" pattern (MEDIUM)

Multiple endpoints follow the same pattern:
1. `supabase.table(X).select(...).eq("id", id).maybe_single().execute()`
2. `if not result.data: raise HTTPException(404, detail="X not found")`
3. `if result.data["user_id"] != user_id: raise HTTPException(404, detail="X not found")`

This appears in: `get_analysis`, `create_generation` (analysis check), `get_job`, `cancel_job`, `delete_post`, `create_comment`, `report_post`.

**Fix:** A generic `fetch_owned_resource(supabase, table, id, user_id, select_cols) -> dict` helper in deps.py would eliminate 30+ lines of duplication.

#### R-3: Cursor pagination boilerplate (MEDIUM)

The "fetch limit+1, check has_more, slice, compute next_cursor" pattern is repeated in: `get_feed`, `get_comments`, `get_user_history`. All use the same structure with minor variations.

**Fix:** A `paginate(query, cursor_field, cursor_value, limit) -> PaginatedResult` utility would centralize this.

#### R-4: Entitlement error response building (MEDIUM)

The entitlement denial response structure `{"error": {"code": ..., "message": ..., "detail": {"limit": ..., "used": ..., ...}}}` is built inline in both `app/api/deps.py:require_entitlement()` and `app/api/generation.py:create_generation()` with identical field construction.

**Fix:** Add `EntitlementResult.to_http_detail() -> dict` method or a standalone `build_entitlement_error(result) -> dict` helper.

---

### Inconsistencies

#### I-1: `Optional[str]` vs `str | None` mixed in the same codebase (LOW)

`app/api/users.py` uses `Optional[str]` (old-style typing) while all other files use `str | None` (PEP 604). Same file also imports `from typing import Optional`.

**Fix:** Replace with `str | None` for consistency with the rest of the codebase.

#### I-2: Sync vs async endpoint handlers inconsistent (LOW)

Some endpoints are `async def` (register, social_login, create_analysis, create_generation) while others are plain `def` (verify_email, logout, delete_account, get_analysis, all user endpoints). The choice does not consistently correlate with whether the handler performs I/O that benefits from async. For example, `verify_email` performs multiple Supabase calls but is sync, while `create_analysis` is async.

**Note:** This is not a bug -- FastAPI handles both correctly via threadpool. But consistency would improve readability.

#### I-3: Error response format varies across endpoints (MEDIUM)

Some endpoints return structured error objects: `{"error": {"code": "...", "message": "..."}}` (generation, entitlement, advisor). Others return plain strings: `"Post not found"`, `"Not authorized"` (posts, users, analyses). Mobile clients parsing these responses will need to handle both formats.

**Fix:** Standardize on the structured format for all 4xx/5xx responses. Consider a shared `error_response(code, message)` helper.

#### I-4: Unreachable code after `raise` in logout (LOW)

`app/api/auth.py:526`: the comment `# The token will expire naturally even if server revocation failed.` appears after a `raise HTTPException(...)` statement, making it unreachable.

**Fix:** Move the comment above the `raise` or into the docstring.

#### I-5: `now_utc` variable name used for ISO string, not datetime (LOW)

Throughout the codebase, `now_utc = datetime.now(tz=timezone.utc).isoformat()` assigns an ISO string to a variable named `now_utc`, which reads as a datetime object. Minor naming issue.

---

### Security Notes (informational, not in scope but notable)

#### S-1: Webhook handler swallows processing errors (MEDIUM)

`app/api/webhooks.py:88-92`: After recording the event in `processed_webhook_events`, any processing error returns 200 with `{"status": "processing_error"}`. This prevents Stripe retries, which is the stated intent, but means failed credit grants or tier changes require manual recovery with no automatic alerting mechanism visible in code.

#### S-2: `find_milestone_eligible` fetches ALL `analysis_insight` rows (MEDIUM)

`app/advisor/nudge_eligibility.py:83-88`: Fetches all `user_memories` of type `analysis_insight` for every milestone count in the loop. For a large user base, this is an unbounded full-table scan run daily.

**Fix:** Use a COUNT GROUP BY query via Supabase RPC instead of client-side counting.

---

## Summary

| Category | Count | Critical | High | Medium | Low |
|---|---|---|---|---|---|
| Duplication | 8 | 0 | 2 | 3 | 3 |
| Dead Code | 8 | 0 | 0 | 1 | 7 |
| Complexity | 4 | 1 | 1 | 2 | 0 |
| Reuse Opportunities | 4 | 0 | 0 | 3 | 1 |
| Inconsistencies | 5 | 0 | 0 | 1 | 4 |
| Security Notes | 2 | 0 | 0 | 2 | 0 |
| **Total** | **31** | **1** | **3** | **12** | **15** |

### Top 5 Priority Actions

1. **CX-1:** Refactor `process_generation_job` (290 lines) into composable steps -- this is the riskiest function in the codebase due to its complexity and error-handling surface area.
2. **D-1 + D-2:** Extract `_SLUG_TO_TIER_NAME` and `_ERROR_MESSAGES` to shared locations -- quick wins that reduce drift risk.
3. **D-3:** Consolidate LLM adapter factory to one location.
4. **I-3 + R-4:** Standardize error response format and extract entitlement error builder.
5. **S-2:** Replace full-table scan in `find_milestone_eligible` with a COUNT GROUP BY RPC before user base grows.

### Files Exceeding Size Thresholds

No files exceed the 800-line threshold. Largest files:
- `app/api/auth.py` -- 612 lines (within limit but approaching)
- `app/api/generation.py` -- 558 lines
- `app/advisor/service.py` -- 492 lines

### Functions Exceeding 50-line Threshold

| File | Function | Lines |
|---|---|---|
| `app/generation/worker.py` | `process_generation_job` | ~290 |
| `app/api/generation.py` | `create_generation` | ~215 |
| `app/api/users.py` | `get_user_history` | ~150 |
| `app/api/generation.py` | `get_job` | ~120 |
| `app/api/auth.py` | `social_login` | ~125 |
| `app/api/auth.py` | `register` | ~155 |
| `app/api/auth.py` | `delete_account` | ~65 |
| `app/api/posts.py` | `get_comments` | ~55 |
| `app/api/posts.py` | `create_post` | ~85 |
