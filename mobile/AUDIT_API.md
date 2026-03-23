# NXME API Audit Report

**Date**: 2026-03-23
**Backend**: http://localhost:8001 (FastAPI + Supabase + Redis)
**Mobile config**: `constants/config.ts`
**Test user**: `audit_tester` / `audit_test@nxme.ai`

---

## Summary

| Severity | Count |
|----------|-------|
| Critical | 3     |
| Major    | 5     |
| Minor    | 4     |

---

## Critical Findings

### C-1: `maybe_single().execute()` returns `None` -- causes 500 on all "not found" lookups

- **Endpoints affected**: ALL endpoints that look up a resource by ID (26 call sites)
  - `GET /v1/analyses/{id}` -- 500 instead of 404
  - `GET /v1/jobs/{id}` -- 500 instead of 404
  - `POST /v1/jobs/{id}/cancel` -- 500 instead of 404
  - `GET /v1/users/{username}/profile` -- 500 for nonexistent username
  - `POST /v1/advisor/nudges/{id}/read` -- 500 instead of 404
  - `PATCH /v1/advisor/nudges/{id}` -- 500 instead of 404
  - Every repo method using `maybe_single()` pattern
- **Expected**: 404 with structured error JSON
- **Actual**: HTTP 500 "Internal Server Error" (plain text)
- **Root cause**: `supabase-py` v2.15.1 / `postgrest` v1.0.2 `maybe_single().execute()` returns `None` (not an object with `.data = None`) when zero rows match. Every repo does `result.data or None`, which throws `AttributeError: 'NoneType' object has no attribute 'data'`.
- **Affected files** (26 locations):
  - `app/repositories/analysis_repo.py` (lines 35, 61, 112)
  - `app/repositories/job_repo.py` (lines 42, 53, 64, 87, 98, 109, 120)
  - `app/repositories/user_repo.py` (lines 33, 45, 66, 101)
  - `app/repositories/image_repo.py` (lines 31, 42)
  - `app/repositories/post_repo.py` (lines 57, 68, 80, 200)
  - `app/repositories/advisor_repo.py` (line 204)
  - `app/repositories/feed_repo.py` (line 99)
  - `app/repositories/subscription_repo.py` (line 46)
  - `app/advisor/memory_manager.py` (line 295)
  - `app/api/deps.py` (line 108)
  - `app/generation/worker.py` (line 304)
- **How to fix**: Add a null guard in every repo method, or create a wrapper:
  ```python
  def _safe_execute(query):
      result = query.maybe_single().execute()
      if result is None:
          return None
      return result.data
  ```
  Then replace all `result = (...).maybe_single().execute(); return result.data or None` with `return _safe_execute(query)`.

### C-2: JWT remains valid after POST /v1/auth/logout

- **Endpoint**: `POST /v1/auth/logout`
- **Expected**: After logout, subsequent requests with the same JWT return 401
- **Actual**: Token continues to work (tested 2 seconds after logout, returned 200 with user data)
- **Tested with**: `GET /v1/auth/me` using the same JWT after successful 204 logout
- **Root cause**: `supabase.auth.admin.sign_out()` is called, but the NXME JWT validation (`validate_jwt` in `app/api/middleware/auth.py`) validates the JWT signature locally (ES256 key check) without checking Supabase's revocation list. The token remains valid until its `exp` claim.
- **How to fix**: Implement a Redis-based token blocklist. On logout, add the JWT's `jti` or full token hash to a Redis set with TTL = remaining token lifetime. In `validate_jwt`, check the blocklist before accepting the token.

### C-3: Missing `/v1/auth/refresh` endpoint -- mobile refresh flow is broken

- **Endpoint**: `POST /v1/auth/refresh`
- **Expected**: Accepts `{ refresh_token }` and returns new `{ access_token, refresh_token }`
- **Actual**: HTTP 404 `{"detail":"Not Found"}`
- **Mobile code**: `lib/api.ts` calls `AUTH_ENDPOINTS.REFRESH` (`/v1/auth/refresh`) on every 401 response. When this fails, all tokens are cleared and the user is logged out.
- **Impact**: Every time the JWT expires (typically 1 hour with Supabase), the mobile app force-logs out the user instead of silently refreshing.
- **How to fix**: Add `POST /auth/refresh` to `app/api/auth.py` that calls `supabase.auth.refresh_session({ refresh_token })` and returns the new session tokens. The mobile config already documents this as forward-compatible (line 51-55 of `config.ts`).

---

## Major Findings

### M-1: Missing `/v1/jobs/{id}/refund` endpoint

- **Endpoint**: `POST /v1/jobs/{id}/refund`
- **Expected**: Backend refund endpoint for generation jobs
- **Actual**: HTTP 404 `{"detail":"Not Found"}`
- **Mobile config**: `ANALYSIS_ENDPOINTS.JOB_REFUND` at line 73 references this path
- **Impact**: The refund button in the mobile app always fails. The mobile code handles this gracefully (shows a failure alert per comment on line 69-71), but the feature is completely non-functional.
- **How to fix**: Implement `POST /jobs/{job_id}/refund` in `app/api/generation.py`. Should verify job is `completed` or `failed`, release credit reservation if one exists, and mark the refund.

### M-2: `POST /v1/credits/purchase` uses wrong Stripe price config

- **Endpoint**: `POST /v1/credits/purchase` (deprecated alias for `POST /v1/credit-purchases`)
- **Expected**: Returns Stripe checkout URL
- **Actual**: HTTP 503 `{"error":{"code":"CREDIT_PACK_NOT_CONFIGURED","message":"Credit pack pricing not configured."}}`
- **Root cause**: The `STRIPE_PRICE_CREDITS_10`, `STRIPE_PRICE_CREDITS_25`, `STRIPE_PRICE_CREDITS_50` env vars are not set. This is likely an environment config issue, but the mobile app's `ENTITLEMENT_ENDPOINTS.PURCHASE_CREDITS` points to the deprecated `/v1/credits/purchase` path, not the canonical `/v1/credit-purchases`.
- **How to fix**: (a) Set Stripe price env vars, (b) Update mobile `ENTITLEMENT_ENDPOINTS.PURCHASE_CREDITS` from `/v1/credits/purchase` to `/v1/credit-purchases`.

### M-3: Reaction count drift between Redis and DB

- **Endpoint**: `POST /v1/posts/{id}/reactions`
- **Expected**: `reaction_count` in the feed matches the actual number of reactions in the DB
- **Actual**: Stored `reaction_count` on posts drifts from actual count. Post `bbbbbbbb...0001` shows stored=5, actual=1 (drift=+4). Post `bbbbbbbb...0002` shows stored=3, actual=1 (drift=+2).
- **Root cause**: The reaction endpoint uses Redis INCR optimistically and relies on ARQ background worker (`persist_reaction`) to sync to DB. The worker decrements Redis on duplicates, but the post's `reaction_count` column is seeded from test data (not from actual reactions). In production, the `reconcile_reaction_counts` nightly job would fix this, but between reconciliation runs the counts can be stale.
- **How to fix**: (a) Run the `reconcile_reaction_counts` ARQ task more frequently (hourly), (b) When `persist_reaction` inserts a new reaction, use the DB function to atomically update `posts.reaction_count` and use THAT value to re-seed Redis (instead of trusting the Redis counter).

### M-4: Registration fails silently on second attempt (no public.users row)

- **Endpoint**: `POST /v1/auth/register`
- **Expected**: Clear error message if auth user already exists without a public.users row
- **Actual**: Returns `{"error":{"code":"INTERNAL_ERROR","message":"Account creation failed."}}` with no indication of what failed
- **Root cause**: The first registration creates the Supabase auth user but may fail on the `public.users` INSERT (e.g., due to unique constraint). The rollback deletes the auth user. On the second attempt, the email is now "available" in Supabase auth, a new auth user is created, but the INSERT into `public.users` can fail again for the same reason (e.g., username collision from a different path). The 500 error message is not actionable.
- **How to fix**: Add more specific error mapping in `_handle_supabase_auth_error()` and in the `users INSERT` catch block. Return 409 for username conflicts, 422 for constraint violations with a clear message.

### M-5: `POST /v1/auth/verify-email` returns 500 instead of meaningful error

- **Endpoint**: `POST /v1/auth/verify-email`
- **Expected**: Tells user their email is not yet verified, or grants trial
- **Actual**: HTTP 500 `{"error":{"code":"INTERNAL_ERROR","message":"Could not verify email status."}}`
- **Root cause**: `user_repo.auth_get_user(user_id_str)` calls Supabase admin API which may fail if the admin operations are rate-limited or the Supabase service is misconfigured. The generic error message hides the underlying cause.
- **How to fix**: Improve error handling in the auth_get_user call with more specific error messages and logging of the actual exception type.

---

## Minor Findings

### m-1: Mobile `ENTITLEMENT_ENDPOINTS.PURCHASE_CREDITS` uses deprecated path

- **Mobile config**: `PURCHASE_CREDITS: "/v1/credits/purchase"`
- **Backend canonical**: `POST /v1/credit-purchases` (the `/v1/credits/purchase` is marked `deprecated=True`)
- **Impact**: Works today via the deprecated alias, but the alias may be removed in a future version.
- **How to fix**: Update mobile config `PURCHASE_CREDITS` to `/v1/credit-purchases`.

### m-2: Mobile `ADVISOR_ENDPOINTS.NUDGE_READ` uses deprecated path

- **Mobile config**: `NUDGE_READ: (id: string) => \`/v1/advisor/nudges/${id}/read\``
- **Backend canonical**: `PATCH /v1/advisor/nudges/{nudge_id}` with `{"read": true}`
- **Backend deprecated**: `POST /v1/advisor/nudges/{nudge_id}/read` (works today)
- **Impact**: Works via the deprecated alias, but the canonical method uses PATCH with a body.
- **How to fix**: Update mobile to use `PATCH /v1/advisor/nudges/{id}` with `{"read": true}`.

### m-3: Comment max length mismatch between mobile and backend

- **Mobile config**: `COMMENTS_CONFIG.MAX_COMMENT_LENGTH = 500`
- **Backend validation**: `CreateCommentRequest.content` has `max_length=1000`
- **Impact**: Mobile truncates at 500 chars but backend allows 1000. No bug, but the client is unnecessarily restrictive. If backend reduces to 500 later, it would be consistent.
- **How to fix**: Align -- either increase mobile to 1000 or decrease backend to 500.

### m-4: Profile endpoint `total_reactions` does not reflect soft-deleted posts

- **Endpoint**: `GET /v1/users/{username}/profile`
- **Expected**: `total_reactions` only counts reactions from active (non-deleted) posts
- **Actual**: After deleting post `bbbbbbbb...0001`, the profile shows `total_reactions: 0` and `post_count: 0`. This is correct behavior after delete.
- **Note**: The `get_user_post_stats` DB function correctly excludes deleted posts. However, the initial reaction count (before delete) showed `total_reactions: 5` which was seeded from test data and not from actual reactions, masking a potential drift issue.
- **How to fix**: No code fix needed, but the reconciliation between post stats and actual DB counts should be validated in integration tests.

---

## Endpoint Path Coverage Matrix

| Mobile Endpoint | Backend Route | Status | Notes |
|----------------|---------------|--------|-------|
| `POST /v1/auth/register` | `POST /v1/auth/register` | OK | 422 on validation errors |
| `POST /v1/auth/email-login` | `POST /v1/auth/email-login` | OK | Returns JWT |
| `POST /v1/auth/login` (social) | `POST /v1/auth/login` | OK | Requires id_token |
| `POST /v1/auth/refresh` | **MISSING** | CRITICAL | Returns 404 |
| `POST /v1/auth/logout` | `POST /v1/auth/logout` | BUG | 204 but token not invalidated |
| `GET /v1/auth/me` | `GET /v1/auth/me` | OK | Returns user profile |
| `GET /v1/feed` | `GET /v1/feed` | OK | Public, all sorts work |
| `POST /v1/posts/{id}/reactions` | `POST /v1/posts/{id}/reactions` | OK | Redis optimistic counter |
| `GET /v1/posts/{id}/comments` | `GET /v1/posts/{id}/comments` | OK | Public, paginated |
| `POST /v1/posts/{id}/comments` | `POST /v1/posts/{id}/comments` | OK | Auth required |
| `DELETE /v1/posts/{id}` | `DELETE /v1/posts/{id}` | OK | Soft delete, owner only |
| `POST /v1/posts/{id}/report` | `POST /v1/posts/{id}/report` | OK | Auth required |
| `POST /v1/users/{id}/block` | `POST /v1/users/{id}/block` | OK | 204 no content |
| `DELETE /v1/users/{id}/block` | `DELETE /v1/users/{id}/block` | OK | 204 no content |
| `GET /v1/users/blocked` | `GET /v1/users/blocked` | OK | Paginated |
| `GET /v1/users/{username}/profile` | `GET /v1/users/{username}/profile` | BUG | 500 on nonexistent user |
| `GET /v1/users/{username}/history` | `GET /v1/users/{username}/history` | OK | Owner only, 404 for others |
| `PATCH /v1/users/{username}` | `PATCH /v1/users/{username}` | OK | Owner only |
| `GET /v1/entitlement` | `GET /v1/entitlement` | OK | Returns tier/credit info |
| `POST /v1/credits/purchase` | `POST /v1/credits/purchase` | DEPRECATED | Use /v1/credit-purchases |
| `POST /v1/subscriptions` | `POST /v1/subscriptions` | OK | Returns checkout URL |
| `DELETE /v1/subscriptions` | `DELETE /v1/subscriptions` | OK | Cancel at period end |
| `GET /v1/advisor/messages` | `GET /v1/advisor/messages` | OK | Paginated |
| `POST /v1/advisor/messages` | `POST /v1/advisor/messages` | OK | Premium-gated (402) |
| `GET /v1/advisor/nudges` | `GET /v1/advisor/nudges` | OK | Paginated |
| `POST /v1/advisor/nudges/{id}/read` | `POST /v1/advisor/nudges/{id}/read` | BUG | 500 on nonexistent nudge |
| `GET /v1/memories` | `GET /v1/memories` | OK | Paginated |
| `POST /v1/memories` | `POST /v1/memories` | OK | Goal/note types |
| `DELETE /v1/memories/{id}` | `DELETE /v1/memories/{id}` | OK | 404 on nonexistent |
| `GET /api/public/cards/{username}` | `GET /api/public/cards/{username}` | OK | 404 when no posts |
| `POST /v1/analyses` | `POST /v1/analyses` | OK | Multipart upload |
| `POST /v1/analyses/{id}/generate` | `POST /v1/analyses/{id}/generate` | OK | Entitlement-gated |
| `GET /v1/jobs/{id}` | `GET /v1/jobs/{id}` | BUG | 500 on nonexistent job |
| `POST /v1/jobs/{id}/cancel` | `POST /v1/jobs/{id}/cancel` | BUG | 500 on nonexistent job |
| `POST /v1/jobs/{id}/refund` | **MISSING** | MAJOR | Returns 404 |

---

## Data Consistency

| Check | Result |
|-------|--------|
| Comment count accuracy | OK -- `comment_count` matches actual comments |
| Reaction count accuracy | MISMATCH -- Redis optimistic counter diverges from DB |
| Post soft-delete exclusion | OK -- deleted posts excluded from feed and stats |
| User soft-delete | OK -- deleted users return 404 on profile |

---

## Recommendations (priority order)

1. **Fix `maybe_single()` null guard** (C-1): Create a shared `_safe_maybe_single()` utility in a base repo class and refactor all 26 call sites. This is the single most impactful fix -- it eliminates 500 errors across every "not found" path.

2. **Implement `/v1/auth/refresh`** (C-3): Without this, mobile users are force-logged out every time their JWT expires. This is the highest-impact UX bug.

3. **Implement token blocklist for logout** (C-2): Add Redis-based JWT revocation to close the security gap where logged-out tokens remain valid.

4. **Implement `/v1/jobs/{id}/refund`** (M-1): The mobile UI already has the refund flow built, it just needs the backend endpoint.

5. **Fix credit pack pricing config** (M-2): Set `STRIPE_PRICE_CREDITS_*` env vars and update mobile to use the canonical endpoint path.

6. **Improve reaction count sync** (M-3): Consider running reconciliation more frequently or using a write-through pattern instead of pure optimistic Redis.
