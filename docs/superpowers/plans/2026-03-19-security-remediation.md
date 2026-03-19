# Security Audit Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 60 actionable security findings from the 2026-03-19 audit across backend, mobile, card-web, and infrastructure.

**Architecture:** Phase 0 creates a prerequisite module, then 5 parallel agents fix findings grouped by security concern (auth, validation, network, logging, infra). A final verification phase runs lint/format/type-check/build across all apps.

**Tech Stack:** Python/FastAPI, React Native/Expo, Next.js 14, PostgreSQL, Redis, Docker

**Spec:** `docs/superpowers/specs/2026-03-19-security-remediation-design.md`
**Audit:** `docs/security-audit-2026-03-19.md`

---

## Phase 0: Prerequisites (sequential — must complete before agents)

### Task 0: Create `app/constants/tiers.py` (C-1)

**Files:**
- Create: `app/constants/__init__.py`
- Create: `app/constants/tiers.py`

This module is imported by `app/api/webhooks.py:19`, `app/api/entitlement.py`, and `app/api/generation.py`. Without it, those routes crash with ImportError.

- [ ] **Step 1: Create `app/constants/__init__.py`**

```python
```

- [ ] **Step 2: Create `app/constants/tiers.py`**

The existing imports expect: `TIER_ID_CREDIT_HOLDER`, `TIER_ID_PREMIUM`, `TIER_ID_TRIAL`, `SLUG_TO_TIER_NAME`, `CREDIT_HOLDER`, `PREMIUM`, `TRIAL`.

Map these from the seed data in `app/config/tiers.py` (SEED_TIERS has slugs: "free", "credits", "premium" with fixed UUIDs).

```python
"""Tier ID constants for runtime use.

Derived from the fixed UUIDs in app/config/tiers.py seed data.
These are stable across environments because the seed migration uses
deterministic UUIDs.
"""

# Tier IDs (must match SEED_TIERS in app/config/tiers.py)
TIER_ID_TRIAL = "a0000000-0000-0000-0000-000000000001"      # slug: free
TIER_ID_CREDIT_HOLDER = "a0000000-0000-0000-0000-000000000002"  # slug: credits
TIER_ID_PREMIUM = "a0000000-0000-0000-0000-000000000003"     # slug: premium

# Slug aliases used by generation.py queue routing
TRIAL = "free"
CREDIT_HOLDER = "credits"
PREMIUM = "premium"

# Slug → display name mapping
SLUG_TO_TIER_NAME: dict[str, str] = {
    TRIAL: "Free",
    CREDIT_HOLDER: "Credits",
    PREMIUM: "Premium",
}
```

- [ ] **Step 3: Verify imports work**

Run: `python -c "from app.constants.tiers import TIER_ID_TRIAL, TIER_ID_CREDIT_HOLDER, TIER_ID_PREMIUM, SLUG_TO_TIER_NAME, TRIAL, CREDIT_HOLDER, PREMIUM; print('OK')"`

Expected: `OK`

---

## Agent 1: Auth & Secrets (9 fixes)

### Task 1: Fix Anthropic key leak to OpenAI (H-5)

**Files:**
- Modify: `app/advisor/adapters/anthropic_adapter.py:29-37`

- [ ] **Step 1: Replace the OpenAI client initialization**

Replace lines 29-37 with:

```python
        self._anthropic = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        # Embeddings use OpenAI — never send Anthropic key to OpenAI
        openai_key = settings.OPENAI_API_KEY
        if not openai_key:
            logger.warning("OPENAI_API_KEY not set — embedding calls will fail")
        self._openai = openai.AsyncOpenAI(api_key=openai_key or "not-configured")
```

### Task 2: Supabase config hardening (H-9, M-20, M-21, L-19)

**Files:**
- Modify: `supabase/config.toml:175,178,209,211,213`

- [ ] **Step 1: Apply all 4 changes to config.toml**

At line 175: `minimum_password_length = 6` → `minimum_password_length = 8`

At line 178: `password_requirements = ""` → `password_requirements = "lower_upper_letters_digits"`

At line 209: `enable_confirmations = false` → `enable_confirmations = true`

At line 211: `secure_password_change = false` → `secure_password_change = true`

At line 213: `max_frequency = "1s"` → `max_frequency = "60s"`

### Task 3: Fix Apple Sign-In nonce (H-7)

**Files:**
- Modify: `mobile/lib/social-auth.ts`

- [ ] **Step 1: Find and fix nonce generation**

Replace the nonce generation with proper hex encoding:

```typescript
const rawNonce = Array.from(Crypto.getRandomBytes(32))
  .map((b) => b.toString(16).padStart(2, "0"))
  .join("");
```

The `rawNonce` is sent to Supabase; Apple hashes it internally.

### Task 4: Timing-safe secret comparison + rate limit docs (M-17, M-18)

**Files:**
- Modify: `card-web/src/app/api/revalidate/route.ts`

- [ ] **Step 1: Add timing-safe comparison**

Replace lines 21-27 with:

```typescript
import { timingSafeEqual } from 'node:crypto';

export async function POST(request: NextRequest): Promise<NextResponse> {
  const secret = request.headers.get('x-revalidation-secret') ?? '';
  const expectedSecret = process.env.REVALIDATION_SECRET ?? '';

  // Timing-safe comparison to prevent brute-force via timing side-channel (M-17)
  const secretBuf = Buffer.from(secret);
  const expectedBuf = Buffer.from(expectedSecret);
  if (
    !expectedSecret ||
    secretBuf.length !== expectedBuf.length ||
    !timingSafeEqual(secretBuf, expectedBuf)
  ) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
```

- [ ] **Step 2: Add rate limit documentation comment**

Add after the `POST` function declaration:

```typescript
// M-18: Rate limiting for this endpoint should be configured at the
// infrastructure level (Vercel rate limiting / CDN WAF). This endpoint
// is called server-to-server by the backend, not by end users.
```

### Task 5: app/config/__init__.py — 3 consolidated fixes (L-1, H-6 URLs, H-10 Redis)

**Files:**
- Modify: `app/config/__init__.py` (OWNER: Agent 1 — consolidated from Agents 1, 2, 5)

- [ ] **Step 1: Add field_validator for SECRET_KEY (L-1)**

Add after the imports at top of file:

```python
from pydantic import field_validator
```

Add inside the `Settings` class, after `SECRET_KEY: str` (around line 10):

```python
    @field_validator("SECRET_KEY")
    @classmethod
    def _secret_key_min_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v
```

Update conftest.py to use a 32+ char key to match.

- [ ] **Step 2: Update Stripe redirect URLs (H-6)**

Change lines 92-93:

```python
    STRIPE_SUCCESS_URL: str = "https://nxme.ai/payment/success"
    STRIPE_CANCEL_URL: str = "https://nxme.ai/payment/cancel"
```

- [ ] **Step 3: Update REDIS_URL default (H-10)**

Change line 19:

```python
    REDIS_URL: str = "redis://:localdev@localhost:6379/0"
```

### Task 6: Conftest APP_ENV guard (L-20)

**Files:**
- Modify: `conftest.py`

- [ ] **Step 1: Add environment guard and fix SECRET_KEY length**

Replace the entire file with:

```python
"""Root conftest — set test env vars before any app imports.

Must be at project root so pytest loads it first, before any test module
triggers `from app.config import settings` (which calls Settings() at
import time and requires these env vars).
"""
import os

# Guard: never run tests against a real environment
os.environ.setdefault("APP_ENV", "test")
_env = os.environ.get("APP_ENV", "")
if _env not in ("development", "test"):
    raise RuntimeError(
        f"Refusing to run tests with APP_ENV={_env!r}. "
        "Set APP_ENV=test or APP_ENV=development."
    )

os.environ.setdefault("SECRET_KEY", "test-secret-key-minimum-32-characters-long!!")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-api-key-minimum-32-chars-long!!")
os.environ.setdefault("SUPABASE_URL", "https://test-project.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-minimum-32-chars-long")
```

---

## Agent 2: Input Validation & Injection (7 fixes)

### Task 7: Trial grant TOCTOU fix + migration (C-3)

**Files:**
- Modify: `app/entitlement/trial_grantor.py`
- Create: `app/migrations/0020_trial_grant_unique.sql`

- [ ] **Step 1: Remove the non-atomic fallback and tighten the idempotency**

Replace the entire `grant` method and remove `_grant_fallback`:

```python
    def grant(self, user_id: UUID) -> None:
        """Grant free trial analyses to *user_id* atomically and idempotently.

        Uses the grant_trial RPC which wraps both writes in a transaction.
        The UNIQUE constraint on (user_id, type='trial_grant') in credit_ledger
        provides a database-level guard against double-grants.

        Raises:
            RuntimeError: if the RPC is unavailable or fails.
        """
        user_id_str = str(user_id)

        try:
            self._sb.rpc(
                "grant_trial",
                {
                    "p_user_id": user_id_str,
                    "p_analyses": settings.FREE_TRIAL_ANALYSES,
                },
            ).execute()
            logger.info(
                "trial_grant applied for user %s — %d analyses granted",
                user_id_str,
                settings.FREE_TRIAL_ANALYSES,
            )
        except Exception as exc:
            # Check if this is a unique violation (already granted)
            exc_str = str(exc).lower()
            if "unique" in exc_str or "duplicate" in exc_str or "23505" in exc_str:
                logger.info("trial_grant already applied for user %s — skipping", user_id_str)
                return
            logger.error("grant_trial RPC failed for user %s: %s", user_id_str, exc)
            raise RuntimeError(
                f"Failed to grant trial for user {user_id_str}"
            ) from exc
```

- [ ] **Step 2: Create migration 0020**

```sql
-- Partial unique index to prevent double trial grants (C-3)
-- PostgreSQL does not support WHERE on ALTER TABLE ADD CONSTRAINT UNIQUE;
-- use CREATE UNIQUE INDEX instead.
CREATE UNIQUE INDEX IF NOT EXISTS uq_credit_ledger_trial_grant
  ON credit_ledger (user_id)
  WHERE type = 'trial_grant';

-- DOWN:
DROP INDEX IF EXISTS uq_credit_ledger_trial_grant;
```

### Task 8: Expand prompt injection defense (H-3)

**Files:**
- Modify: `app/advisor/content_filter.py:36-45`

- [ ] **Step 1: Add unicode normalization and expanded patterns**

Add `import unicodedata` at top. Replace `_INJECTION_PATTERNS` and update `sanitize_input`:

```python
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts?)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+a", re.IGNORECASE),
    re.compile(r"act\s+as\s+(if\s+you\s+are|a)\s+", re.IGNORECASE),
    re.compile(r"forget\s+everything", re.IGNORECASE),
    re.compile(r"disregard\s+(your\s+)?(previous|prior)\s+", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"<\s*system\s*>", re.IGNORECASE),
    re.compile(r"\[INST\]", re.IGNORECASE),
    # Extended patterns
    re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
    re.compile(r"override\s+(previous|system)\s+", re.IGNORECASE),
    re.compile(r"reveal\s+(your|the)\s+(system|prompt|instructions?)", re.IGNORECASE),
    re.compile(r"what\s+(are|is)\s+your\s+(system|initial)\s+(prompt|instructions?)", re.IGNORECASE),
    re.compile(r"repeat\s+(your|the)\s+(system|initial)\s+", re.IGNORECASE),
    re.compile(r"(print|output|show|display)\s+(your|the)\s+(system|initial)\s+", re.IGNORECASE),
    re.compile(r"bypass\s+(safety|content|filter)", re.IGNORECASE),
    re.compile(r"do\s+not\s+follow\s+(your|any)\s+", re.IGNORECASE),
    re.compile(r"base64\s*:", re.IGNORECASE),
    re.compile(r"<<\s*SYS\s*>>", re.IGNORECASE),
]
```

Update `sanitize_input` to normalize unicode first:

```python
def sanitize_input(text: str) -> str:
    if len(text) > settings.ADVISOR_MAX_MESSAGE_LENGTH:
        raise ValueError(
            f"Message too long: {len(text)} chars (max {settings.ADVISOR_MAX_MESSAGE_LENGTH})"
        )

    # Normalize unicode to NFC to defeat homoglyph attacks
    cleaned = unicodedata.normalize("NFC", text)
    # Strip zero-width characters
    cleaned = re.sub(r"[\u200b\u200c\u200d\u2060\ufeff]", "", cleaned)

    for pattern in _INJECTION_PATTERNS:
        cleaned = pattern.sub("", cleaned)

    cleaned = re.sub(r"\s{3,}", " ", cleaned).strip()

    if not cleaned:
        raise ValueError("Message is empty after sanitization")

    return cleaned
```

### Task 9: Replace custom URI scheme for Stripe (H-6)

**Files:**
- Modify: `mobile/lib/entitlement.ts`
- Modify: `mobile/app.json`
- Note: `app/config/__init__.py` Stripe URL changes are in Task 5 (Agent 1 owns that file)

- [ ] **Step 1: Update mobile entitlement.ts**

Replace any `nxme://payment/success` and `nxme://payment/cancel` with `https://nxme.ai/payment/success` and `https://nxme.ai/payment/cancel`.

- [ ] **Step 3: Add TODO for AASA infrastructure**

Add comment in `mobile/app.json` near the scheme configuration:

```json
// TODO: AASA (apple-app-site-association) and assetlinks.json must be hosted
// at https://nxme.ai/.well-known/ for universal links to work with Stripe redirects
```

### Task 10: Validate signup deep link card param (M-15)

**Files:**
- Modify: `mobile/app/(auth)/signup.tsx`

- [ ] **Step 1: Validate card parameter against USERNAME_PATTERN before rendering**

Find where the `card` parameter is used and add validation:

```typescript
import { AUTH_VALIDATION } from "@/constants/config";

// Where card is read from URL params:
const rawCard = /* existing code to get card param */;
const card = rawCard && AUTH_VALIDATION.USERNAME_PATTERN.test(rawCard) ? rawCard : undefined;
```

### Task 11: JSON-LD XSS fix (M-16)

**Files:**
- Modify: `card-web/src/app/[username]/page.tsx`

- [ ] **Step 1: Escape `</script>` sequences in JSON-LD**

Find the `dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}` and replace with:

```tsx
dangerouslySetInnerHTML={{
  __html: JSON.stringify(jsonLd).replace(/</g, '\\u003c'),
}}
```

### Task 12: SECURITY DEFINER search_path migration (M-23)

**Files:**
- Create: `app/migrations/0021_security_definer_search_path.sql`

- [ ] **Step 1: Create migration to add SET search_path to all SECURITY DEFINER functions**

Read `app/migrations/0014_credit_ledger_rpcs.sql` and `app/migrations/0015_atomic_writes.sql` to identify all SECURITY DEFINER functions, then ALTER each one.

```sql
-- Add SET search_path = public to all SECURITY DEFINER functions (M-23)
-- This prevents search_path manipulation attacks.

ALTER FUNCTION public.credit_reserve SET search_path = public;
ALTER FUNCTION public.credit_release SET search_path = public;
ALTER FUNCTION public.credit_commit SET search_path = public;
ALTER FUNCTION public.sum_credit_balance SET search_path = public;
ALTER FUNCTION public.insert_comment_atomic SET search_path = public;
ALTER FUNCTION public.persist_reaction_atomic SET search_path = public;
ALTER FUNCTION public.handle_checkout_credit_atomic SET search_path = public;

-- DOWN:
ALTER FUNCTION public.credit_reserve RESET search_path;
ALTER FUNCTION public.credit_release RESET search_path;
ALTER FUNCTION public.credit_commit RESET search_path;
ALTER FUNCTION public.sum_credit_balance RESET search_path;
ALTER FUNCTION public.insert_comment_atomic RESET search_path;
ALTER FUNCTION public.persist_reaction_atomic RESET search_path;
ALTER FUNCTION public.handle_checkout_credit_atomic RESET search_path;
```

### Task 13: Avatar regex restriction (L-8)

**Files:**
- Modify: `app/api/users.py:305`

- [ ] **Step 1: Restrict to explicit extensions**

Replace the regex at line 305:

```python
        if not re.match(rf"^avatars/{re.escape(user_id)}/[a-zA-Z0-9_\-]+\.(jpg|jpeg|png|webp)$", body.avatar_storage_key):
```

---

## Agent 3: Network & SSRF (14 fixes)

### Task 14: SSRF protection on provider image URLs + job_data init (H-1, L-4)

**Files:**
- Modify: `app/generation/worker.py:188-189,438`

- [ ] **Step 1: Add URL validation helper at module level**

Add after the imports (around line 36):

```python
import ipaddress
from urllib.parse import urlparse

_ALLOWED_IMAGE_HOSTS = frozenset(["fal.ai", "fal.run", "fal.media", "storage.googleapis.com"])

def _validate_provider_url(url: str) -> None:
    """Reject URLs pointing to private IPs or non-allowed hosts."""
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    if not any(hostname == h or hostname.endswith(f".{h}") for h in _ALLOWED_IMAGE_HOSTS):
        raise ValueError(f"Image URL host not in allowlist: {hostname}")
    # Reject private/loopback IPs (in case hostname resolves to one)
    try:
        import socket
        for info in socket.getaddrinfo(hostname, None):
            addr = ipaddress.ip_address(info[4][0])
            if addr.is_private or addr.is_loopback or addr.is_link_local:
                raise ValueError(f"Image URL resolves to private address: {addr}")
    except socket.gaierror:
        pass  # DNS resolution failure will be caught by httpx
```

- [ ] **Step 2: Add validation before each httpx.get call on provider URLs**

Before line 189 (`resp = await client.get(gen_result.image_url)`):

```python
        _validate_provider_url(gen_result.image_url)
```

Do the same for retry image downloads (around line 258).

- [ ] **Step 3: Fix job_data locals() check (L-4)**

At line 438, change:

```python
        await _fail_job(job_repo, job_id, job_data if 'job_data' in locals() else {}, FAILURE_PROVIDER, supabase=supabase)
```

This is already safe because `job_data` is assigned before the try block (line 392). But to be explicit, initialize before the try:

After `user_id_for_concurrent: str | None = None` (line 389), the job_data fetch already happens before try. No change needed — the `locals()` check is redundant but harmless. Remove it for clarity:

```python
        await _fail_job(job_repo, job_id, job_data, FAILURE_PROVIDER, supabase=supabase)
```

### Task 15: Fix rate limit proxy handling + full hash (H-2, L-3)

**Files:**
- Modify: `app/api/social.py:174,247`

- [ ] **Step 1: Use full SHA-256 digest (L-3)**

At line 174, change:
```python
    token_hash = hashlib.sha256(token.encode()).hexdigest()[:32]
```
to:
```python
    token_hash = hashlib.sha256(token.encode()).hexdigest()
```

- [ ] **Step 2: Add shared IP helper import and use it (H-2)**

At line 247, replace:
```python
    client_ip = request.client.host
```
with:
```python
    client_ip = _get_client_ip(request)
```

Add the helper function (or import from auth.py). If auth.py's `_get_client_ip` is private, add a shared version:

```python
def _get_client_ip(request: Request) -> str:
    """Get client IP, respecting TRUST_PROXY_HEADERS setting."""
    if settings.TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    if not request.client:
        return "unknown"
    return request.client.host
```

### Task 16: Rate limits on comments and reports (M-3, M-4)

**Files:**
- Modify: `app/api/posts.py:220-275,344-374`

- [ ] **Step 1: Add rate limiting to create_comment**

Add imports and rate limit constants:

```python
import redis.asyncio as aioredis
from app.api.deps import get_redis
```

Add constants:

```python
_COMMENT_RATE_LIMIT = 10  # per minute
_COMMENT_RATE_WINDOW = 60
_REPORT_RATE_LIMIT = 5   # per hour
_REPORT_RATE_WINDOW = 3600
```

Make `create_comment` async and add rate limiting:

```python
async def create_comment(
    post_id: UUID,
    body: CreateCommentRequest,
    claims: UserClaims = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
    post_repo: PostRepository = Depends(get_post_repo),
    redis_client: aioredis.Redis = Depends(get_redis),
) -> Response:
    user_id = claims["sub"]

    # Rate limit: 10 comments per minute per user
    rate_key = f"comment_rate:{user_id}"
    count = await redis_client.incr(rate_key)
    if count == 1:
        await redis_client.expire(rate_key, _COMMENT_RATE_WINDOW)
    if count > _COMMENT_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many comments. Please slow down.")

    # ... rest of existing logic
```

- [ ] **Step 2: Add rate limiting + dedup to report_post**

Similarly make `report_post` async and add:

```python
async def report_post(
    post_id: UUID,
    body: ReportRequest,
    claims: UserClaims = Depends(get_current_user),
    post_repo: PostRepository = Depends(get_post_repo),
    redis_client: aioredis.Redis = Depends(get_redis),
) -> ReportResponse:
    user_id = claims["sub"]

    # Rate limit: 5 reports per hour per user
    rate_key = f"report_rate:{user_id}"
    count = await redis_client.incr(rate_key)
    if count == 1:
        await redis_client.expire(rate_key, _REPORT_RATE_WINDOW)
    if count > _REPORT_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many reports. Please slow down.")

    # ... rest of existing logic
```

### Task 17: Rough queue estimate (M-7)

**Files:**
- Modify: `app/api/generation.py:370`

- [ ] **Step 1: Replace exact queue depth with bucket**

Replace `queue_position = await redis_client.llen(...)` usage in the response with:

```python
    raw_position = await redis_client.llen(f"arq:queue:{queue_lane}")
    # Return rough estimate to avoid leaking exact queue depth (M-7)
    if raw_position <= 5:
        queue_position = raw_position  # exact for short waits
    elif raw_position <= 50:
        queue_position = (raw_position // 10) * 10  # round to nearest 10
    else:
        queue_position = (raw_position // 50) * 50  # round to nearest 50
```

### Task 18: Generic validation error (M-8)

**Files:**
- Modify: `app/image_pipeline/pipeline.py:108-112`

- [ ] **Step 1: Replace detailed error with generic message**

```python
        except (ValueError, TypeError, OSError) as exc:
            logger.warning("Image validation failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Image validation failed. Please upload a valid JPEG or PNG image.",
            ) from exc
```

### Task 19: Mobile HTTPS enforcement + API error + refresh token (M-13, L-11, L-13)

**Files:**
- Modify: `mobile/lib/api.ts`

- [ ] **Step 1: Add HTTPS guard**

Near the top of `apiFetch`, add:

```typescript
  const url = `${API_BASE_URL}${path}`;
  if (!__DEV__ && !url.startsWith("https://")) {
    throw new Error("API calls must use HTTPS in production");
  }
```

- [ ] **Step 2: Sanitize error message (L-11)**

In the `ApiError` constructor or where the error message is built, change to omit URL in production:

```typescript
const message = __DEV__ ? `API ${status}: ${url}` : `API ${status}`;
```

- [ ] **Step 3: Store refresh_token (L-13 reduced scope)**

In the login response handler, after storing the JWT, also store the refresh_token:

```typescript
import { SECURE_STORE_KEYS } from "@/constants/config";
import * as SecureStore from "expo-secure-store";

// After successful login:
if (response.refresh_token) {
  await SecureStore.setItemAsync("nxme_refresh_token", response.refresh_token);
}
```

### Task 20: Username validation + apiFetch in card screen (M-14, L-9)

**Files:**
- Modify: `mobile/app/card/[username].tsx`

- [ ] **Step 1: Add username validation and use apiFetch**

Replace the raw `fetch` with `apiFetch` and add `encodeURIComponent`:

```typescript
import { AUTH_VALIDATION, CARD_ENDPOINTS } from "@/constants/config";
import { apiFetch } from "@/lib/api";

// Validate username before API call
if (!AUTH_VALIDATION.USERNAME_PATTERN.test(username)) {
  throw new Error("Invalid username");
}

const data = await apiFetch(CARD_ENDPOINTS.PUBLIC(encodeURIComponent(username)));
```

### Task 21: OG image SSRF protection (M-19)

**Files:**
- Modify: `card-web/src/app/[username]/opengraph-image.tsx`

- [ ] **Step 1: Add image URL validation**

Add a helper function and validate before rendering:

```typescript
const ALLOWED_IMAGE_HOSTS = ["supabase.co", "fal.ai", "fal.media", "fal.run"];

function isAllowedImageUrl(url: string): boolean {
  try {
    const hostname = new URL(url).hostname;
    return ALLOWED_IMAGE_HOSTS.some(
      (h) => hostname === h || hostname.endsWith(`.${h}`)
    );
  } catch {
    return false;
  }
}
```

Before using `card.before_image_url` and `card.after_image_url`, validate them:

```typescript
const beforeUrl = isAllowedImageUrl(card.before_image_url) ? card.before_image_url : "";
const afterUrl = isAllowedImageUrl(card.after_image_url) ? card.after_image_url : "";
```

---

## Agent 4: Information Disclosure & Logging (14 fixes)

### Task 22: Sanitize readiness endpoint (H-4)

**Files:**
- Modify: `app/api/health.py:34-42`

- [ ] **Step 1: Replace detailed error messages with generic ones**

```python
    try:
        await r.ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        logger.error("Redis readiness check failed: %s", exc)
        checks["redis"] = "unavailable"

    try:
        supabase.table("tiers").select("id").limit(1).execute()
        checks["supabase"] = "ok"
    except Exception as exc:  # noqa: BLE001
        logger.error("Supabase readiness check failed: %s", exc)
        checks["supabase"] = "unavailable"
```

### Task 23: app/main.py — 4 consolidated fixes (H-8, C-2, M-2, M-25)

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Add demo secret guard in lifespan (H-8)**

After the mock adapter block (after line 49), add:

```python
    # H-8: Reject well-known demo JWT secrets in non-development environments
    _DEMO_SECRETS = {
        "super-secret-jwt-token-with-at-least-32-characters-long",
        "local-dev-secret-key-change-in-production",
    }
    if settings.APP_ENV != "development":
        if settings.SUPABASE_JWT_SECRET in _DEMO_SECRETS:
            msg = "FATAL: Well-known demo SUPABASE_JWT_SECRET detected in non-development environment"
            logger.critical(msg)
            raise SystemExit(msg)
        if settings.SECRET_KEY in _DEMO_SECRETS:
            msg = "FATAL: Well-known demo SECRET_KEY detected in non-development environment"
            logger.critical(msg)
            raise SystemExit(msg)
```

- [ ] **Step 2: Add ContentSizeLimitMiddleware (C-2)**

Add import at the top:

```python
from starlette.middleware.trustedhost import TrustedHostMiddleware  # already may exist
```

In `create_app()`, after `SecurityHeadersMiddleware`, add:

```python
    # C-2: Limit request body size to prevent OOM via unbounded uploads
    from starlette.middleware import Middleware
    # Note: Starlette doesn't have a built-in ContentSizeLimitMiddleware.
    # Use a simple ASGI middleware instead:
    max_body = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @app.middleware("http")
    async def limit_request_body(request, call_next):
        if request.headers.get("content-length"):
            content_length = int(request.headers["content-length"])
            if content_length > max_body:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request body too large"},
                )
        return await call_next(request)
```

Add `from starlette.responses import JSONResponse as StarletteJSONResponse` at the import if needed, or use FastAPI's:

```python
from fastapi.responses import JSONResponse
```

- [ ] **Step 3: Restrict docs to development only (M-2)**

Change lines 114-115:

```python
        docs_url="/docs" if settings.APP_ENV == "development" else None,
        redoc_url="/redoc" if settings.APP_ENV == "development" else None,
```

- [ ] **Step 4: Add CORS decision comment (M-25)**

Add after the middleware block:

```python
    # M-25: No CORSMiddleware added — this API is consumed by the mobile app
    # (native HTTP, no CORS) and card-web (server-side rendering, no browser-direct
    # calls). If browser-direct calls are needed in the future, add CORSMiddleware
    # with explicit allow_origins (never "*").
```

### Task 24: Remove PII from auth logs (M-1)

**Files:**
- Modify: `app/api/auth.py:234`

- [ ] **Step 1: Remove email from log**

Change line 234:

```python
    logger.info("Registered user %s", user_id)
```

### Task 25: Fix webhook error handling for Stripe retries (M-5)

**Files:**
- Modify: `app/api/webhooks.py:55-84`
- Modify: `app/repositories/subscription_repo.py` (add `is_webhook_event_processed` method)

- [ ] **Step 0: Add read-only idempotency check to SubscriptionRepository**

Add to `app/repositories/subscription_repo.py`:

```python
def is_webhook_event_processed(self, provider: str, event_id: str) -> bool:
    """Check if a webhook event has already been processed (read-only)."""
    result = (
        self._sb.table("processed_webhook_events")
        .select("id")
        .eq("provider", provider)
        .eq("event_id", event_id)
        .limit(1)
        .execute()
    )
    return bool(result.data)
```

- [ ] **Step 1: Move idempotency recording AFTER processing**

Restructure the event processing:

```python
    # --- Route to handler (process BEFORE recording idempotency) ---
    try:
        data = event.data.get("data", {}).get("object", {})

        if event_type == "checkout.session.completed":
            await _handle_checkout_completed(sub_repo, data, event_id)
        elif event_type == "customer.subscription.created":
            _handle_subscription_created(sub_repo, data)
        elif event_type == "customer.subscription.updated":
            _handle_subscription_updated(sub_repo, data)
        elif event_type == "customer.subscription.deleted":
            _handle_subscription_deleted(sub_repo, data)
        elif event_type == "invoice.payment_failed":
            _handle_payment_failed(sub_repo, data)
        else:
            logger.info("Unhandled webhook event type: %s", event_type)

    except (httpx.HTTPError, ConnectionError, TimeoutError, OSError) as exc:
        logger.warning("Transient error processing webhook %s (type=%s): %s", event_id, event_type, exc)
        # Return 500 so Stripe retries (M-5)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "TRANSIENT_ERROR", "message": "Temporary processing error"}},
        ) from exc

    # Record idempotency AFTER successful processing
    sub_repo.record_webhook_event(provider="stripe", event_id=event_id)

    return {"status": "processed"}
```

Also add an idempotency check at the top that just reads (doesn't write):

```python
    if sub_repo.is_webhook_event_processed(provider="stripe", event_id=event_id):
        logger.info("Duplicate webhook event %s — skipping", event_id)
        return {"status": "already_processed"}
```

### Task 26: Fix fire-and-forget memory extraction (M-6)

**Files:**
- Modify: `app/advisor/service.py:153-169`

- [ ] **Step 1: Add proper exception handling**

Replace the callback with a proper handler:

```python
        async def _extract_with_logging() -> None:
            try:
                await self._memory_manager.extract_memories_from_turn(
                    user_id=user_id,
                    user_message=message,
                    advisor_response=advisor_response,
                )
            except Exception:
                logger.warning(
                    "Memory extraction failed for user %s. Will retry on next message.",
                    str(user_id),
                    exc_info=True,
                )

        asyncio.create_task(_extract_with_logging())
```

### Task 27: Mobile _layout.tsx — 4 consolidated fixes (M-10, M-11, M-12, H-6 StripeProvider)

**Files:**
- Modify: `mobile/app/_layout.tsx`

- [ ] **Step 1: Sanitize init error log (M-10)**

Change `console.warn("App initialization error:", error)` to:

```typescript
console.warn("App initialization failed");
```

- [ ] **Step 2: Sanitize deep link rejection log (M-11)**

Change `console.warn("Rejected non-universal deep link:", event.url)` to:

```typescript
console.warn("Rejected non-universal deep link");
```

- [ ] **Step 3: Add JWT expiry check (M-12)**

Where `getStoredJwt()` is called, add expiry validation:

```typescript
const jwt = await getStoredJwt();
if (jwt) {
  // Decode JWT exp claim without verification (validation happens server-side)
  try {
    const payload = JSON.parse(atob(jwt.split(".")[1]));
    if (payload.exp && payload.exp * 1000 < Date.now()) {
      // Token expired — clear it
      await SecureStore.deleteItemAsync(SECURE_STORE_KEYS.JWT);
    }
  } catch {
    // Malformed token — clear it
    await SecureStore.deleteItemAsync(SECURE_STORE_KEYS.JWT);
  }
}
```

- [ ] **Step 4: Change StripeProvider urlScheme (H-6)**

Change `urlScheme="nxme"` to use the universal link:

```tsx
<StripeProvider
  publishableKey={STRIPE_PUBLISHABLE_KEY}
  urlScheme="https"
  // ...
>
```

### Task 28: Migration runner DSN comment (L-5)

**Files:**
- Modify: `app/migrations/run.py:217-218`

- [ ] **Step 1: Add comment**

Before `conn = psycopg2.connect(dsn)`:

```python
    # Security: DSN contains credentials — never log it.
    # Use only for the connection, then discard.
    dsn = _get_dsn()
    conn = psycopg2.connect(dsn)
```

### Task 29: Permissions-Policy header (L-6)

**Files:**
- Modify: `app/api/middleware/security_headers.py:25`

- [ ] **Step 1: Add Permissions-Policy after CSP**

```python
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
```

### Task 30: Card-web error boundary fixes (L-14)

**Files:**
- Modify: `card-web/src/app/error.tsx`
- Modify: `card-web/src/app/[username]/error.tsx`

- [ ] **Step 1: Guard console.error in both files**

Replace `console.error(error)` with:

```typescript
if (process.env.NODE_ENV !== "production") {
  console.error(error);
}
```

### Task 31: Card-web API error message (L-15)

**Files:**
- Modify: `card-web/src/lib/api.ts:46`

- [ ] **Step 1: Use generic error message**

Replace:
```typescript
throw new Error(`Failed to fetch card for "${username}": ${res.status} ${res.statusText}`);
```
with:
```typescript
throw new Error("Unable to load this card. Please try again later.");
```

### Task 32: Card-web API_URL fallback warning (L-16)

**Files:**
- Modify: `card-web/src/config/constants.ts`

- [ ] **Step 1: Add warning when falling back**

```typescript
export const API_BASE_URL: string = (() => {
  const serverUrl = process.env.API_URL;
  if (serverUrl) return serverUrl;
  if (process.env.NODE_ENV === "production") {
    console.warn(
      "[config] API_URL not set — falling back to NEXT_PUBLIC_API_URL. " +
      "Set API_URL for server-side requests in production."
    );
  }
  return process.env.NEXT_PUBLIC_API_URL ?? "https://api.nxme.ai";
})();
```

### Task 33: CSRF documentation comment (Info)

**Files:**
- Modify: `card-web/src/app/api/revalidate/route.ts`

- [ ] **Step 1: Add comment at top of file**

```typescript
// Security: No CSRF protection needed — this endpoint uses a shared secret
// header (not cookies) for authentication. It is called server-to-server
// by the backend, not by browsers. If cookie-authenticated endpoints are
// added in the future, implement CSRF tokens or SameSite cookies.
```

---

## Agent 5: Infra & Dependencies (10 fixes)

### Task 34: Secure Redis (H-10, L-22)

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add password, restrict binding, remove version**

```yaml
services:
  redis:
    image: redis:7.2-alpine
    container_name: nxme-redis
    ports:
      - "127.0.0.1:6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD:-localdev}
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD:-localdev}", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
    restart: unless-stopped

volumes:
  redis_data:

networks:
  default:
    name: nxme-dev
```

Note: REDIS_URL default in `app/config/__init__.py` is updated in Task 5 (Agent 1 owns that file).
Also update `scripts/local-env.sh` if it sets REDIS_URL.

### Task 35: Docker dev non-root + gcc cleanup (M-22, L-18)

**Files:**
- Modify: `Dockerfile`

- [ ] **Step 1: Remove gcc after pip install and add non-root to dev**

```dockerfile
# ── Base ────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for Pillow / MediaPipe / psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Remove build tools after pip install (L-18)
RUN apt-get purge -y gcc && apt-get autoremove -y


# ── Dev ─────────────────────────────────────────────────────────────────────
FROM base AS dev

COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt

# Non-root user for dev (M-22)
RUN groupadd -r appuser && useradd -r -g appuser appuser

COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]


# ── Production ──────────────────────────────────────────────────────────────
FROM base AS prod

RUN groupadd -r appuser && useradd -r -g appuser appuser

COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "4", "--proxy-headers"]
```

### Task 36: Next.js CVE verification (M-24)

**Files:**
- Modify: `card-web/package.json` (if upgrade needed)

- [ ] **Step 1: Verify CVE patches**

Run: `cd card-web && npm audit`

Check if Next.js 14.2.29 is affected by CVE-2024-51479, CVE-2025-29927, CVE-2024-46982. If yes, upgrade. If already patched, add a comment in package.json.

### Task 37: Disposable email startup guard (L-2)

**Files:**
- Modify: `app/services/disposable_email.py:25-34`

- [ ] **Step 1: Fail startup in non-dev if package missing**

```python
except ImportError:
    from app.config import settings as _settings
    if _settings.APP_ENV not in ("development", "test"):
        raise RuntimeError(
            "disposable-email-domains package required in non-development environments. "
            "Run: pip install disposable-email-domains"
        )
    logger.critical(
        "disposable-email-domains package not installed — using minimal fallback blocklist."
    )
    _DISPOSABLE_DOMAINS: set[str] = {
        "mailinator.com", "guerrillamail.com", "yopmail.com",
        "tempmail.com", "throwaway.email", "sharklasers.com",
        "10minutemail.com", "maildrop.cc", "trashmail.com",
    }
```

### Task 38: Stuck jobs index migration (L-7)

**Files:**
- Create: `app/migrations/0022_stuck_jobs_index.sql`

- [ ] **Step 1: Create composite index**

```sql
-- Composite index for watchdog stuck job query (L-7)
CREATE INDEX IF NOT EXISTS idx_glow_up_jobs_status_updated
  ON glow_up_jobs (status, updated_at)
  WHERE status IN ('processing', 'finalizing');

-- DOWN:
DROP INDEX IF EXISTS idx_glow_up_jobs_status_updated;
```

### Task 39: Mobile push token projectId (L-12)

**Files:**
- Modify: `mobile/lib/notifications.ts`

- [ ] **Step 1: Add explicit projectId**

```typescript
import Constants from "expo-constants";

const token = await Notifications.getExpoPushTokenAsync({
  projectId: Constants.expoConfig?.extra?.eas?.projectId,
});
```

### Task 40: Pin Supabase hostname in card-web (L-17)

**Files:**
- Modify: `card-web/next.config.mjs`

- [ ] **Step 1: Pin to specific Supabase project**

Replace the wildcard `*.supabase.co` with the project-specific hostname. Read from env:

```javascript
{
  protocol: 'https',
  hostname: process.env.NEXT_PUBLIC_SUPABASE_HOSTNAME ?? '**.supabase.co',
}
```

If the env var isn't available, keep the wildcard but add a comment documenting the trade-off.

### Task 41: Pin onnxruntime (L-21)

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add version constraint**

Find the `onnxruntime` line (or add one) and ensure:

```
onnxruntime>=1.19,<2.0
```

### Task 42: npm audit script (Info)

**Files:**
- Modify: `card-web/package.json`

- [ ] **Step 1: Add audit script**

In the `scripts` section:

```json
"audit": "npm audit --audit-level=high"
```

---

## Phase 6: Verification

### Task 43: Python lint, format, type-check

- [ ] **Step 1: Run ruff**

```bash
cd /Users/vladimirtrifonov/src/ai/nxme.ai
ruff check --fix app/ conftest.py
ruff format app/ conftest.py
```

- [ ] **Step 2: Run pytest**

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -x -q 2>&1 | head -50
```

Fix any failures.

### Task 44: Mobile TypeScript check

- [ ] **Step 1: Run tsc**

```bash
cd mobile && npx tsc --noEmit 2>&1 | head -50
```

Fix any errors.

### Task 45: Card-web TypeScript + build + lint

- [ ] **Step 1: Run checks**

```bash
cd card-web && npx tsc --noEmit && npm run build && npx eslint src/ 2>&1 | head -50
```

Fix any errors.

### Task 46: Commit, PR, merge

- [ ] **Step 1: Stage changed files (review first)**

```bash
git status  # Review all changes
git diff    # Review unstaged changes
# Stage specific files (never git add -A):
git add app/ mobile/ card-web/ supabase/ Dockerfile docker-compose.yml conftest.py requirements.txt docs/security-audit-2026-03-19.md
```

- [ ] **Step 2: Commit**

```bash
git commit -m "fix(security): remediate all 60 findings from 2026-03-19 audit

Fixes across all severity levels:
- 3 Critical: missing tiers module, unbounded upload, trial grant race
- 10 High: SSRF, API key leak, custom URI scheme, Redis auth, demo secrets
- 25 Medium: XSS, timing attacks, rate limits, PII logging, Supabase config
- 22 Low: hash truncation, headers, dependencies, error messages"
```

- [ ] **Step 3: Push and create PR**

```bash
git push -u origin fix/app-audit-2026-03-19
gh pr create --base dev --title "fix(security): remediate all audit findings" --body "..."
```

- [ ] **Step 4: Merge to dev**

```bash
gh pr merge --merge
```
