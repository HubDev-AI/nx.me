# Social-Only Auth Screen + Editable Username

**Date**: 2026-03-24
**Status**: Approved

## Overview

Simplify the auth screen to social-only (no email form), and add username editing to the existing Edit Profile sheet.

## 1. Auth Screen Simplification

### Current State
`mobile/app/(auth)/login.tsx` is a unified auth screen with social login buttons + email form with login/signup tabs. Email form code is hidden when disabled but present.

### Target State
- **Social buttons only** — no email form code
- Screen fetches enabled providers from backend, renders matching buttons
- Error state with retry if providers endpoint fails
- Hero headline, brand label, HeroBackground unchanged

### Code to Remove from `login.tsx`
- All email form state (`email`, `password`, `confirmPassword`, `username`, `displayName`, `emailMode`)
- All `AuthInput` refs and validation logic
- `handleEmailLogin`, `handleEmailSignup`, `handleEmailSubmit`
- Email mode toggle tabs, `emailEnabled` check
- Imports: `AuthInput`, `AUTH_VALIDATION`, `AUTH_ENDPOINTS.REGISTER`, `AUTH_ENDPOINTS.EMAIL_LOGIN`

### Code to Keep
- `useEnabledProviders` hook (drives button rendering)
- `useSocialAuth` hook (handles Google/Apple/TikTok flows)
- `SocialLoginButtons` component (already config-driven)
- Provider error + retry UI
- `mobile/app/(auth)/signup.tsx` redirect (handles stale deep links)

### Dead Code Cleanup
- `mobile/components/auth/AuthInput.tsx` — only consumer was login.tsx email form. Delete it.

## 2. Username Editing

### Location
Add username field to the existing **Edit Profile sheet** at `mobile/components/profile/EditProfileSheet.tsx`, alongside display_name.

### Frontend Behavior
- Username field with inline validation (3-30 chars, `^[a-zA-Z][a-zA-Z0-9_]*$`)
- Debounced availability check (300ms) via `GET /v1/users/check-username?username=foo`
- Show availability status: available (green check), taken (red X), checking (spinner)
- If within 24h cooldown: username field disabled with hint "You can change your username again in X hours"
- On successful save: update auth context username via `setAuthUsername(newUsername)` so all subsequent API calls use the new username
- Update `hasChanges` dirty-detection to include username field

### Frontend Types
- Add `new_username?: string` to `UpdateProfilePayload` in `mobile/components/profile/types.ts`
- Add `username_change_cooldown_remaining_seconds?: number` to profile response type

### Backend: Username Availability Endpoint (NEW)
**`GET /v1/users/check-username?username=foo`**
- File: `app/api/users.py`
- No auth required (public — needed for availability checking)
- Response: `{ available: bool, reason?: string }` (reason: "taken", "reserved", "invalid")
- Case-insensitive check: `LOWER(username)` comparison
- Also checks `username_reserved_until` for deleted accounts

### Backend: Update Username via PATCH
**`PATCH /v1/users/{username}`** in `app/api/users.py`
- Add optional `new_username: str | None` field to `UpdateProfileRequest` pydantic model
- Validation: 3-30 chars, `^[a-zA-Z][a-zA-Z0-9_]*$`, case-insensitive uniqueness
- **Important**: the endpoint routes by the OLD username in the URL path. The handler already resolves the user by `claims["sub"]` (user_id) for ownership checks. After update, the response must return the new username so the frontend can update its state.
- Rate limit: check `username_changed_at` column — if within 24h, return HTTP 429 with `Retry-After` header and message "Username can only be changed once every 24 hours"
- Uniqueness: validated server-side, 409 on conflict ("Username is already taken")
- On success: update both `username` and `username_changed_at` in a single query
- Response: existing `UpdateProfileResponse` extended with `username` field

### Backend: User Repository
- Add `update_username(user_id, new_username)` method to `app/repositories/user_repo.py`
- Sets both `username` and `username_changed_at` atomically

### Case-Insensitive Uniqueness
Username uniqueness should be case-insensitive (standard for social platforms). `FooBar` and `foobar` are the same username. The availability check and update both use `LOWER(username)` for comparison.

### Shareable Card URL Breakage
When a user changes their username, previously shared card URLs (`nxme.ai/@oldname`) become dead links. **Accepted as a known limitation.** The UI should show a confirmation dialog warning: "Changing your username will break any links you've shared with your current username."

### Rate Limit Details
- Mechanism: DB column `username_changed_at` (not Redis) — simple, persists across restarts
- Cooldown: 24 hours from last change
- HTTP response when on cooldown: `429 Too Many Requests` with `Retry-After` header (seconds remaining)
- Frontend: fetch cooldown status from profile data, disable field + show hint if active

## 3. What Stays Unchanged
- Backend email auth endpoints (`/register`, `/email-login`) — still gated by config flags
- `AUTH_PROVIDER_EMAIL_ENABLED` config flag — stays in backend config
- Onboarding flow — no changes
- Auth guard routing — no changes
- Settings screen — username stays read-only

## 4. Migration

```sql
-- 0031_username_changed_at.sql

-- UP
ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS username_changed_at TIMESTAMPTZ;

-- DOWN (rollback)
-- ALTER TABLE public.users DROP COLUMN IF EXISTS username_changed_at;
```

## 5. Files Changed

### Mobile (modify)
- `mobile/app/(auth)/login.tsx` — strip email form code, social-only
- `mobile/components/profile/EditProfileSheet.tsx` — add username field with availability check
- `mobile/components/profile/types.ts` — add `new_username` to payload type
- `mobile/lib/auth-context.tsx` — no change needed (setAuthUsername already exists)

### Mobile (delete)
- `mobile/components/auth/AuthInput.tsx` — dead code after email form removal

### Mobile (no change)
- `mobile/hooks/useEnabledProviders.ts`
- `mobile/hooks/useSocialAuth.ts`
- `mobile/components/auth/SocialLoginButtons.tsx`
- `mobile/app/(auth)/signup.tsx` (redirect stays)

### Backend (modify)
- `app/api/users.py` — add `new_username` to PATCH handler, add `GET /users/check-username`, enforce 24h cooldown
- `app/repositories/user_repo.py` — add `update_username`, `check_username_availability_ci` methods

### Backend (new)
- `app/migrations/0031_username_changed_at.sql`
