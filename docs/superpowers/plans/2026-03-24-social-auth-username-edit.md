# Social-Only Auth + Editable Username Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strip email form from auth screen (social-only), add username editing to Edit Profile sheet with 24h cooldown and availability checking.

**Architecture:** Auth screen becomes a minimal social-button-only screen driven by `GET /auth/providers`. Username editing is added to the existing Edit Profile sheet with debounced availability checks and a DB-column-based 24h cooldown enforced server-side.

**Tech Stack:** React Native (Expo), FastAPI, Supabase (Postgres), TypeScript

**Spec:** `docs/superpowers/specs/2026-03-24-social-auth-username-edit-design.md`

---

## File Structure

### Mobile (modify)
- `mobile/app/(auth)/login.tsx` — strip email form, keep social-only
- `mobile/components/profile/EditProfileSheet.tsx` — add username field + availability check
- `mobile/components/profile/types.ts` — add `new_username` to payload, add cooldown to profile type
- `mobile/app/(tabs)/profile.tsx` — propagate username change to auth context after save

### Mobile (delete)
- `mobile/components/auth/AuthInput.tsx` — dead code (only consumer was email form)

### Backend (modify)
- `app/api/users.py` — add username availability endpoint, extend PATCH for username changes, include cooldown in profile response
- `app/repositories/user_repo.py` — add `check_username_available_ci`, `update_username`

### Backend (new)
- `app/migrations/0031_username_changed_at.sql`

---

### Task 1: DB Migration — `username_changed_at` column

**Files:**
- Create: `app/migrations/0031_username_changed_at.sql`

- [ ] **Step 1: Write the migration**

```sql
-- 0031_username_changed_at.sql
-- Track when username was last changed (24h cooldown enforcement)

ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS username_changed_at TIMESTAMPTZ;
```

- [ ] **Step 2: Run the migration**

Run: `make migrate`
Expected: Migration applies cleanly

- [ ] **Step 3: Commit**

```bash
git add app/migrations/0031_username_changed_at.sql
git commit -m "feat: add username_changed_at column for edit cooldown"
```

---

### Task 2: Backend — Username availability endpoint + repo methods

**Files:**
- Modify: `app/repositories/user_repo.py` — add `check_username_available_ci`
- Modify: `app/api/users.py` — add `GET /users/check-username`

- [ ] **Step 1: Add case-insensitive username availability check to UserRepository**

Add to `app/repositories/user_repo.py` after the existing `check_username_taken` method:

```python
def check_username_available_ci(self, username: str, exclude_user_id: str | None = None) -> dict:
    """Check if a username is available (case-insensitive).

    Returns { available: bool, reason?: str }.
    Checks: active users, reserved usernames (deleted accounts within reservation window).
    """
    from datetime import datetime, timezone

    # Case-insensitive lookup using Postgres ILIKE
    result = (
        self._sb.table("users")
        .select("id, deleted_at, username_reserved_until")
        .ilike("username", username)
        .execute()
    )

    if not result.data:
        return {"available": True}

    for row in result.data:
        if row.get("deleted_at") is None:
            if exclude_user_id and row["id"] == exclude_user_id:
                continue
            return {"available": False, "reason": "taken"}

        reserved_until_str = row.get("username_reserved_until")
        if reserved_until_str:
            reserved_until = datetime.fromisoformat(reserved_until_str)
            if reserved_until.tzinfo is None:
                reserved_until = reserved_until.replace(tzinfo=timezone.utc)
            if reserved_until > datetime.now(tz=timezone.utc):
                return {"available": False, "reason": "reserved"}

    return {"available": True}
```

- [ ] **Step 2: Add the availability endpoint to `app/api/users.py`**

**Important:** `re`, `Query`, `BaseModel`, `run_sync`, `get_user_repo` are already imported in `users.py` — do NOT add duplicate imports.

Add constants and the endpoint before existing routes:

```python
_USERNAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")
_USERNAME_MIN_LENGTH = 3
_USERNAME_MAX_LENGTH = 30


class UsernameAvailabilityResponse(BaseModel):
    available: bool
    reason: str | None = None


@router.get("/check-username", response_model=UsernameAvailabilityResponse)
async def check_username(
    username: str = Query(min_length=_USERNAME_MIN_LENGTH, max_length=_USERNAME_MAX_LENGTH),
    user_repo: UserRepository = Depends(get_user_repo),
) -> UsernameAvailabilityResponse:
    """Check if a username is available (case-insensitive). No auth required."""
    if not _USERNAME_PATTERN.match(username):
        return UsernameAvailabilityResponse(available=False, reason="invalid")

    result = await run_sync(user_repo.check_username_available_ci, username)
    return UsernameAvailabilityResponse(**result)
```

Note: function name is `check_username` (not `check_username_availability`) to avoid shadowing the existing repo method name.

- [ ] **Step 3: Verify backend compiles**

Run: `python -m py_compile app/api/users.py && python -m py_compile app/repositories/user_repo.py && echo OK`

- [ ] **Step 4: Commit**

```bash
git add app/repositories/user_repo.py app/api/users.py
git commit -m "feat: add username availability endpoint with case-insensitive check"
```

---

### Task 3: Backend — Extend PATCH endpoint for username changes

**Files:**
- Modify: `app/api/users.py` — extend `UpdateProfileRequest`, add cooldown + username change logic
- Modify: `app/repositories/user_repo.py` — add `update_username`

- [ ] **Step 1: Add `update_username` to UserRepository**

```python
def update_username(self, user_id: str, new_username: str) -> None:
    """Update username and set username_changed_at atomically."""
    from datetime import datetime, timezone
    self._sb.table("users").update({
        "username": new_username,
        "username_changed_at": datetime.now(tz=timezone.utc).isoformat(),
    }).eq("id", user_id).execute()
```

- [ ] **Step 2: Extend `UpdateProfileRequest` in `app/api/users.py`**

Add `new_username` field to the existing model (uses constants from Task 2):

```python
class UpdateProfileRequest(BaseModel):
    display_name: str | None = None
    avatar_storage_key: str | None = None
    new_username: str | None = Field(
        default=None,
        min_length=_USERNAME_MIN_LENGTH,
        max_length=_USERNAME_MAX_LENGTH,
        pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$",
    )
```

- [ ] **Step 3: Update PATCH handler**

Three changes to the `update_profile` function in `app/api/users.py`:

**3a. Update the `_lookup_user` select or the `get_by_username` repo method to include `username_changed_at`.**
Add `username_changed_at` to the select fields in `get_by_username()` in `user_repo.py`:
```python
.select("id, username, display_name, avatar_storage_key, created_at, username_changed_at")
```

**3b. Add username change logic** after existing display_name/avatar handling and before the `user_repo.update_profile(user_id, updates)` call:

```python
# --- Username change (with 24h cooldown) ---
username_changed = False
if body.new_username is not None and body.new_username != user_row["username"]:
    # Enforce 24h cooldown
    username_changed_at_str = user_row.get("username_changed_at")
    if username_changed_at_str:
        from datetime import datetime, timedelta, timezone
        last_change = datetime.fromisoformat(username_changed_at_str)
        if last_change.tzinfo is None:
            last_change = last_change.replace(tzinfo=timezone.utc)
        cooldown_end = last_change + timedelta(hours=24)
        now = datetime.now(tz=timezone.utc)
        if now < cooldown_end:
            remaining = int((cooldown_end - now).total_seconds())
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Username can only be changed once every 24 hours.",
                headers={"Retry-After": str(remaining)},
            )

    # Check availability (case-insensitive)
    availability = await run_sync(
        user_repo.check_username_available_ci,
        body.new_username,
        user_id,
    )
    if not availability["available"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username is {availability.get('reason', 'unavailable')}.",
        )

    # Apply username change atomically (separate from other updates)
    try:
        await run_sync(user_repo.update_username, user_id, body.new_username)
        username_changed = True
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username is taken.",
            )
        raise
```

**3c. Fix the re-fetch after update.** The current code re-fetches the user by the old username from the URL path. After a username change, the old username is no longer valid. Change the re-fetch to use `user_id` instead of the URL's `username` param. Add a `get_profile_by_id` call (already exists in UserRepository) or use the existing one. The re-fetched row should use the user_id which doesn't change.

**3d. Include `username` in `UpdateProfileResponse`.** Check if `UpdateProfileResponse` already includes `username` — if not, add it. Also add `username_change_cooldown_remaining_seconds: int | None` to the response so the frontend can proactively disable the field.

- [ ] **Step 4: Verify backend compiles**

Run: `python -m py_compile app/api/users.py && echo OK`

- [ ] **Step 5: Commit**

```bash
git add app/api/users.py app/repositories/user_repo.py
git commit -m "feat: support username changes in PATCH with 24h cooldown"
```

---

### Task 4: Mobile — Strip email form from auth screen

**Files:**
- Modify: `mobile/app/(auth)/login.tsx` — remove email form code
- Delete: `mobile/components/auth/AuthInput.tsx`

- [ ] **Step 1: Rewrite `login.tsx` as social-only**

Remove all email-related code:
- State: `showEmailForm`, `emailMode`, `email`, `password`, `confirmPassword`, `username`, `displayName`, `isEmailLoading` (lines 85-94)
- Refs: `emailRef`, `passwordRef`, `confirmPasswordRef`, `usernameRef`, `displayNameRef`
- Functions: `validate`, `resolveUsername`, `handleEmailLogin`, `handleEmailSignup`, `handleEmailSubmit`
- `emailEnabled` variable and all conditionals using it
- Email toggle divider JSX
- Email form JSX (mode tabs, AuthInput fields, GlowButton CTA)
- Imports: `AuthInput`, `AUTH_VALIDATION`, `AUTH_ENDPOINTS` (REGISTER, EMAIL_LOGIN), `TextInput`, `Pressable`
- Remove `AUTH_INPUT_BG` from colors import if unused after removal

Keep: `useEnabledProviders`, `useSocialAuth`, `SocialLoginButtons`, provider error/retry, hero background, general error display.

Simplify: `isAnyLoading` = just `isSocialLoading`. `FieldErrors` = just `{ general?: string }`.

Remove unused styles: `form`, `inputCard`, `ctaWrapper`, `modeToggle`, `modeTab`, `modeTabActive`, `modeTabText`, `modeTabTextActive`, `toggleRow`, `toggleDividerLine`, `toggleText`.

- [ ] **Step 2: Delete `AuthInput.tsx`**

```bash
rm mobile/components/auth/AuthInput.tsx
```

Verify no other file imports it:
Run: `grep -r "AuthInput" mobile/ --include="*.ts" --include="*.tsx" | grep -v node_modules`
Expected: no results

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd mobile && npx tsc --noEmit 2>&1 | grep -E "(login\.tsx|AuthInput)" | head -10`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add mobile/app/\(auth\)/login.tsx
git rm mobile/components/auth/AuthInput.tsx
git commit -m "refactor: strip email form from auth screen, social-only"
```

---

### Task 5: Mobile — Add username field + availability check to Edit Profile Sheet

**Files:**
- Modify: `mobile/components/profile/types.ts` — add `new_username` to payload, cooldown to profile type
- Modify: `mobile/components/profile/EditProfileSheet.tsx` — add username field with debounced availability

- [ ] **Step 1: Update types**

In `mobile/components/profile/types.ts`:

```typescript
export interface UpdateProfilePayload {
  display_name?: string;
  new_username?: string;
}
```

Also check if `UserProfile` needs `username_change_cooldown_remaining_seconds` — if the backend returns it in the profile response, add it to the type.

- [ ] **Step 2: Add username editing to EditProfileSheet**

Import `apiFetch` from `../../lib/api` and `Alert` from `react-native`.

Add state vars:
```typescript
const [newUsername, setNewUsername] = useState(profile.username);
const [usernameAvailable, setUsernameAvailable] = useState<boolean | null>(null);
const [usernameChecking, setUsernameChecking] = useState(false);
const [usernameError, setUsernameError] = useState<string | null>(null);
```

Add debounced availability check via `useEffect` (300ms timeout, skip if unchanged from `profile.username`, validate format locally first, then call `GET /v1/users/check-username`).

Update `hasChanges` to include `newUsername !== profile.username`.

Add username `TextInput` in JSX above/below display name with availability indicator (green check / red X / spinner).

- [ ] **Step 3: Update save flow with confirmation dialog**

In `handleSave`, if username changed:
1. Include `new_username: newUsername` in the payload
2. Show `Alert.alert` warning about broken links before saving
3. Handle 429 (cooldown) and 409 (taken) responses specifically in the error handling

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd mobile && npx tsc --noEmit 2>&1 | grep "EditProfileSheet" | head -10`
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add mobile/components/profile/types.ts mobile/components/profile/EditProfileSheet.tsx
git commit -m "feat: add username editing to Edit Profile sheet with availability check"
```

---

### Task 6: Mobile — Propagate username change to auth context

**Files:**
- Modify: `mobile/app/(tabs)/profile.tsx` — update auth context after username save

- [ ] **Step 1: Update profile.tsx handleSaveProfile**

In `profile.tsx`, after a successful save that included a username change, call `setUsername(newUsername)` from the auth context (`useAuth`). The profile screen already has access to `useAuth` — check if it destructures `setUsername`. If not, add it.

The `updateProfile` callback in `useProfile` hook should return the response so the caller knows if the username changed. Check the current return type and adjust if needed.

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd mobile && npx tsc --noEmit 2>&1 | grep "profile" | head -10`

- [ ] **Step 3: Commit**

```bash
git add mobile/app/\(tabs\)/profile.tsx
git commit -m "feat: propagate username changes to auth context"
```

---

### Task 7: Final verification

- [ ] **Step 1: Backend lint**

Run: `make lint`
Expected: no new errors from our changes

- [ ] **Step 2: Mobile TypeScript check**

Run: `cd mobile && npx tsc --noEmit 2>&1 | grep -v node_modules | head -20`
Expected: no new errors from our changes

- [ ] **Step 3: Manual test checklist**

- Auth screen shows only social buttons (no email form, no toggle)
- Disabling all providers in config → auth screen shows error + retry
- Edit Profile sheet shows username field with current username pre-filled
- Typing unavailable username → shows "taken" indicator
- Typing valid available username → shows green check
- Saving username change → confirmation dialog about broken links
- After save → profile shows new username, subsequent API calls use new username
- Trying to change again within 24h → 429 error with meaningful message
- Settings screen still shows username read-only
