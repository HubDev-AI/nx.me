# Auto Review Log

**Project:** NXME.ai
**Started:** 2026-03-19
**Reviewer:** Claude Opus 4.6 (internal — Codex MCP unavailable)

---

## Round 1 (2026-03-19 14:50 UTC)

### Assessment (Summary)
- Score: 7/10
- Verdict: Almost ready — strong engineering discipline, but 6 issues remain
- Overall: Post-audit codebase is clean. The 21-finding remediation (Waves 1-3) addressed the major architectural gaps. Remaining issues are at the edges — async correctness, missing validation, and one logic bug.

### Findings

#### 1. MEDIUM: Nudge eligibility functions are async but contain zero awaits

**Files:** `app/advisor/nudge_eligibility.py:23,46,83`

All three eligibility functions (`find_weekly_checkin_eligible`, `find_milestone_eligible`, `find_re_engagement_eligible`) are declared `async def` but contain no `await` expressions. They call synchronous repo methods directly. This means:
- They block the event loop during DB calls
- The `async` declaration is misleading — callers `await` them expecting non-blocking behavior

**Fix:** Either wrap repo calls with `run_sync()` (consistent with M-8 fix in Wave 2), or remove `async` and call them synchronously.

#### 2. MEDIUM: `MODEL_HAIKU` in nudge_policy.py is evaluated at import time

**File:** `app/advisor/nudge_policy.py:23`

```python
MODEL_HAIKU = settings.ADVISOR_MODEL_HAIKU
```

This captures the model ID at import time. If settings are overridden for testing (e.g., monkeypatch), the nudge scheduler still uses the original value. The same pattern was correctly avoided in `service.py` which reads from settings at call time.

**Fix:** Use `settings.ADVISOR_MODEL_HAIKU` directly in `nudge_scheduler.py` instead of the module-level alias.

#### 3. LOW: Stripe webhook returns 400 for invalid signature instead of 401

**File:** `app/api/webhooks.py:45-48`

The docstring says "AC-4: Invalid signature returns 401" but the code raises `HTTP_400_BAD_REQUEST`. This contradicts the spec's acceptance criteria.

**Fix:** Change to `status.HTTP_401_UNAUTHORIZED`.

#### 4. LOW: `_handle_subscription_created` does tier upgrade + subscription insert non-atomically

**File:** `app/api/webhooks.py:167-179`

Two separate DB calls: `insert_subscription()` then `update_user_tier()`. If the second fails, the subscription row exists but the tier is wrong. The credit purchase path correctly uses an atomic RPC (`handle_checkout_credit_atomic`), but subscription creation doesn't.

**Fix:** Wrap in a single RPC or accept the risk (watchdog can reconcile). Document the trade-off.

#### 5. LOW: Readiness endpoint calls Supabase synchronously in async handler

**File:** `app/api/health.py:43-44`

```python
supabase.table("tiers").select("id").limit(1).execute()
```

This blocks the event loop. The Redis ping on line 36 correctly uses `await`. Inconsistent.

**Fix:** Wrap with `await run_sync(...)` or use `loop.run_in_executor()`.

#### 6. INFO: `_get_client_ip` duplicated between auth.py and social.py

**Files:** `app/api/auth.py:44-55`, `app/api/social.py:36-44`

Same function, slightly different implementations (auth version is more verbose). Should be a shared utility.

**Fix:** Extract to a shared helper in `app/api/deps.py` or a utility module. Low priority.

### Actions Taken
- None (assessment only)

### Status
- Continuing to Round 2

---

## Round 2 (2026-03-19 15:00 UTC)

### Actions Taken
All 5 actionable findings fixed (Finding 4 — non-atomic subscription — documented as accepted risk):

1. **Nudge eligibility async** — wrapped all 6 sync repo calls with `run_sync()` in nudge_eligibility.py
2. **MODEL_HAIKU import-time eval** — replaced with `settings.ADVISOR_MODEL_HAIKU` at call site in nudge_scheduler.py
3. **Webhook 400→401** — changed to `HTTP_401_UNAUTHORIZED` in webhooks.py
4. **Readiness sync call** — wrapped Supabase query with `run_sync()` in health.py
5. **Client IP dedup** — extracted `get_client_ip()` to deps.py, removed duplicates from auth.py and social.py

Commit: `2a3b15d`

### Re-Assessment
- Score: 8/10
- Verdict: Ready
- All Round 1 findings addressed. Finding 4 (non-atomic subscription creation) accepted as-is — Stripe retries failed webhooks, and the tier can be reconciled. No new issues found.
- 78 tests pass, 0 failures across all codebases.

### Status
- Loop complete — positive assessment reached (score >= 6, verdict = ready)
