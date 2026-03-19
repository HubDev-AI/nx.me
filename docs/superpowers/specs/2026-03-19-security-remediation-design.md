# Security Audit Remediation — Design Spec

**Date:** 2026-03-19
**Branch:** `fix/app-audit-2026-03-19`
**Audit report:** `docs/security-audit-2026-03-19.md`

## Overview

Fix all 60 actionable findings from the 2026-03-19 security audit across backend, mobile, card-web, and infrastructure. No new features or architectural changes — surgical edits only.

## Approach

Phase 0 (sequential prerequisite) → 5 parallel agents by security concern → verification phase.

### File Ownership Rules

Each shared file has exactly one agent owner. Other agents must NOT edit files they don't own.

| Shared File | Owner | Fixes Consolidated |
|-------------|-------|--------------------|
| `app/main.py` | Agent 4 | H-8, C-2, M-2, M-25 |
| `mobile/app/_layout.tsx` | Agent 4 | M-12, M-10, M-11 + H-6 StripeProvider urlScheme change |
| `mobile/lib/api.ts` | Agent 3 | L-13, M-13, L-11 |
| `mobile/app/card/[username].tsx` | Agent 3 | M-14, L-9 |
| `card-web/src/app/api/revalidate/route.ts` | Agent 1 | M-17, M-18 |
| `app/api/social.py` | Agent 3 | H-2, L-3 |
| `app/generation/worker.py` | Agent 3 | H-1, L-4 |
| `supabase/config.toml` | Agent 1 | H-9, M-20, M-21, L-19 |
| `docker-compose.yml` | Agent 5 | H-10, L-22 |
| `Dockerfile` | Agent 5 | M-22, L-18 |

### Migration Ordering

All new migrations must use sequential timestamps. Agents 2 and 5 create migrations:
- `0020_trial_grant_unique.sql` (Agent 2 — C-3)
- `0021_security_definer_search_path.sql` (Agent 2 — M-23)
- `0022_stuck_jobs_index.sql` (Agent 5 — L-7)

## Phase 0 — Prerequisites (sequential, before agents start)

Create `app/constants/__init__.py` and `app/constants/tiers.py` with tier ID constants. This module is imported by `webhooks.py`, `entitlement.py`, and `generation.py` — all agents depend on it existing.

## Agent 1 — Auth & Secrets (9 fixes)

| ID | Severity | File(s) | Fix |
|----|----------|---------|-----|
| H-5 | High | `app/advisor/adapters/anthropic_adapter.py` | Initialize OpenAI client only with OPENAI_API_KEY, never cross-send |
| H-7 | High | `mobile/lib/social-auth.ts` | Fix nonce to proper hex encoding of random bytes |
| H-9 | High | `supabase/config.toml` (OWNER) | Set minimum_password_length=8, password_requirements="lower_upper_letters_digits" |
| M-12 | Medium | ~~mobile/app/_layout.tsx~~ → owned by Agent 4 | _Moved to Agent 4_ |
| M-17 | Medium | `card-web/src/app/api/revalidate/route.ts` (OWNER) | Use `crypto.timingSafeEqual` + M-18 rate limit documentation |
| M-20 | Medium | `supabase/config.toml` (OWNER) | Set enable_confirmations=true |
| M-21 | Medium | `supabase/config.toml` (OWNER) | Set secure_password_change=true |
| L-1 | Low | `app/config/__init__.py` | Add field_validator for min 32 chars on SECRET_KEY |
| L-13 | Low | ~~mobile/lib/api.ts~~ → owned by Agent 3 | _Moved to Agent 3 (scope reduced: store refresh_token only, defer full interceptor)_ |
| L-19 | Low | `supabase/config.toml` (OWNER) | Set max_frequency=60s |
| L-20 | Low | `conftest.py` | Add APP_ENV assertion guard |

## Agent 2 — Input Validation & Injection (7 fixes)

| ID | Severity | File(s) | Fix |
|----|----------|---------|-----|
| C-3 | Critical | `app/entitlement/trial_grantor.py` + migration 0020 | Remove non-atomic fallback, add UNIQUE constraint on (user_id, type='trial_grant') |
| H-3 | High | `app/advisor/content_filter.py` | Expand denylist, add unicode normalization, output scanning |
| H-6 | High | `mobile/lib/entitlement.ts`, `mobile/app.json` | Replace nxme:// URLs with HTTPS universal links for Stripe redirects. Add TODO comment for AASA/assetlinks.json infrastructure prerequisite. StripeProvider urlScheme change in _layout.tsx owned by Agent 4. |
| M-14 | Medium | ~~mobile/app/card/[username].tsx~~ → owned by Agent 3 | _Moved to Agent 3_ |
| M-15 | Medium | `mobile/app/(auth)/signup.tsx` | Validate card param against USERNAME_PATTERN |
| M-16 | Medium | `card-web/src/app/[username]/page.tsx` | Escape `</script>` in JSON-LD with `\u003c` replacement |
| M-23 | Medium | Migration 0021 | ALTER all SECURITY DEFINER functions to add SET search_path = public |
| L-8 | Low | `app/api/users.py` | Restrict avatar regex to explicit extensions (.jpg, .png, .webp) |

## Agent 3 — Network & SSRF (14 fixes)

| ID | Severity | File(s) | Fix |
|----|----------|---------|-----|
| H-1 | High | `app/generation/worker.py` (OWNER) | Validate image URLs against domain allowlist, reject private IPs. Also L-4: initialize job_data={} before try block. |
| H-2 | High | `app/api/social.py` (OWNER) | Use shared `_get_client_ip()` for rate limiting. Also L-3: use full SHA-256 hex digest. |
| M-3 | Medium | `app/api/posts.py` | Add Redis rate limit on comments (10/min per user) |
| M-4 | Medium | `app/api/posts.py` | Add Redis rate limit on reports (5/hr per user) + dedup |
| M-7 | Medium | `app/api/generation.py` | Replace exact queue depth with rough estimate |
| M-8 | Medium | `app/image_pipeline/pipeline.py` | Return generic error, log details server-side |
| M-13 | Medium | `mobile/lib/api.ts` (OWNER) | Add HTTPS enforcement guard for production. Also L-11: omit URL from ApiError in production. Also L-13 (reduced scope): store refresh_token in SecureStore alongside JWT. |
| M-14 | Medium | `mobile/app/card/[username].tsx` (OWNER) | Add encodeURIComponent + username validation. Also L-9: use apiFetch instead of raw fetch. |
| M-19 | Medium | `card-web/src/app/[username]/opengraph-image.tsx` | Validate image URLs against allowed hosts |

## Agent 4 — Information Disclosure & Logging (14 fixes)

| ID | Severity | File(s) | Fix |
|----|----------|---------|-----|
| H-4 | High | `app/api/health.py` | Return "error"/"unavailable" only, log details server-side |
| H-8 | High | `app/main.py` (OWNER) | Reject known demo JWT secret values when APP_ENV != "development". Also C-2: add ContentSizeLimitMiddleware. Also M-2: disable docs for all envs except "development". Also M-25: add CORS decision comment. |
| M-1 | Medium | `app/api/auth.py` | Remove email from log messages, log user_id only |
| M-5 | Medium | `app/api/webhooks.py` | Return 500 for transient errors, record idempotency only after success |
| M-6 | Medium | `app/advisor/service.py` | Add proper exception handling on background task |
| M-10 | Medium | `mobile/app/_layout.tsx` (OWNER) | Log generic init message only. Also M-11: log rejection without URL. Also M-12: decode JWT exp claim, clear if expired. Also H-6 StripeProvider: change urlScheme to HTTPS universal link. |
| L-5 | Low | `app/migrations/run.py` | Add comment ensuring DSN never logged |
| L-6 | Low | `app/api/middleware/security_headers.py` | Add Permissions-Policy header |
| L-14 | Low | `card-web/src/app/error.tsx` + `[username]/error.tsx` | Guard console.error with NODE_ENV check |
| L-15 | Low | `card-web/src/lib/api.ts` | Generic error message for user-facing throw |
| L-16 | Low | `card-web/src/config/constants.ts` | Log warning when API_URL falls back |
| Info | Info | card-web general | Add CSRF documentation comment |

## Agent 5 — Infra & Dependencies (10 fixes)

| ID | Severity | File(s) | Fix |
|----|----------|---------|-----|
| H-10 | High | `docker-compose.yml` (OWNER) | Add --requirepass, bind 127.0.0.1, update REDIS_URL. Also L-22: remove version field. |
| M-22 | Medium | `Dockerfile` (OWNER) | Add non-root user to dev stage. Also L-18: remove gcc after pip install. |
| M-24 | Medium | `card-web/package.json` | Verify Next.js 14.2.29 includes patches for CVE-2024-51479, CVE-2025-29927, CVE-2024-46982. Document findings in comment or upgrade if needed. |
| L-2 | Low | `app/services/disposable_email.py` | Fail startup in non-dev if package missing |
| L-7 | Low | Migration 0022 | Add composite index on glow_up_jobs(status, updated_at) |
| L-12 | Low | `mobile/lib/notifications.ts` | Pass explicit projectId |
| L-17 | Low | `card-web/next.config.mjs` | Pin to specific Supabase project hostname |
| L-21 | Low | `requirements.txt` | Pin onnxruntime>=1.19 |
| Info | Info | `card-web/package.json` | Add npm audit script |

## Verification Phase

After all 5 agents complete:

1. **Python:** `ruff check --fix app/` + `ruff format app/`
2. **Python tests:** `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest`
3. **Mobile TS:** `cd mobile && npx tsc --noEmit`
4. **Card-web:** `cd card-web && npx tsc --noEmit && npm run build`
5. **Card-web lint:** `cd card-web && npx eslint src/`
6. Fix any warnings/errors from above steps
7. Single commit with all fixes
8. PR to dev
9. Merge

## Constraints

- No new features or architectural changes
- No dependency major version upgrades (except Next.js if needed for CVE)
- No changes to test files beyond conftest guard
- No refactoring beyond what's needed for fixes
- All fixes must be surgical — minimal diff per finding
- L-13 (token refresh): reduced to storing refresh_token only; full 401 interceptor deferred to follow-up
- H-6 (universal links): replace URLs in code + add TODO for AASA/assetlinks.json infrastructure
