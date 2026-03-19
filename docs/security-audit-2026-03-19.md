# NXME Security Audit Report

**Date:** 2026-03-19
**Branch:** `fix/app-audit-2026-03-19`
**Methodology:** STRIDE Threat Model + OWASP Top 10 + OWASP Mobile Top 10
**Scope:** Full codebase — Python backend (`app/`), React Native mobile (`mobile/`), Next.js card-web (`card-web/`), infrastructure (Docker, migrations, config)

---

## Executive Summary

| Severity | Backend | Mobile | Card-Web | Infra | **Total** |
|----------|---------|--------|----------|-------|-----------|
| Critical | 3 | 0 | 0 | 0 | **3** |
| High | 5 | 2 | 0 | 3 | **10** |
| Medium | 8 | 7 | 4 | 6 | **25** |
| Low | 8 | 5 | 4 | 5 | **22** |
| Info | 7 | 4 | 4 | 12 | **27** |
| **Total** | **31** | **18** | **12** | **26** | **87** |

**Positive findings:** 20+ well-implemented security controls including JWT validation, RLS on all tables, fail-closed NSFW screening, webhook signature verification, mock adapter blocking, security headers, and ephemeral face embeddings.

---

## Critical Findings (3)

### C-1. Missing Module: `app/constants/tiers` Does Not Exist
- **File:** `app/api/webhooks.py:19`, `app/api/entitlement.py`, `app/api/generation.py`
- **Category:** OWASP-A05 / STRIDE-Tampering
- **Description:** Multiple critical routes import from `app.constants.tiers` (TIER_ID_CREDIT_HOLDER, TIER_ID_PREMIUM, etc.). This module does not exist. The application will crash with ImportError on any request to these routes.
- **Impact:** Stripe webhook processing, credit purchases, subscriptions, and generation endpoints are all broken. Webhook failures cause missed payments and lost credits.
- **Recommendation:** Create `app/constants/tiers.py` with the correct tier ID constants and slug-to-name mapping. Deployment blocker.

### C-2. Unbounded File Upload Read Into Memory
- **File:** `app/api/analyses.py:76`
- **Category:** OWASP-A04 / STRIDE-DoS
- **Description:** `await file.read()` reads the entire upload into memory before any size validation. FastAPI has no default request body size limit.
- **Impact:** A single multi-GB request can OOM-kill the API server.
- **Recommendation:** Add `ContentSizeLimitMiddleware` set to `MAX_UPLOAD_SIZE_MB`, or read in chunks and abort early.

### C-3. TOCTOU Race in Trial Grant Idempotency
- **File:** `app/entitlement/trial_grantor.py:44-84`
- **Category:** OWASP-A04 / STRIDE-Tampering
- **Description:** Idempotency check reads credit_ledger, then separately inserts. Concurrent `POST /auth/verify-email` requests can double-grant. The fallback path performs two non-atomic writes.
- **Impact:** Users can receive unlimited trial credits via concurrent requests.
- **Recommendation:** Always use the `grant_trial` RPC (atomic). Add a UNIQUE constraint on `(user_id, type='trial_grant')` in credit_ledger. Remove the non-atomic fallback.

---

## High Findings (10)

### H-1. SSRF via Provider Image URL
- **File:** `app/generation/worker.py:188-189`
- **Category:** OWASP-A10 / STRIDE-Tampering
- **Description:** Worker downloads images from URLs returned by fal.ai without URL validation. A compromised provider response could point to internal metadata endpoints (AWS IMDS `169.254.169.254`).
- **Impact:** Internal service enumeration, credential theft from cloud metadata.
- **Recommendation:** Validate URLs against an allowlist (`*.fal.ai`, `*.fal.run`). Reject private IP ranges.

### H-2. Reaction Rate Limit Bypassed by Missing Proxy Handling
- **File:** `app/api/social.py:247`
- **Category:** OWASP-A07 / STRIDE-DoS
- **Description:** Uses `request.client.host` directly instead of `_get_client_ip()` helper that respects `TRUST_PROXY_HEADERS`. Behind a reverse proxy, all requests share the proxy IP.
- **Impact:** Rate limiting non-functional in production. Unlimited reaction spam.
- **Recommendation:** Use the shared `_get_client_ip()` helper for all IP-based rate limiting.

### H-3. Incomplete Prompt Injection Defense
- **File:** `app/advisor/content_filter.py:36-45`
- **Category:** OWASP-A03 / STRIDE-Tampering
- **Description:** Short regex denylist trivially bypassed via unicode homoglyphs, zero-width characters, base64 encoding, multilingual equivalents.
- **Impact:** Attacker can extract SOUL.md contents, user data, or cause harmful advisor output.
- **Recommendation:** Defense-in-depth: expand denylist, use LLM safety features, output scanning, dedicated prompt injection detection model.

### H-4. Readiness Endpoint Leaks Internal Error Details
- **File:** `app/api/health.py:35-42`
- **Category:** OWASP-A05 / STRIDE-Information Disclosure
- **Description:** Unauthenticated `/readiness` returns full exception messages from Redis/Supabase failures including connection strings and hostnames.
- **Impact:** Infrastructure fingerprinting and topology discovery.
- **Recommendation:** Return only "error"/"unavailable". Log details server-side. Consider auth-gating `/readiness`.

### H-5. Anthropic API Key Leaked to OpenAI
- **File:** `app/advisor/adapters/anthropic_adapter.py:30`
- **Category:** OWASP-A02 / STRIDE-Spoofing
- **Description:** OpenAI client initialized with `ANTHROPIC_API_KEY` as fallback. If `OPENAI_API_KEY` override fails (bare except), the Anthropic key is sent to OpenAI's servers.
- **Impact:** Secret leaked to third-party. If OpenAI logs failed auth, the key is persisted.
- **Recommendation:** Initialize OpenAI client only with `OPENAI_API_KEY`. Never cross-send provider keys.

### H-6. Custom URI Scheme for Stripe Payment Redirects (Mobile)
- **File:** `mobile/lib/entitlement.ts:67-68`
- **Category:** OWASP-Mobile-M1 / STRIDE-Spoofing
- **Description:** `nxme://payment/success` and `nxme://payment/cancel` used as Stripe redirect URLs. Custom URI schemes are not cryptographically bound — any app can register the same scheme.
- **Impact:** Malicious app intercepts Stripe payment callback, steals session tokens or tricks user.
- **Recommendation:** Replace with HTTPS universal links or use Stripe's in-app payment sheet.

### H-7. Apple Sign-In Nonce Generation Issue (Mobile)
- **File:** `mobile/lib/social-auth.ts:104-107`
- **Category:** OWASP-Mobile-M5 / STRIDE-Tampering
- **Description:** Nonce generated as `SHA256(Uint8Array.toString())` — the `.toString()` on bytes produces comma-separated decimals, not a proper hex string. Mismatched with Supabase expectations.
- **Impact:** Potential auth failure or reduced replay protection.
- **Recommendation:** Use proper hex encoding: `Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('')`.

### H-8. Well-Known JWT Secret Without Startup Guard (Infra)
- **File:** `scripts/local-env.sh:16-23`
- **Category:** OWASP-A07
- **Description:** Well-known Supabase demo JWT keys written to `.env`. No runtime guard rejects these in staging/production.
- **Impact:** If deployed without replacing demo keys, any attacker can forge JWTs with full service-role access.
- **Recommendation:** Add startup check in `app/main.py` that rejects known demo values when `APP_ENV != "development"`.

### H-9. Weak Supabase Password Policy (Infra)
- **File:** `supabase/config.toml:175-178`
- **Category:** OWASP-A07
- **Description:** `minimum_password_length = 6`, `password_requirements = ""`. Supabase auth layer accepts 6-char passwords, bypassing the app's 8-char Pydantic validation if Supabase API is called directly.
- **Impact:** Weak passwords, easier brute-force.
- **Recommendation:** Set `minimum_password_length = 8` and `password_requirements = "lower_upper_letters_digits"`.

### H-10. Redis Exposed Without Auth (Infra)
- **File:** `docker-compose.yml:8`
- **Category:** OWASP-A05
- **Description:** Redis bound to `0.0.0.0:6379` with no `requirepass` or ACL.
- **Impact:** Any process on the host can read/write rate-limiter keys, cached tiers, and the ARQ job queue.
- **Recommendation:** Add `--requirepass ${REDIS_PASSWORD}`, bind to `127.0.0.1`, or remove host port binding.

---

## Medium Findings (25)

### Backend (8)

| ID | File | Title | Category |
|----|------|-------|----------|
| M-1 | `app/api/auth.py:234` | PII (email) logged in plain text | OWASP-A09 |
| M-2 | `app/main.py:113-115` | Swagger/Redoc enabled in non-production envs (staging, QA) | OWASP-A05 |
| M-3 | `app/api/posts.py:220-275` | Comments endpoint missing rate limit | OWASP-A04 |
| M-4 | `app/api/posts.py:344-374` | Reports endpoint missing rate limit | OWASP-A04 |
| M-5 | `app/api/webhooks.py:80-84` | Transient webhook errors return 200, preventing Stripe retry | OWASP-A09 |
| M-6 | `app/advisor/service.py:153-169` | Fire-and-forget asyncio task silently swallows errors | OWASP-A09 |
| M-7 | `app/api/generation.py:370` | Redis key enumeration reveals queue architecture | OWASP-A01 |
| M-8 | `app/image_pipeline/pipeline.py:111` | Validation error leaks internal library details | OWASP-A05 |

### Mobile (7)

| ID | File | Title | Category |
|----|------|-------|----------|
| M-9 | `mobile/app/_layout.tsx:76` | StripeProvider urlScheme set to custom URI "nxme" | OWASP-Mobile-M1 |
| M-10 | `mobile/app/_layout.tsx:41` | Init error logged with sensitive context | OWASP-Mobile-M10 |
| M-11 | `mobile/app/_layout.tsx:54` | Rejected deep link URL logged to console | OWASP-Mobile-M10 |
| M-12 | `mobile/app/_layout.tsx:35-39` | JWT existence check without expiration validation | OWASP-Mobile-M4 |
| M-13 | `mobile/app/(auth)/login.tsx:94-97` | No certificate pinning; password sent over network | OWASP-Mobile-M3 |
| M-14 | `mobile/app/card/[username].tsx:62` | Username interpolated into API URL without sanitization | OWASP-Mobile-M7 |
| M-15 | `mobile/app/(auth)/signup.tsx:371` | Deep link `card` parameter rendered without validation | OWASP-Mobile-M7 |

### Card-Web (4)

| ID | File | Title | Category |
|----|------|-------|----------|
| M-16 | `card-web/src/app/[username]/page.tsx:89` | JSON-LD XSS via unsanitized `</script>` in user data | OWASP-A03 |
| M-17 | `card-web/src/app/api/revalidate/route.ts:25` | Timing-attack-vulnerable secret comparison | OWASP-A07 |
| M-18 | `card-web/src/app/api/revalidate/route.ts` | No rate limiting on revalidation endpoint | OWASP-A01 |
| M-19 | `card-web/src/app/[username]/opengraph-image.tsx:125` | SSRF via image URLs in OG image generation | OWASP-A10 |

### Infrastructure (6)

| ID | File | Title | Category |
|----|------|-------|----------|
| M-20 | `supabase/config.toml:209` | Email confirmation disabled in Supabase auth | OWASP-A07 |
| M-21 | `supabase/config.toml:211` | `secure_password_change = false` | OWASP-A07 |
| M-22 | `Dockerfile:19-28` | Dev stage runs as root | OWASP-A05 |
| M-23 | `app/migrations/0015_atomic_writes.sql` | SECURITY DEFINER functions without `SET search_path` | OWASP-A03 |
| M-24 | `card-web/package.json:13` | Next.js 14.2.29 may have known CVEs | OWASP-A06 |
| M-25 | Backend | No CORS middleware (acceptable if mobile-only, needs documentation) | OWASP-A05 |

---

## Low Findings (22)

<details>
<summary>Click to expand all 22 low findings</summary>

### Backend (8)
| ID | File | Title |
|----|------|-------|
| L-1 | `app/config/__init__.py:9` | SECRET_KEY has no minimum length enforcement |
| L-2 | `app/services/disposable_email.py:25` | Fallback blocklist only 9 domains |
| L-3 | `app/api/social.py:174` | Guest token hash truncated to 128 bits (unnecessary) |
| L-4 | `app/generation/worker.py:438` | Fragile `locals()` check in exception handler |
| L-5 | `app/migrations/run.py:36` | DB credentials in process environment |
| L-6 | `app/api/middleware/security_headers.py` | Missing Permissions-Policy header |
| L-7 | `app/worker_settings.py:74` | Watchdog query every minute may need index |
| L-8 | `app/api/users.py:304` | Avatar regex allows dots (low risk, but could restrict to extensions) |

### Mobile (5)
| ID | File | Title |
|----|------|-------|
| L-9 | `mobile/app/card/[username].tsx:62` | Uses raw fetch instead of apiFetch wrapper |
| L-10 | `mobile/app.json:9` | Custom URI scheme registered at OS level |
| L-11 | `mobile/lib/api.ts:49` | ApiError includes full URL in error message |
| L-12 | `mobile/lib/notifications.ts:31` | Expo push token obtained without projectId |
| L-13 | `mobile/lib/api.ts:18` | No token refresh logic; refresh_token discarded |

### Card-Web (4)
| ID | File | Title |
|----|------|-------|
| L-14 | `card-web/src/app/error.tsx:18` | Error object logged to client console |
| L-15 | `card-web/src/lib/api.ts:46` | Error message includes username |
| L-16 | `card-web/src/config/constants.ts:29` | API_URL fallback exposes NEXT_PUBLIC to server |
| L-17 | `card-web/next.config.mjs:5` | Broad wildcard image domain pattern |

### Infrastructure (5)
| ID | File | Title |
|----|------|-------|
| L-18 | `Dockerfile:11-13` | GCC left in production image |
| L-19 | `supabase/config.toml:213` | Email OTP max_frequency = 1s (too permissive) |
| L-20 | `conftest.py:9-14` | Hardcoded test secrets with no env guard |
| L-21 | `requirements.txt:44` | insightface 0.7.3 unmaintained (onnxruntime CVEs) |
| L-22 | `docker-compose.yml:1` | Deprecated compose file version field |

</details>

---

## Positive Security Controls (Already Implemented)

These are things the codebase does well:

1. **JWT validation** — HS256 pinned, audience/issuer/sub/exp checked, no algorithm confusion
2. **Row-Level Security** — Enabled + forced on all 16 user-scoped tables with `auth.uid()` policies
3. **Fail-closed NSFW screening** — Rekognition unavailable = image rejected
4. **Ephemeral face embeddings** — Computed, compared, discarded. Never persisted (ADR-1)
5. **Mock adapter blocking** — `SystemExit` if mock/local adapters used outside development
6. **Webhook signature verification** — Stripe SDK `construct_event` with signature header
7. **Security headers** — HSTS, X-Frame-Options DENY, CSP, X-Content-Type-Options on both backend and card-web
8. **Path traversal guard** — `LocalStorageAdapter` validates `path.is_relative_to(base)`
9. **Consistent auth dependency** — All authenticated routes use shared `get_current_user`
10. **Deep link guard** (mobile) — Rejects non-HTTPS deep links at runtime
11. **SecureStore** (mobile) — JWT stored in Keychain/Keystore, not AsyncStorage
12. **Input validation** — Username regex, email format, Pydantic models throughout
13. **Credit advisory lock** (migration 0019) — `pg_advisory_xact_lock` prevents double-spend
14. **No secrets in git** — `.env` gitignored, `.env.example` uses CHANGE_ME placeholders
15. **Docs disabled in production** — FastAPI docs_url/redoc_url set to None

---

## Recommended Remediation Priority

### Immediate (Before Next Deploy)
1. **C-1** — Create missing `app/constants/tiers.py` (routes are broken)
2. **C-2** — Add request body size limit middleware
3. **C-3** — Fix trial grant race condition with DB-level unique constraint
4. **H-5** — Fix Anthropic key leak to OpenAI client
5. **H-8** — Add startup guard against demo JWT secrets

### Short-Term (This Sprint)
6. **H-1** — SSRF protection on provider image URLs
7. **H-2** — Fix rate limit proxy handling in social.py
8. **H-6** — Replace custom URI scheme with universal links for Stripe
9. **H-10** — Secure Redis with authentication
10. **M-5** — Fix webhook error handling to allow Stripe retries
11. **M-16** — Fix JSON-LD XSS in card-web
12. **M-17** — Use timing-safe secret comparison in revalidation endpoint

### Medium-Term (Next Sprint)
13. **H-3** — Strengthen prompt injection defense
14. **H-4** — Sanitize readiness endpoint errors
15. **H-7** — Fix Apple Sign-In nonce generation
16. **H-9** — Tighten Supabase password policy
17. **M-1 through M-4** — PII logging, docs exposure, missing rate limits
18. **M-20/M-21** — Supabase email confirmation and secure password change
19. **M-23** — Add `SET search_path` to SECURITY DEFINER functions

### Backlog
20. All Low and Info findings
