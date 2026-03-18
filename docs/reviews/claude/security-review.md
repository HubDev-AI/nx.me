# Security Review

- Date: 2026-03-17
- Scope: app/**/*.py (all API handlers, middleware, services, adapters)
- Branch: feature/story-2-2-auth-social-login
- Method: static analysis — full read of all route handlers, middleware, payment, and auth code
- Auditor note: a prior partial audit (`2026-03-17-security-audit.md`) exists with five findings. This review supersedes it with verified-against-live-code findings only. Three of the five prior findings were already fixed in the current tree; that is noted inline.

---

## Executive Summary

The application demonstrates a strong security posture overall. All secrets flow through `pydantic-settings` with no hardcoded values found. JWT validation enforces issuer, audience, and required claims. Rate limiting uses `request.client.host` (TCP peer), not user-supplied headers. Payment flows route entirely through Stripe-hosted checkout with no raw card data touching the app. Credit mutations are fully atomic via PostgreSQL RPCs.

Four findings require remediation before a production release: one high-severity unvalidated trust path in the webhook user_id, one high-severity guest token system flaw, one medium-severity logout failure mode, and one medium-severity missing HTTP security header layer.

---

## Findings

### Critical

_None._

---

### High

#### H-1: Webhook user_id sourced from Stripe metadata without format or existence validation

**File:** `app/api/webhooks.py` lines 106–138 (`_handle_checkout_completed`) and lines 152–180 (`_handle_subscription_created`)

**Detail:** `user_id` is read directly from the Stripe event `metadata` dict and passed without validation into `credit_ledger` inserts and `users` table updates:

```python
user_id = metadata.get("user_id")          # line 106
...
supabase.table("credit_ledger").insert({   # line 126
    "user_id": user_id,
    ...
```

And similarly at line 178:

```python
supabase.table("users").update({
    "tier_id": TIER_ID_PREMIUM,
}).eq("id", user_id).execute()
```

Stripe webhook signatures are verified correctly (the `construct_webhook_event` call validates HMAC-SHA256), so the event content is authentic. However:

1. Metadata values are set by your own server at checkout session creation time, so under normal operation this cannot be attacker-controlled.
2. If the webhook secret is ever compromised, or if a Stripe account takeover occurs, an attacker could craft events with arbitrary `user_id` values (any UUID) and elevate any account to Premium or inject arbitrary credits.
3. There is no `UUID()` parse validation — a malformed `user_id` string will propagate to DB queries where it may cause unexpected errors rather than a clean early rejection.

**Risk:** Under normal operation the impact is low because the metadata is server-set. Under a webhook secret compromise, impact is critical (arbitrary account elevation). Defence-in-depth requires validating the user_id against the `users` table before applying financial mutations.

**Recommendation:**
```python
# After extracting user_id from metadata, validate it exists and is not deleted:
if not user_id:
    logger.warning("checkout.session.completed missing user_id in metadata")
    return

try:
    UUID(user_id)   # format validation
except ValueError:
    logger.error("Invalid user_id UUID in webhook metadata: %s", user_id)
    return

user_check = supabase.table("users").select("id").eq("id", user_id).is_("deleted_at", "null").maybe_single().execute()
if not user_check.data:
    logger.error("Webhook user_id %s does not exist or is deleted", user_id)
    return
```

Apply the same guard to `_handle_subscription_created` and `_handle_subscription_deleted`.

---

#### H-2: Guest reaction tokens are client-generated with no server-side registry

**File:** `app/api/social.py` lines 239–247

**Detail:** The `react_to_post` endpoint accepts an `X-Guest-Token` header and validates only its format (64-char hex). The token itself is generated entirely on the client (`mobile/lib/` — outside this audit scope but noted in the prior review as using `Date.now()` + `Math.random()`). The server performs no existence check against a stored token registry.

This means:
- Any client can fabricate a 64-char hex string and react as a unique "guest".
- An attacker can write a simple loop generating arbitrary guest tokens and spam reactions on any post.
- The IP-based rate limit (`_REACTION_RATE_LIMIT = 10 per 5 minutes`) is the only practical throttle, and it is trivially bypassed by distributing requests across IPs.
- UNIQUE constraint deduplication only catches the exact same token reacting twice, not distinct forged tokens.

**Note:** The per-IP rate limiting and the format validation are both correct implementations — they just cannot compensate for the absence of a token registry.

**Recommendation (two-tier approach):**

Option A (lower effort): generate CSPRNG tokens server-side via a `POST /guest-sessions` endpoint, store a hash of the token in a `guest_sessions` table with a TTL, and validate the hash on each reaction before applying it. This closes the fabrication surface entirely.

Option B (pragmatic): keep client-generated tokens but add:
1. On first use, record the token hash in Redis with a TTL (e.g., 30 days) and reject tokens not seen in that registry.
2. Require the mobile client to call a server endpoint to "register" the guest token before first use.

Either option significantly raises the cost of abuse over the current state.

---

### Medium

#### M-1: Logout does not return an error when server-side token revocation fails

**File:** `app/api/auth.py` lines 517–526

**Detail:** When `supabase.auth.admin.sign_out(token)` throws, the handler returns `HTTP 502` to the caller. This is better than silently returning 204 (which was the prior code). However, the comment at line 526 notes "The token will expire naturally" — this is unreachable code after the `raise` on line 525, so the actual behaviour is to return 502 on any revocation failure.

Re-reading the code more carefully, the current implementation **does** raise an HTTPException 502 on failure — this is correct. The prior audit finding (finding 4) claimed it returned 204; that was already fixed. This medium finding is a documentation/UX concern: the 502 response body format at line 524 embeds the error code inside a `detail.error` object, which diverges from the standard FastAPI `detail` string format used by other endpoints. The inconsistency may confuse client error handling.

**Recommendation:** Normalize the 502 detail body to match the rest of the API or update the client error handler to handle both shapes.

---

#### M-2: No HTTP security headers middleware

**File:** `app/main.py` — no security header middleware found across entire `app/` tree

**Detail:** The FastAPI application mounts no middleware that sets standard security response headers:

- `Strict-Transport-Security` (HSTS)
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Content-Security-Policy` (relevant even for an API, to mitigate browser-based misuse of the OpenAPI docs endpoint)

The OpenAPI docs are served on `/docs` and `/redoc` in non-production environments (correctly disabled in production per `main.py:82-83`). But development environments will serve them without any security headers, which is a developer hygiene issue.

For a mobile-backend-only API, the risk is lower than for a browser-facing app, but HSTS and `X-Content-Type-Options` are universally applicable and take one dependency to add.

**Recommendation:**

```python
# In main.py, after creating the app:
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware  # only in prod
app.add_middleware(SecurityHeadersMiddleware)  # custom or use secure[starlette]
```

Or use `secure` package:
```
pip install secure
```
```python
import secure
secure_headers = secure.Secure()

@app.middleware("http")
async def set_secure_headers(request, call_next):
    response = await call_next(request)
    secure_headers.framework.fastapi(response)
    return response
```

---

#### M-3: `avatar_storage_key` accepted from client without path validation in `PATCH /users/{username}`

**File:** `app/api/users.py` lines 326–329

**Detail:** The `UpdateProfileRequest` accepts an `avatar_storage_key: Optional[str]` field and writes it directly to `users.avatar_storage_key` without any format or path validation:

```python
if body.avatar_storage_key is not None:
    updates["avatar_storage_key"] = body.avatar_storage_key
```

A malicious authenticated user can set their `avatar_storage_key` to an arbitrary string — including path traversal sequences (`../../sensitive-file`) or storage keys belonging to other users. When `build_avatar_url` generates a signed URL from this key, it will faithfully produce a signed URL for whatever key was stored, potentially exposing private storage objects of other users.

**Recommendation:**

1. Validate that the `avatar_storage_key` matches the expected format for user-owned avatars (e.g., must start with `avatars/{user_id}/`).
2. Alternatively, move avatar upload to a dedicated `POST /users/{username}/avatar` endpoint that accepts the file bytes, stores it in the correct path, and records the key server-side — never accepting a raw storage key from the client.

---

### Low

#### L-1: `display_name` field in registration has no XSS-relevant validation beyond length

**File:** `app/api/auth.py` line 57

**Detail:** `display_name: str = Field(min_length=1, max_length=50)` accepts arbitrary Unicode including HTML characters. For a mobile API this is currently harmless since display names are rendered in a native app context. However, the `/public/cards/{username}` endpoint returns `display_name` in JSON that may be consumed by web clients or server-side-rendered SEO pages in the future. If display names are ever interpolated into HTML without escaping, this becomes an XSS vector.

**Recommendation:** Consider stripping or rejecting display names containing `<`, `>`, and `"` characters now, before public web rendering is added, as it is simpler to enforce early than retroactively clean stored data.

---

#### L-2: Rate limiter key namespace for reactions does not include port, enabling IPv6 collision edge cases

**File:** `app/api/social.py` line 256

**Detail:**

```python
client_ip = request.client.host if request.client else "unknown"
rate_key = f"reaction_rate:{client_ip}"
```

If `request.client` is `None` (e.g., WebSocket upgrade or reverse-proxy edge case), all reactions from those clients share the key `reaction_rate:unknown`, causing any single such client to lock out all others in the same state. This is a low-probability edge case on a well-configured deployment but should be handled.

**Recommendation:**

```python
client_ip = request.client.host if request.client else ""
if not client_ip:
    raise HTTPException(status_code=400, detail="Cannot determine client IP")
```

This is already the pattern used in `auth.py:96-101` — apply it consistently here.

---

#### L-3: `check_login_rate_limit` shares the same window config as registration — no independent tuning

**File:** `app/services/rate_limiter.py` lines 60–76

**Detail:** `check_login_rate_limit` reuses `REGISTRATION_IP_LIMIT` (4) and `REGISTRATION_IP_WINDOW_SECONDS` (3600). This means login rate limiting cannot be tuned independently from registration rate limiting without affecting both. In practice, login may need a tighter window (e.g., 10 attempts per 15 minutes to resist credential-stuffing) than registration.

**Recommendation:** Add `LOGIN_IP_LIMIT` and `LOGIN_IP_WINDOW_SECONDS` settings with appropriate defaults, and use them in `check_login_rate_limit`.

---

#### L-4: Stripe webhook signature error returns HTTP 401 instead of 400

**File:** `app/api/webhooks.py` lines 43–49

**Detail:** An invalid signature raises `HTTP 401 Unauthorized`. RFC 7235 defines 401 as indicating that authentication is required and a `WWW-Authenticate` challenge is expected. For webhook endpoints that do not use bearer-token auth, `HTTP 400 Bad Request` is more semantically accurate for a malformed/invalid signature. This is a minor semantic issue but can confuse monitoring dashboards that alert on 401s.

---

## Findings Confirmed Fixed (from prior audit)

The following findings from `2026-03-17-security-audit.md` were verified as already fixed in the current code:

| Prior Finding | Status | Evidence |
|---------------|--------|---------|
| Finding 1: `X-Forwarded-For` trusted for IP rate limiting | Fixed | `auth.py:96` uses `request.client.host` with comment explaining the rationale |
| Finding 3: Stripe return URLs user-controlled | Fixed | `entitlement.py:172-176` sources `success_url`/`cancel_url` from `settings.STRIPE_SUCCESS_URL` / `settings.STRIPE_CANCEL_URL`; hardcoded deep-link scheme (`nxme://`) in `config.py:85-86` |
| Finding 5: JWT middleware not validating `iss`/`aud` | Fixed | `middleware/auth.py:66` validates `audience="authenticated"` and `issuer=f"{settings.SUPABASE_URL}/auth/v1"` |

Finding 4 (logout fails open) was partially fixed — the handler now raises 502 on revocation failure. The residual issue is noted as M-1 above (response shape inconsistency only).

---

## OWASP Top 10 Coverage

| # | Category | Status | Notes |
|---|----------|--------|-------|
| A01 | Broken Access Control | Pass | All routes check `user_id` from JWT `sub` claim. IDOR pattern consistently uses `user_id != claims["sub"]` then 404 (not 403, preventing enumeration). Owner-only endpoints enforced on analyses, jobs, history, profile update. |
| A02 | Cryptographic Failures | Pass | Passwords handled by Supabase Auth (bcrypt). JWT uses HS256 with `SUPABASE_JWT_SECRET` env var. No plaintext secrets found in code. Signed URLs for private images with configurable expiry. |
| A03 | Injection | Pass | All DB queries use Supabase PostgREST SDK with parameterized query construction. No raw SQL string concatenation found. Credit mutations exclusively through stored-procedure RPCs. Cursor values parsed as typed floats/ints before use in SQL function params. |
| A04 | Insecure Design | Partial | H-2 (guest token system design) is a design-level weakness. Credit ledger atomic RPCs are well-designed. Rate limiting architecture is sound. |
| A05 | Security Misconfiguration | Partial | M-2 (no security headers). OpenAPI docs disabled in production. Mock adapters blocked in non-development environments (`main.py:31-39`). `ADMIN_API_KEY` required but no routes using it were found in the audited files — if there are admin routes, verify they check this key. |
| A06 | Vulnerable and Outdated Components | Not audited | Dependency audit (`pip audit`) not performed in this static review. Recommend running before release. |
| A07 | Identification and Authentication Failures | Partial | JWT validation is correct. Social login delegates to Supabase GoTrue for `iss`/`aud`/`exp`/`nonce` validation. Login rate limit shares tuning with registration (L-3). Guest token system is weak (H-2). |
| A08 | Software and Data Integrity Failures | Pass | Stripe webhook HMAC-SHA256 verified before any processing. Idempotency check uses DB UNIQUE constraint. ARQ jobs enqueued after DB write, not before. |
| A09 | Security Logging and Monitoring Failures | Pass | Security-relevant events logged at appropriate levels: registration, login, account deletion, webhook events, rate limit hits. Sensitive data (passwords, tokens) not logged — only user_id and provider. |
| A10 | Server-Side Request Forgery (SSRF) | Pass | No user-supplied URLs are fetched server-side. Stripe URLs come from config. Image uploads go through the pipeline which validates content type and dimensions, not via URL fetch. |

---

## Payment Security Checklist

| Control | Status | Notes |
|---------|--------|-------|
| No raw card data handled | Pass | All card collection via Stripe hosted checkout / mobile SDK |
| Webhook signature verified | Pass | `StripePaymentAdapter.construct_webhook_event` uses `stripe.Webhook.construct_event` |
| Webhook idempotency | Pass | `processed_webhook_events` table with UNIQUE constraint on `(provider, event_id)` |
| Credit mutations atomic | Pass | All via `credit_reserve` / `credit_release` / `credit_commit` RPCs in DB transactions |
| user_id validated in webhook | Partial | Format not validated; DB existence not checked — see H-1 |
| Checkout return URLs server-controlled | Pass | Hardcoded deep-link scheme in config |
| Subscription state via webhook only | Pass | Tier upgrades/downgrades happen only on verified Stripe events |
| Balance check before reserve | Pass | `EntitlementService.check()` runs before `CreditLedger.reserve()` in generation flow |

---

## Secrets Detection

No hardcoded secrets found. All sensitive configuration fields (`SECRET_KEY`, `ADMIN_API_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`, `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET`, `FAL_API_KEY`, `ANTHROPIC_API_KEY`) are declared as required `str` fields in `pydantic-settings` with no default values, causing immediate startup failure if any are absent.

The `ADMIN_API_KEY` is declared in `config.py` but no routes using it were found in this audit. Verify that admin endpoints (if they exist) actually validate this key before use.

---

## Summary Table

| ID | Severity | Area | Title | Effort |
|----|----------|------|-------|--------|
| H-1 | High | Payment/Webhook | Webhook user_id not validated against DB | Low |
| H-2 | High | Social/Auth | Guest tokens client-generated with no registry | Medium |
| M-1 | Medium | Auth | Logout 502 response shape inconsistency | Low |
| M-2 | Medium | Infrastructure | No HTTP security headers middleware | Low |
| M-3 | Medium | Users | avatar_storage_key accepted from client without path validation | Low |
| L-1 | Low | Auth | display_name allows HTML characters | Low |
| L-2 | Low | Social | Reaction rate key uses "unknown" fallback | Low |
| L-3 | Low | Auth | Login rate limit shares registration tuning constants | Low |
| L-4 | Low | Webhooks | Invalid webhook signature returns HTTP 401 instead of 400 | Trivial |

---

## Recommended Remediation Order

1. **H-1** — Add UUID parse + DB existence check for `user_id` in all three webhook handlers before any ledger/tier mutation. One day of work.
2. **M-3** — Add path prefix validation to `avatar_storage_key` in `PATCH /users/{username}`. Two hours.
3. **H-2** — Introduce server-side guest token registration endpoint and existence check in reaction handler. This is the most involved fix (new table/endpoint) but closes a meaningful abuse surface before launch.
4. **M-2** — Add `secure` package and one middleware function to `main.py`. One hour.
5. **L-2**, **L-3**, **M-1** — Minor hardening, can be batched in a single PR.
