# NXME Audit Cycle 3 — Consolidated Findings

**Date:** 2026-03-23
**Scope:** Full stack re-audit after merge to `dev` — mobile + backend
**Previous:** Cycle 2 found 11 remaining issues (score 8.2/10)
**Method:** 5 parallel agents (UI consistency, API wiring, navigation, backend, design)

---

## Summary

| Severity | Count | Category |
|----------|-------|----------|
| Critical | 4 | API type mismatches, missing endpoints, null safety |
| Major | 5 | Type mismatches, hardcoded values, pagination |
| Minor | 8 | Polish, tech debt, deprecated paths |
| Resolved | 3 | From previous cycles — now confirmed fixed |

---

## Status of Previous Cycle Issues

### Confirmed FIXED since Cycle 2
- **C-2 (JWT logout invalidation):** Now implemented in `auth.py:626-663` via `auth.admin.sign_out(token)` ✅
- **C-1 (maybe_single null safety):** 21 of 23 call sites now have proper null guards ✅ (1 remaining — see CR-4)
- **CommentsSheet keyboard:** `keyboardShouldPersistTaps="handled"` in place ✅

### STILL OPEN from previous cycles
- **C-3 (Missing /v1/auth/refresh):** Not implemented — see CR-1
- **M-1 (Missing /v1/jobs/{id}/refund):** Not implemented — see CR-2
- **Wiring #1 (Analysis response shape):** Not verified — needs separate check
- **Wiring #4 (Feed doesn't filter blocked users server-side):** Not verified — needs separate check

---

## Critical Findings

### CR-1: Missing `/v1/auth/refresh` endpoint [STILL OPEN from C-3]

- **Backend:** No refresh endpoint exists in `app/api/auth.py`
- **Mobile:** `lib/api.ts` calls `POST /v1/auth/refresh` on every 401, gets 404, force-logs out user
- **Impact:** Users are force-logged out every time JWT expires (~1 hour)
- **Fix:** Add `POST /auth/refresh` to `app/api/auth.py` that calls `supabase.auth.refresh_session()`

### CR-2: Missing `/v1/jobs/{id}/refund` endpoint [STILL OPEN from M-1]

- **Backend:** No refund route in `app/api/generation.py`
- **Mobile:** Config references `ANALYSIS_ENDPOINTS.JOB_REFUND` — always returns 404
- **Impact:** Refund feature completely non-functional
- **Fix:** Implement refund endpoint with credit release logic

### CR-3: Nudge response type mismatch — will crash at runtime

- **Mobile:** `lib/advisor.ts:26-32`
  ```
  interface Nudge { id, title, content, type, is_read, created_at }
  ```
- **Backend:** `app/advisor/models.py:81-86`
  ```
  NudgeResponse { id, trigger, content, read_at (nullable string), created_at }
  ```
- **Mismatches:**
  - `title` vs `trigger` — mobile reads undefined
  - `is_read` (boolean) vs `read_at` (nullable string) — type mismatch
  - `type` — doesn't exist in backend response
- **Impact:** NudgeFeed component will show empty titles and broken read status
- **Fix:** Update mobile Nudge interface:
  ```typescript
  interface Nudge {
    id: string;
    trigger: string;      // was: title
    content: string;
    read_at: string | null; // was: is_read: boolean
    created_at: string;
  }
  ```
  Then update all consumers to use `nudge.trigger` and `!!nudge.read_at`

### CR-4: Ban check null safety gap in `deps.py:111`

- **File:** `app/api/deps.py:111`
- **Code:** `is_banned = bool(user_row.data and user_row.data.get("is_banned"))`
- **Problem:** If `user_row` is `None` (maybe_single returns None), throws `AttributeError`
- **Impact:** Every authenticated request could 500 if user row missing
- **Fix:**
  ```python
  if not user_row or not user_row.data:
      is_banned = False
  else:
      is_banned = bool(user_row.data.get("is_banned"))
  ```

---

## Major Findings

### MJ-1: Memory content type mismatch

- **Mobile:** `lib/advisor.ts:47-52` — `content: string`
- **Backend:** `app/advisor/models.py:44-48` — `content: dict[str, Any]`
- **Impact:** All memory fetch/create operations receive dict but expect string
- **Fix:** Change mobile to `content: Record<string, unknown>` and update UI rendering

### MJ-2: Messages response missing `next_cursor`

- **Mobile:** `lib/advisor.ts:21-24` — no `next_cursor` field
- **Backend:** `app/advisor/models.py:95-99` — sends `next_cursor: str | None`
- **Impact:** Advisor message pagination can't fetch beyond first page
- **Fix:** Add `next_cursor: string | null` to `MessagesResponse` and wire into `fetchMessages()`

### MJ-3: Hardcoded spacing values in post detail

- **File:** `app/post/[postId].tsx` lines 418, 422, 476, 477
- **Values:** `paddingHorizontal: 20`, `gap: 10`, `paddingHorizontal: 16`, `paddingVertical: 12`
- **Should be:** `THEME.spacing.xl`, `THEME.spacing.md`, `THEME.spacing.lg`, `THEME.spacing.md`
- **Fix:** Replace all raw numbers with THEME.spacing equivalents

### MJ-4: Hardcoded tab bar bottom padding (magic number)

- **Files:** `app/(tabs)/index.tsx:276`, `app/(tabs)/profile.tsx:294`
- **Value:** `paddingBottom: 90` (assumes tab bar height)
- **Should be:** Derive from tab bar actual height or use a shared constant
- **Fix:** Export `TAB_BAR_HEIGHT` from `_layout.tsx` and use it

### MJ-5: Hardcoded icon colors in post detail header

- **File:** `app/post/[postId].tsx` lines 340, 354, 367, 469
- **Value:** `color="#ffffff"` on close, share, menu icons
- **Should be:** `THEME.colors.white` or `TEXT_INVERSE`
- **Fix:** Replace with theme token

---

## Minor Findings

### mn-1: Deprecated credit purchase endpoint path

- **Mobile:** `config.ts:154` uses `/v1/credits/purchase`
- **Backend:** Canonical is `POST /v1/credit-purchases`, deprecated alias still works
- **Fix:** Update `ENTITLEMENT_ENDPOINTS.PURCHASE_CREDITS` to `/v1/credit-purchases`

### mn-2: Deprecated nudge read endpoint path

- **Mobile:** `config.ts` uses `POST /v1/advisor/nudges/{id}/read`
- **Backend:** Canonical is `PATCH /v1/advisor/nudges/{id}` with `{"read": true}`
- **Fix:** Update mobile to use PATCH method with body

### mn-3: Onboarding uses own SPACING constant instead of THEME

- **File:** `app/onboarding.tsx:28` — `const SPACING = 8`
- **Uses:** `SPACING * 6` instead of `THEME.spacing.xxxl`
- **Fix:** Replace with THEME.spacing tokens

### mn-4: Profile loading uses ActivityIndicator not skeleton

- **File:** `app/(tabs)/profile.tsx:193-199`
- **Current:** Spinner
- **Better:** ProfileSkeleton with shimmer (matches FeedSkeleton pattern)

### mn-5: Onboarding has no error state UI for entitlement fetch

- **File:** `app/onboarding.tsx`
- **Current:** Logs error to console, no user feedback
- **Fix:** Add error fallback with retry button

### mn-6: Inconsistent error response format in backend

- **Some endpoints:** `{"error": {"code": "...", "message": "..."}}`
- **Others:** `"Job not found"` (plain string)
- **Files:** `app/api/generation.py` mixed formats
- **Fix:** Standardize to structured format everywhere

### mn-7: Hardcoded overlay colors in post detail

- **File:** `app/post/[postId].tsx:428,452`
- **Values:** `rgba(0,0,0,0.4)`, `rgba(0,0,0,0.45)` for header buttons and labels
- **Fix:** Add `THEME.colors.imageOverlay` token

### mn-8: Comment max length mismatch

- **Mobile:** `COMMENTS_CONFIG.MAX_COMMENT_LENGTH = 500`
- **Backend:** `CreateCommentRequest.content` allows `max_length=1000`
- **Fix:** Align to same value (either both 500 or both 1000)

---

## Confirmed Working (No Issues)

| Area | Status |
|------|--------|
| Navigation / routing | All 18 routes valid, no orphans, proper back buttons |
| Deep link handling | Secure with URL guard and username validation |
| Memory leak prevention | All subscriptions/timers cleaned up properly |
| Accessibility | 121+ labels, roles, states — excellent coverage |
| Auth flow (login/signup/logout) | Working correctly |
| Feed endpoints (list/react/comment/delete) | Correctly wired |
| Block/unblock operations | Working, 204 handling correct |
| Profile/history endpoints | Correctly wired |
| Entitlement/subscription | Correctly wired |
| Design consistency across screens | Strong — glass cards, fonts, spacing consistent |
| Dynamic accent color | Properly used via useTheme() on all screens |
| Error boundaries | Present at app root |

---

## Priority Fix Order

### Phase 1 — Critical (breaks features)
1. **CR-3:** Fix Nudge type mismatch (mobile-only change, ~15 min)
2. **CR-4:** Fix deps.py ban check null safety (backend, ~5 min)
3. **MJ-1:** Fix Memory content type (mobile-only, ~15 min)
4. **MJ-2:** Add next_cursor to MessagesResponse (mobile-only, ~10 min)

### Phase 2 — Missing endpoints (backend work)
5. **CR-1:** Implement `/v1/auth/refresh` (backend, ~30 min)
6. **CR-2:** Implement `/v1/jobs/{id}/refund` (backend, ~45 min)

### Phase 3 — Consistency & polish
7. **MJ-3–5:** Replace hardcoded values with THEME tokens (~20 min)
8. **mn-1–2:** Update deprecated endpoint paths (~10 min)
9. **mn-3–8:** Minor polish items (~1 hour)

---

## Code Quality Score: 8.4/10 (up from 8.2)

| Dimension | Score | Change | Notes |
|-----------|-------|--------|-------|
| Type Safety | 7.5/10 | -0.5 | Advisor types don't match backend |
| Error Handling | 8.5/10 | = | Solid, minor format inconsistency |
| UX Polish | 8/10 | +0.5 | Design consistency improved |
| Performance | 8.5/10 | = | Memoization, pagination, no N+1 |
| Accessibility | 8.5/10 | +0.5 | 121+ labels verified |
| Code Organization | 8.5/10 | = | Well-structured |
| API Integration | 7/10 | NEW | 3 type mismatches, 2 missing endpoints |
| Security | 8.5/10 | NEW | JWT logout fixed, 1 null safety gap |
