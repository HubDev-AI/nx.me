---
title: "Account deletion: the hard-reset invariants"
module: auth
date: 2026-04-18
problem_type: best_practice
component: authentication
severity: critical
related_components:
  - database
  - background_job
  - mobile
applies_when:
  - Adding a new user-owned DB table, device key, Redis key, or blob prefix
  - Implementing or auditing the account-deletion endpoint
  - Designing soft-delete vs hard-delete strategy for user-scoped data
  - Adding admin / support tooling that terminates user accounts
symptoms:
  - Re-signup blocked after account deletion (tombstone held unique email)
  - Device onboarding skipped on re-signup due to surviving local flag
  - Blob storage orphaned after user cascade
root_cause: missing_workflow_step
resolution_type: migration
tags:
  - account-deletion
  - hard-delete
  - cascade
  - username-reservation
  - device-wipe
  - auth-delete-first
  - orphan-sweeper
  - homograph
  - nfkc
  - data-retention
related_prs:
  - "HubDev-AI/nx.me#162"
  - "HubDev-AI/nx.me#166"
related_docs:
  - docs/superpowers/specs/2026-04-18-delete-account-hard-reset-design.md
  - docs/superpowers/plans/2026-04-18-delete-account-hard-reset.md
---

# Account deletion: the hard-reset invariants

## Context

NXME.ai started with a soft-delete account model: a `deleted_at` column on
`users`, a `username_reserved_until` column, and no cascading foreign keys.
The design decision in the early auth story (Story 2-3, March 2026) kept
the user row alive as a tombstone so a 180-day username reservation could
be enforced, with "primary storage deleted asynchronously within 72 hours"
deferred as a future story (session history).

That model never delivered what users expect when they tap "Delete Account":
**nothing remains**. In practice, five surfaces leaked state:

| Surface | Leak |
|---|---|
| DB rows | 11 of 17 user-referencing FKs were `NO ACTION`. No cascade, orphaned rows. |
| Blob storage | No enumeration before delete → blobs orphaned forever. The 72-hour cleanup was never built. |
| Redis keys | Cleaned up, but `KEYS` (O(N) blocking scan) was used instead of `SCAN`. |
| Device-local | Logout only cleared tokens. `nxme_onboarding_complete` + dismissed-jobs cache + refund-toast cache + React Query cache + MMKV mutation queue all survived. |
| In-memory singletons | Module-level `cache: Set<string>` in dismissed-jobs-store / refund-toast-store persisted. |

**Triggering bug** (PR #162): a user deleted their account, then tried to
sign up with the same email → `users_email_key` UNIQUE violation because
`soft_delete` left `email` + `tiktok_open_id` on the tombstone row. Quick
fix: scrub those columns in-place. But the deeper issue was that this bug
was only the first to surface — the soft-delete model made every new
user-owned surface opt-in to cleanup, a permanent drift risk.

**What Didn't Work** (session history):

- Scrubbing just `email` + `tiktok_open_id` (PR #162) — re-signup worked, but
  `nxme_onboarding_complete` in device SecureStore still caused the new
  account to skip the onboarding screen. Five other surfaces still leaked.
- Keeping the soft-delete tombstone + relying on the CDN/async-cleanup story
  — the cleanup story was never written, and the tombstone itself was the
  source of the collision bugs.

PR #166 replaced the model entirely with a hard-delete across all five
surfaces, plus two migrations and a compensating nightly sweeper.

## Guidance — five invariants

### 1. Single-surface registry pattern

Every user-owned surface has exactly two choke points:

- **Server:** `DELETE /v1/auth/account` in `app/api/auth.py::delete_account`.
- **Client:** `mobile/lib/account-wipe.ts::wipeLocalDeviceState`.

New surfaces must be wired into one of these two. The registry is enforced
by reviewers, not by code — so it lives in project memory (auto memory
[claude]: `feedback_delete_account_scope.md`):

> When adding new user-owned state, update the delete path:
> - new FK table → `ON DELETE CASCADE` in the creating migration
> - new `SecureStore` key → `SECURE_STORE_KEYS` + `wipeLocalDeviceState`
> - new Redis pattern → Redis cleanup block in `delete_account`
> - new blob prefix → `list_user_storage_keys` + bucket constants
> - new client singleton → expose `clear()`, call from `wipeLocalDeviceState`
>
> Reviewers reject PRs that add user-owned state without touching the delete path.

### 2. Step ordering for retry-safety

The endpoint runs 7 steps in a specific order. Re-ordering is load-bearing:

```
1. Fetch user profile — missing → idempotent 204
2. Release credit reservations
3. Enumerate blob keys (paginated — BEFORE cascade kills enumeration)
4. Delete Supabase auth identity      ← FIRST. Failure = row intact, retry-safe.
5. Wipe blobs (inline ≤500; ARQ offload above; DLQ on failure)
6. DELETE FROM users                  ← Cascade + SET NULL drops/anonymizes owned data
7. Insert username_reservations row   ← ONLY if step 6 returned a row
8. Redis cleanup via `scan_iter`      ← Not `keys` (O(N) blocking)
```

Why auth-first: if step 4 fails, the user row still exists, their session
still works, they can retry. If step 4 succeeded and step 6 fails, the
row is an orphan (see invariant 3).

Why reservation after DELETE: if DELETE returns zero rows (race — user
already gone), no reservation is inserted. An orphaned reservation would
block the user's own future handle reclaim.

### 3. Compensating sweeper for partial failures

The auth-delete-succeeds-but-DB-delete-fails window is rare but unrecoverable
without compensation: auth identity gone, `public.users` row survives, user
can't log in (no auth identity), can't re-register (row still holds the
unique email, if we ever add one back).

Nightly `reconcile_orphaned_users` in `app/workers/retention.py` walks
`public.users` and deletes any row whose Supabase `auth.users` identity is
gone. Cascade chain (post-0044 + 0045) drops every owned row.

This invariant caught a P0 in code review — without the sweeper, the
earlier-discovered `reports.post_id` FK bug (see invariant 1: new FK must
be CASCADE) would have left hundreds of zombie accounts.

### 4. Two-sided normalization

Username normalization happens in two places, and both are required:

**App side** — `app/api/auth_helpers.py`:

```python
import unicodedata
from unidecode import unidecode

def normalize_username(username: str) -> str:
    """NFKC + ASCII-fold lowercase — homograph-safe availability key."""
    return unidecode(unicodedata.normalize("NFKC", username)).lower()
```

**DB side** — `app/migrations/0044_hard_delete_account.sql`:

```sql
CREATE TABLE username_reservations (
    username       TEXT PRIMARY KEY CHECK (username = lower(username)),
    reserved_until TIMESTAMPTZ NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE username_reservations ENABLE ROW LEVEL SECURITY;
CREATE POLICY username_reservations_deny_all ON username_reservations
    FOR ALL TO anon, authenticated USING (false) WITH CHECK (false);
```

App-only normalization breaks when a future path forgets to call the
helper (or a migration inserts directly). DB-only normalization breaks
when app code reads un-normalized usernames and compares. Both are load
bearing.

Normalization is applied at registration, availability check, and
reservation insert — every username write site.

### 5. Inline vs ARQ offload threshold

Synchronous blob wipe for small users (≤500 blobs). Above the threshold,
an ARQ job `wipe_deleted_user_blobs` handles it with 250-key chunks and
`asyncio.to_thread` for the sync Supabase storage calls.

Critical: ARQ dedup via `_job_id=f"delete_account:{user_id}"` returns
`None` silently if a job with the same ID was enqueued within the last
24 hours (result-key TTL). Check the return:

```python
job = await arq_pool.enqueue_job(
    "wipe_deleted_user_blobs",
    user_id=user_id,
    keys_by_bucket=keys_by_bucket,
    _job_id=f"delete_account:{user_id}",
)
if job is None:
    logger.warning(
        "delete_account: ARQ job delete_account:%s was deduped — previous snapshot will run",
        user_id,
    )
```

## Why this matters

Without these invariants, the symptoms rebuild from zero:

- **Re-signup silently broken** → tombstone holds UNIQUE email / username.
- **Blob storage leaks indefinitely** → no enumeration step before cascade.
- **Zombie accounts on partial failure** → auth gone, row alive, no sweeper.
- **Homograph attacks bypass reservation** → Cyrillic "а" ≠ Latin "a".
- **Device retains JWT after server-side deletion** → logout-only wipe.
- **Onboarding skipped on re-signup** → device flag survives deletion.

Code review (16 reviewers, ~28 merged findings) caught 3 P0 + 10 P1 issues
BEFORE merge, including:

- `reports.post_id` FK still `NO ACTION` — would block cascade mid-delete,
  leaving the account as a zombie (invariant 1 missed — triggered migration 0045).
- ARQ dedup silently dropping retries (invariant 5 incomplete).
- `Promise.all` over SecureStore deletes short-circuiting → JWT retained
  on device after first rejection (invariant 1, client side).

## When to apply

Apply the five invariants whenever designing a deletion flow for
user-scoped data in this repo:

| Scenario | Applies? |
|---|---|
| Account hard-delete (this doc) | Reference impl |
| Sub-account / linked-account deletion | Yes — same choke points |
| Data-export-then-delete | Yes — export must run BEFORE step 4 (auth delete) |
| Admin force-delete support tooling | Yes — same ordering; do NOT skip blob enumeration |
| Adding a new user-owned DB table / SecureStore key / Redis key / blob prefix / client singleton | Required edit to `delete_account` + `wipeLocalDeviceState` before PR ships |

**Out of scope** (deliberately):

- **Ada MCP tool for delete-account** — Ada is a styling advisor, not a
  general agent. She must NOT get tools for destructive account actions.
  If `compound-engineering:review:agent-native-reviewer` flags this as a
  gap, reject the finding — agent-native parity is a non-goal outside
  styling (auto memory [claude]: `feedback_ada_scope.md`).
- **CDN cache purge for `post-images` bucket** — pre-launch, the Cache-Control
  TTL gap is accepted. Revisit if / when GDPR timing becomes concrete.
- **Pre-emptive session / JWT revocation** — Supabase GoTrue revokes refresh
  tokens on `auth.admin.delete_user` (sufficient for this iteration); access
  tokens stay valid until `exp`. Accepted residual risk; client-side
  `wipeLocalDeviceState` deletes the JWT from the originating device.

## Examples

### Server: the endpoint ordering

```python
# app/api/auth.py — see the live signature for the full dependency list
@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_account(claims: UserClaims = Depends(get_current_user), ...) -> Response:
    """Ordering (do NOT re-order):
      1. Fetch the user. Missing → idempotent 204.
      2. Release active credit reservations.
      3. Enumerate owned blob keys (BEFORE CASCADE kills enumeration).
         — Re-raise on failure; do NOT swallow (would leak blobs silently).
      4. Delete Supabase auth identity FIRST — failure is retry-safe.
      5. Wipe blobs (inline ≤500, ARQ for large; DLQ on failure).
         — Check ARQ enqueue_job return; warn on dedup-drop.
      6. Hard-delete the users row — CASCADE + SET NULL fans out the rest.
      7. Insert the username reservation (ONLY if step 6 deleted a row).
      8. Redis cleanup via scan_iter (NEVER use KEYS).
    """
```

### Client: `wipeLocalDeviceState`

```typescript
// mobile/lib/account-wipe.ts
export async function wipeLocalDeviceState(): Promise<void> {
  // 1. SecureStore — per-key catch so one failure can't leave JWT on device
  await Promise.all(
    Object.values(SECURE_STORE_KEYS).map((key) =>
      deleteItem(key).catch(() => { /* log in dev; swallow in prod */ }),
    ),
  );

  // 2. Module-level caches (each owns its own @nxme:* AsyncStorage key)
  await Promise.all([clearDismissedJobs(), clearRefundToastSeen()]);

  // 3. MMKV-backed offline mutation queue (NOT reachable via AsyncStorage)
  mutationQueue.clear();

  // 4. React Query cache
  queryClient.clear();
}
```

### Delete screen: timeout-as-logout escape hatch

Full-screen overlay + `usePreventRemove` blocks navigation mid-delete.
Client-side `DELETE_ACCOUNT_TIMEOUT_MS` (60s) escape hatch — if the
server stalls, wipe local + navigate to login anyway (compensating
sweeper covers any server-side partial state):

```typescript
// mobile/app/settings.tsx
usePreventRemove(isDeleting, () => { /* rejection is the whole point */ });

// inside handleDeleteAccount onPress (abort-on-timeout race omitted for clarity):
const controller = new AbortController();
try {
  // Race the fetch against DELETE_ACCOUNT_TIMEOUT_MS; timeout → controller.abort() + reject(TIMEOUT_SENTINEL)
  await raceWithTimeout(
    apiFetch<void>(AUTH_ENDPOINTS.DELETE_ACCOUNT, { method: "DELETE", signal: controller.signal }),
    DELETE_ACCOUNT_TIMEOUT_MS,
    () => { controller.abort(); throw new Error(TIMEOUT_SENTINEL); },
  );
  await wipeLocalDeviceState();
  setSessionMode("anon");
  router.replace("/(auth)/login");
} catch (err) {
  // On timeout: still wipe + logout (prevents trapping the user behind the
  // overlay if the server is slow). Compensating sweeper reconciles.
  if (err instanceof Error && err.message === TIMEOUT_SENTINEL) {
    await wipeLocalDeviceState();
    setSessionMode("anon");
    router.replace("/(auth)/login");
    showToast({ kind: "info", message: "Deletion is taking longer than expected..." });
  } else { /* show error, setIsDeleting(false) */ }
}
```

### Pre-commit checklist for new user-owned state

From `feedback_delete_account_scope.md` (auto memory [claude]). Answer
yes to all five, or reject the PR:

1. **New DB table with `user_id` FK?** → FK is `ON DELETE CASCADE`; migration comments explain.
2. **New `SecureStore` key?** → Added to `SECURE_STORE_KEYS`; `wipeLocalDeviceState` iterates `Object.values(SECURE_STORE_KEYS)` so this is automatic.
3. **New Redis key pattern scoped to a user?** → Redis cleanup block in `delete_account` covers it (via `scan_iter`).
4. **New blob bucket or prefix?** → `list_user_storage_keys` in `user_repo.py` enumerates it; constants in `app/services/public_url.py` updated.
5. **New client singleton with persistent state?** → Exposes `clear()` method; `wipeLocalDeviceState` calls it.

## References

- **Spec:** `docs/superpowers/specs/2026-04-18-delete-account-hard-reset-design.md`
- **Plan:** `docs/superpowers/plans/2026-04-18-delete-account-hard-reset.md`
- **PR #166** (hard-delete rewrite): `https://github.com/HubDev-AI/nx.me/pull/166`
- **PR #162** (predecessor quick fix, superseded): `https://github.com/HubDev-AI/nx.me/pull/162`
- **Migrations:** `app/migrations/0044_hard_delete_account.sql`, `app/migrations/0045_delete_account_cascade_completeness.sql`
- **Endpoint:** `app/api/auth.py::delete_account`
- **Worker:** `app/workers/delete_account_blobs.py::wipe_deleted_user_blobs`, `app/workers/retention.py::reconcile_orphaned_users`, `app/workers/retention.py::purge_expired_username_reservations`
- **Client helper:** `mobile/lib/account-wipe.ts::wipeLocalDeviceState`
- **Normalization:** `app/api/auth_helpers.py::normalize_username`
- **Memory:** `feedback_delete_account_scope.md`, `feedback_ada_scope.md`, `feedback_pre_launch_destructive_ok.md`
