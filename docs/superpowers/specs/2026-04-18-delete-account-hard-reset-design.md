# Delete Account — Hard Reset Design

**Date:** 2026-04-18
**Status:** Approved (sections 1–5); amended 2026-04-18 after plan refine pass.
**Author:** brainstorm session with @trifonov

> **Amendment history**
>
> 2026-04-18 (refine): added ARQ offload for large-user blob wipe; added
> `post-images` public bucket to the wipe set; switched `reports.reporter_user_id`
> and both `blocked_users` FKs to `ON DELETE SET NULL` (preserve moderation +
> safety signal); added NFKC + ASCII-fold (`unidecode`) username normalization
> at every comparison site; added RLS deny-all on `username_reservations`;
> reordered the delete sequence to auth-delete → blobs → DB DELETE →
> reservation-only-if-rows-deleted; added a full-screen `DeleteAccountOverlay`
> + `usePreventRemove` + client-side `DELETE_ACCOUNT_TIMEOUT_MS` escape.

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
    ├── 1. Release active credit reservations               (existing)
    │
    ├── 2. Collect blob keys (paginated, BEFORE cascade)    (NEW)
    │      uploads.image_url + jobs.before/after_image_url
    │      + posts.before/after_storage_key + avatar
    │      → bucket groups: raw-selfies, generated-images,
    │                        post-images, avatars
    │
    ├── 3. auth.admin.delete_user(id)                       (REORDERED — first)
    │      On failure: 502, row intact, user can retry.
    │
    ├── 4. Storage wipe                                     (NEW)
    │      If total_blobs ≤ 500: inline image_repo.remove()
    │                            + orphan_repo DLQ on failure
    │      Else:                 enqueue ARQ wipe_deleted_user_blobs
    │                            job_id=f"delete_account:{user_id}" (dedupe)
    │
    ├── 5. DELETE FROM public.users WHERE id=:id            (CHANGED)
    │      CASCADEs most FKs; SET NULL on reports +
    │      blocked_users to preserve moderation + safety.
    │
    ├── 6. Insert username_reservations row                 (MOVED AFTER DELETE)
    │      Only if step 5 returned a row — no orphan reservations.
    │      UPSERT on lower(_normalize_username(username))
    │
    └── 7. Redis key cleanup (SCAN, not KEYS)               (existing)

Client (settings.tsx → handleDeleteAccount):
    Alert.alert(destructive confirm, hard-delete semantics copy)
      → onPress:
          setIsDeleting(true)                              // overlay shows
          Promise.race([
            apiFetch("/v1/auth/account", { method: "DELETE" }),
            timeout(DELETE_ACCOUNT_TIMEOUT_MS)             // 60s escape hatch
          ])
          await wipeLocalDeviceState()
          setSessionMode("anon")
          router.replace("/(auth)/login")

    <DeleteAccountOverlay /> full-screen while isDeleting
    usePreventRemove blocks hardware back + iOS edge-swipe
    HeaderBackButton hidden while isDeleting
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

-- 3. FK rewrites. Most tables CASCADE (their rows have no independent
--    meaning after the owning user is gone). Moderation + safety tables
--    (reports, blocked_users) SET NULL so the record survives to preserve
--    the audit trail and the blockee's safety signal.

-- CASCADE set (8 FKs):
ALTER TABLE images           DROP CONSTRAINT images_user_id_fkey,
                             ADD  CONSTRAINT images_user_id_fkey
                                  FOREIGN KEY (user_id) REFERENCES users(id)
                                  ON DELETE CASCADE;
-- …repeat for: posts, reactions, comments, shareable_cards,
--               subscriptions, credit_ledger, credit_reservations.

-- SET NULL set (3 FKs): preserve the row, drop the identity.
ALTER TABLE reports
    ALTER COLUMN reporter_user_id DROP NOT NULL,
    DROP CONSTRAINT reports_reporter_user_id_fkey,
    ADD  CONSTRAINT reports_reporter_user_id_fkey
         FOREIGN KEY (reporter_user_id) REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE blocked_users
    ALTER COLUMN blocker_id DROP NOT NULL,
    DROP CONSTRAINT blocked_users_blocker_id_fkey,
    ADD  CONSTRAINT blocked_users_blocker_id_fkey
         FOREIGN KEY (blocker_id) REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE blocked_users
    ALTER COLUMN blocked_id DROP NOT NULL,
    DROP CONSTRAINT blocked_users_blocked_id_fkey,
    ADD  CONSTRAINT blocked_users_blocked_id_fkey
         FOREIGN KEY (blocked_id) REFERENCES users(id) ON DELETE SET NULL;

-- 4. RLS: username_reservations is service-role only. Blocks an
--    authenticated user from enumerating the table and learning who
--    recently deleted an account.
ALTER TABLE username_reservations ENABLE ROW LEVEL SECURITY;
CREATE POLICY username_reservations_deny_all ON username_reservations
    FOR ALL TO anon, authenticated USING (false) WITH CHECK (false);

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

Public repo API is unchanged. Internals do two checks against the
**NFKC + ASCII-folded lowercase** normalized form of the input (via the
`_normalize_username` helper using `unicodedata.normalize("NFKC", s)` +
`unidecode(s).lower()` — add `unidecode` via `uv add unidecode`):

1. `SELECT 1 FROM users WHERE lower(username) = lower($norm)` → taken.
2. `SELECT 1 FROM username_reservations
     WHERE lower(username) = lower($norm)
       AND reserved_until > now()` → reserved.
3. Otherwise → available.

Normalization is applied at every call site (registration, availability,
reservation insert) so Cyrillic 'а', fullwidth 'ａ', and diacritics
('café') cannot bypass the reservation by masquerading as a new handle.

Both `check_username_availability` and its alias `check_username_available_ci`
(consumed by the mobile availability endpoint) must consult reservations.

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

### Blob wipe — inline vs ARQ offload

`_INLINE_BLOB_WIPE_THRESHOLD = 500` blobs:

- **≤ 500 blobs:** inline `image_repo.remove(bucket, chunk)`; failures
  per-key to the existing orphan DLQ.
- **> 500 blobs:** enqueue ARQ job `wipe_deleted_user_blobs` with
  `job_id=f"delete_account:{user_id}"` (idempotent dedupe). The worker
  chunks each bucket into 250-key batches; failed batches push every
  key to the orphan DLQ. Buckets covered: `raw-selfies`,
  `generated-images`, `post-images`, `avatars`.

The threshold keeps the HTTP handler well under the reverse-proxy timeout
for the common case; large users get a best-effort background wipe with
the same DLQ safety net.

### Delete order and recovery

The endpoint orders operations so no partial failure leaves a worse state
than "user still exists and can retry":

1. `auth.admin.delete_user` first → if it fails, DB untouched, retry OK.
2. Blob enumeration + wipe (or ARQ enqueue) → orphan blobs are safer than
   stale rows.
3. `DELETE FROM users` → CASCADE + SET NULL fan-out.
4. `insert_username_reservation` only if step 3 returned a row → no
   orphan reservations blocking the user's own handle.
5. Redis cleanup with `SCAN_ITER` (not `KEYS`) → no blocking O(N) scan.

Second call on an already-deleted user returns 204 (idempotent). No
rate-limiting, no advisory lock — double-delete work is bounded and the
orphan DLQ dedupes.

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

### Wiring + delete UX

`mobile/app/settings.tsx → handleDeleteAccount` is wrapped in a
destructive `Alert.alert` whose copy reflects hard-delete semantics
("Your photos, glow-ups, and account data will be permanently deleted.
Your username will be reserved for 180 days. This cannot be undone.").

On confirm:

```ts
setIsDeleting(true);
try {
  await Promise.race([
    apiFetch<void>("/v1/auth/account", { method: "DELETE" }),
    timeout(DELETE_ACCOUNT_TIMEOUT_MS),   // 60s — unblocks the UI on hang
  ]);
  await wipeLocalDeviceState();
  setSessionMode("anon");
  router.replace("/(auth)/login");
} catch (err) {
  // Surface a recovery message; distinguish timeout from other errors.
  setIsDeleting(false);
  showToast({ kind: "error", message: messageFor(err) });
}
```

While `isDeleting` is true:

- A full-screen `DeleteAccountOverlay` component covers the screen
  (`accessibilityViewIsModal` traps VO/TB focus, activity indicator +
  title + subtitle with `maxFontSizeMultiplier` caps).
- `usePreventRemove` (via `navigation.addListener("beforeRemove")`)
  blocks iOS edge-swipe + Android hardware back.
- `HeaderBackButton` is replaced with a spacer so the visible chrome
  cannot initiate navigation either.
- `DELETE_ACCOUNT_TIMEOUT_MS` is the escape hatch: if the server hangs,
  the overlay dismisses with a recoverable toast rather than trapping
  the user forever.

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
inline above, and the refine-pass additions (ARQ offload, SET NULL FKs,
NFKC+ASCII-fold, RLS, overlay/timeout UX) have been folded back into
the spec body.

## Residual Risks (accepted, not addressed in this iteration)

These surfaced in review but are knowingly out of scope for this change.
Called out so a future iteration can pick them up.

- **Outstanding JWT after auth-delete.** Supabase GoTrue revokes refresh
  tokens on `auth.admin.delete_user`, but access tokens stay valid until
  their `exp`. Between auth-delete and DB delete, a valid JWT could be
  replayed; the calls are ordered so the DB row cascade/set-null happens
  immediately after. Not addressed: pre-emptive session revocation.
- **post-images bucket for `shareable_cards`.** The main `posts` table's
  public copies are wiped; the `shareable_cards` URL path (separate
  artefact) still 404s via cascade but any CDN-cached public bytes may
  outlive deletion until the CDN TTL expires.
- **Username reservation PII.** The preserved handle is indirectly PII
  for 180 days. No GDPR erasure endpoint exists for the reservation
  itself.
- **Concurrent-delete race with no lock.** Accepted: double-work is
  bounded (second DELETE returns 0 rows, DLQ dedupes). If we see it in
  practice, add a Redis `SET NX` lock keyed on `user_id`.
