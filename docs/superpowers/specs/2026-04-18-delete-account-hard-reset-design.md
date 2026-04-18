# Delete Account — Hard Reset Design

**Date:** 2026-04-18
**Status:** Approved (sections 1–5)
**Author:** brainstorm session with @trifonov

## Problem

Two bugs, one root cause.

1. After deleting the account and re-signing up on the same device, the
   user lands directly on the feed — the onboarding screen never shows.
2. Even after the server-side soft-delete scrub (PR #162), the deleted
   user's DB row and owned tables linger, violating the user's "nothing
   remains" expectation.

**Root causes.**

- `nxme_onboarding_complete` is stored in device SecureStore (not
  user-scoped) and is never cleared on delete-account. The next signup
  reads the stale `true` and skips onboarding.
- `DELETE /auth/account` soft-deletes `public.users` (sets `deleted_at`,
  `username_reserved_until`). 17 tables reference `users.id`; only 6 are
  `ON DELETE CASCADE`. The other 11 (`images`, `posts`, `reactions`,
  `comments`, `shareable_cards`, `subscriptions`, `credit_ledger`,
  `credit_reservations`, `reports`, `blocked_users × 2`) hold stale
  rows indefinitely. Blobs in object storage are never deleted
  (the 72-hour async cleanup was deferred and never built).

## Goal

Delete-account produces a clean slate across **every** surface that
holds user-owned state — DB rows, object-storage blobs, Redis keys,
device-local storage, in-memory singletons, React Query cache — with
one carve-out: a 180-day username reservation so nobody can impersonate
a freshly-deleted user.

## Non-Goals

- Changing logout behavior. Logout stays narrow (`clearAllTokens` +
  `setSessionMode("anon")`) — it is not an account-wipe event.
- GDPR export / anonymized retention. Pre-launch; no legal hold yet.
- Shareable-card HTTP 410 semantics. Post-hard-delete, the natural 404
  is sufficient.

## Architecture

```
DELETE /v1/auth/account
    │
    ├── 1. Release active credit reservations           (existing)
    │
    ├── 2. Collect blob storage keys                    (NEW)
    │      uploads.storage_key + glowup outputs + avatar
    │
    ├── 3. Insert username_reservations row             (NEW)
    │      (username, reserved_until = now+180d)
    │      ON CONFLICT (username) DO UPDATE
    │        SET reserved_until = EXCLUDED.reserved_until
    │
    ├── 4. Storage wipe                                 (NEW — inline)
    │      image_repo.remove(bucket, keys)
    │      on failure → orphan_repo.enqueue_many(…)     (DLQ fallback)
    │
    ├── 5. DELETE FROM public.users WHERE id=:id        (CHANGED)
    │      CASCADEs to every user-owned table
    │
    ├── 6. auth.admin.delete_user(id)                   (existing)
    │
    └── 7. Redis key cleanup                            (existing)

Client (settings.tsx → handleDeleteAccount):
    await apiFetch("/v1/auth/account", { method: "DELETE" })
    await wipeLocalDeviceState()                         (NEW)
    setSessionMode("anon")
    router.replace("/(auth)/login")
```

## Backend

### Migration `00NN_hard_delete_account.sql`

```sql
BEGIN;

-- 1. Reservation table
CREATE TABLE username_reservations (
    username       TEXT PRIMARY KEY,
    reserved_until TIMESTAMPTZ NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_username_reservations_expiry
    ON username_reservations(reserved_until);
-- Case-insensitive uniqueness matches users.username semantics.
CREATE UNIQUE INDEX idx_username_reservations_username_lower
    ON username_reservations (lower(username));

-- 2. Drop soft-delete columns
ALTER TABLE users
    DROP COLUMN deleted_at,
    DROP COLUMN username_reserved_until;

-- 3. Switch 11 FKs to ON DELETE CASCADE
ALTER TABLE images           DROP CONSTRAINT images_user_id_fkey,
                             ADD  CONSTRAINT images_user_id_fkey
                                  FOREIGN KEY (user_id) REFERENCES users(id)
                                  ON DELETE CASCADE;
-- …repeat for: posts, reactions, comments, shareable_cards,
--               subscriptions, credit_ledger, credit_reservations,
--               reports, blocked_users (blocker_id AND blocked_id).

COMMIT;
```

Pre-launch destructive OK (per `feedback_pre_launch_destructive_ok`):
wipe local DB with `make nuke` before applying; no backfill needed.

### `delete_account` endpoint

Rewritten to the 7-step order above. Key changes:

- Collect blob keys **before** the DB delete. Once cascades fire, we
  cannot enumerate them.
- Blob wipe is inline with a DLQ fallback via
  `orphaned_storage_repo.enqueue_many(bucket, keys)`.
- `user_repo.soft_delete` is deleted. Replace with `user_repo.delete`
  (single DELETE, no `deleted_at` guard).
- `user_repo.insert_username_reservation(username, reserved_until)`:
  UPSERT on `lower(username)` so a re-delete of the same username
  extends the window rather than erroring.

### `check_username_availability` semantics

Public repo API is unchanged. Internals do two checks:

1. `SELECT 1 FROM users WHERE lower(username) = lower($1)` → taken.
2. `SELECT 1 FROM username_reservations
     WHERE lower(username) = lower($1)
       AND reserved_until > now()` → reserved.
3. Otherwise → available.

A single SQL with `UNION ALL`+`LIMIT 1` is fine; prefer that over two
round-trips.

### Reservation hygiene

Nightly cron (add to `app/workers/retention.py`):

```python
supabase.table("username_reservations") \
    .delete() \
    .lt("reserved_until", datetime.now(tz=UTC).isoformat()) \
    .execute()
```

Not required for correctness — the availability check already ignores
expired rows — but keeps the table bounded.

### Code cleanup (no tombstone anymore)

Remove every `is_("deleted_at", "null")` guard across repos:

- `app/repositories/user_repo.py` (~8 sites)
- `app/repositories/post_repo.py`, `feed_repo.py` (any filter of this
  shape)
- Shareable-card HTTP 410 branch in `app/api/public.py` → drop; a hard
  DELETE makes the route a natural 404.
- Drop `user_repo.soft_delete` + the `tests/test_user_repo_soft_delete.py`
  suite shipped in PR #162.
- Drop `users.username_reserved_until` references everywhere.

## Mobile

### `wipeLocalDeviceState` (new — `mobile/lib/account-wipe.ts`)

```ts
export async function wipeLocalDeviceState(): Promise<void> {
  // 1. SecureStore — every nxme_* key
  await Promise.all([
    deleteItem(SECURE_STORE_KEYS.JWT),
    deleteItem(SECURE_STORE_KEYS.REFRESH_TOKEN),
    deleteItem(SECURE_STORE_KEYS.GUEST_TOKEN),
    deleteItem(SECURE_STORE_KEYS.PENDING_EMAIL_VERIFICATION),
    deleteItem(SECURE_STORE_KEYS.GUEST_PURGED_AT),
    deleteItem(SECURE_STORE_KEYS.ONBOARDING_COMPLETE),
    deleteItem(SECURE_STORE_KEYS.USERNAME),
  ]);

  // 2. AsyncStorage — every @nxme:* key
  await AsyncStorage.multiRemove([
    PROFILE_DISMISSED_ERRORED_JOBS_STORAGE_KEY,
    REFUND_TOAST_SEEN_STORAGE_KEY,
  ]);

  // 3. In-memory singletons
  dismissedJobsStore.clear();
  refundToastStore.clear();
  offlineQueue.clear();

  // 4. React Query cache
  queryClient.clear();
}
```

### Constants promotion

Move previously inline keys into `mobile/constants/config.ts`:

- `"nxme_onboarding_complete"` → `SECURE_STORE_KEYS.ONBOARDING_COMPLETE`
- `"nxme_username"` → `SECURE_STORE_KEYS.USERNAME`

All call sites use the constant. This makes the "did a reviewer
remember to update `wipeLocalDeviceState`?" check a trivial grep over
`SECURE_STORE_KEYS` definitions.

### Wiring

`mobile/app/settings.tsx → handleDeleteAccount`:

```ts
await apiFetch<void>("/v1/auth/account", { method: "DELETE" });
await wipeLocalDeviceState();
setSessionMode("anon");
router.replace("/(auth)/login");
```

Logout path (`handleLogout` etc.) is **not** modified.

## Durable Rule

Every new user-owned surface (DB table with `user_id`, SecureStore /
AsyncStorage key, Redis key pattern, storage bucket prefix, client
singleton) must be wired into the delete-account flow at the moment it
is added:

- New FK table → `ON DELETE CASCADE` in the creating migration.
- New device key → listed in `SECURE_STORE_KEYS` / async-storage keys
  block **and** in `wipeLocalDeviceState`.
- New Redis key pattern → added to the Redis cleanup block in
  `delete_account`.
- New blob prefix → added to the inline blob-wipe step.
- New client singleton with state → exposes `clear()` and is called
  from `wipeLocalDeviceState`.

Reviewers reject PRs that add user-owned state without touching the
delete path. This rule is also stored in project memory
(`feedback_delete_account_scope.md`).

## Testing

```
Backend
├── migration unit test
│   └── username_reservations exists + 11 FKs are ON DELETE CASCADE
├── delete_account integration test (in-process, MockSupabase)
│   ├── inserts username_reservations row with reserved_until ≈ now+180d
│   ├── calls image_repo.remove with collected blob keys
│   ├── DELETE users → cascade rows gone
│   ├── Redis keys cleaned
│   └── re-signup with same email succeeds (new users row)
├── delete_account idempotency
│   └── second call on already-deleted user → 404
├── check_username_availability
│   ├── name in users → unavailable
│   ├── name in reservations within window → unavailable
│   ├── name with expired reservation → available
│   └── case-insensitive match across both tables
└── reservation cleanup cron
    └── deletes rows where reserved_until < now()

Mobile
├── wipeLocalDeviceState unit test
│   ├── every SECURE_STORE_KEYS value deleted
│   ├── every @nxme:* key deleted
│   ├── dismissedJobsStore.clear / refundToastStore.clear /
│   │   offlineQueue.clear called
│   └── queryClient.clear called
├── handleDeleteAccount test
│   └── after 204, wipeLocalDeviceState called exactly once before
│       setSessionMode
└── Maestro flow
    └── delete-account → login again (same device) → onboarding visible
```

## Out of Scope

- Device-independent wipe (e.g., logging the deleted user out of
  sessions on other devices they were signed into). Supabase auth
  revokes refresh tokens on `auth.admin.delete_user`, which is
  sufficient.
- "Undo delete" / grace period. Pre-launch; not worth the complexity.
- Analytics event retention policy (usage_events already CASCADEs).

## Open Questions

None. Every branch surfaced during the brainstorming pass is resolved
inline above.
