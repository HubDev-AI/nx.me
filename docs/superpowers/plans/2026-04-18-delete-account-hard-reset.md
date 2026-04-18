# Delete Account — Hard Reset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current soft-delete account flow with a hard-delete that wipes every user-owned surface (DB rows, blobs including public CDN, Redis keys, device-local storage, in-memory singletons, React Query cache), while preserving a 180-day username reservation in a dedicated RLS-locked table. Moderation + safety records (reports, blocked_users) are preserved via SET NULL on the deleted-user side rather than CASCADE.

**Architecture:** One migration creates a `username_reservations` table (with RLS deny-all), drops `users.deleted_at` + `users.username_reserved_until` after dropping their dependents (RLS policy, v_feed_posts view, partial index), and rewrites user-referencing FKs. Most FKs switch to `ON DELETE CASCADE`; `reports.reporter_user_id` and both `blocked_users` columns switch to `ON DELETE SET NULL` (columns made nullable) to preserve moderation audit trails and safety signals. The `DELETE /v1/auth/account` endpoint is rewritten with auth-delete first (so a failure leaves the row intact and the user can retry), then blob-wipe, then `DELETE FROM users` (cascade/set-null), then reservation insert (only if the DELETE returned a row), then Redis cleanup. Large users (>500 blobs) offload the blob wipe to an ARQ job so the HTTP request stays synchronous. Username lookups everywhere (users + reservations) normalize via NFKC + ASCII-fold. Client adds a `wipeLocalDeviceState` helper and a full-screen deleting overlay with back-navigation blocked via `usePreventRemove`.

**Tech Stack:** Python 3.12, FastAPI, Supabase (Postgres via supabase-py + PostgREST), ARQ, pytest. Mobile: TypeScript, React Native, Expo, expo-secure-store, @react-native-async-storage/async-storage, @tanstack/react-query, Maestro.

**Branch:** `feat/delete-account-hard-reset`

**Pre-flight (run once, before Task 1):**

```bash
git checkout dev
git pull origin dev
git checkout -b feat/delete-account-hard-reset
make nuke    # pre-launch: wipe local DB so drop-column + FK changes have no stale rows to worry about
```

Add the reservation-window setting to `app/config/__init__.py`:

```python
# In the Settings class, alongside existing username/auth tunables:
USERNAME_RESERVATION_DAYS: int = 180
```

And to `app/.env.example`:

```
# Days a username is held after an account is hard-deleted (blocks re-registration under the same handle).
USERNAME_RESERVATION_DAYS=180
```

Commit as a discrete prep:

```bash
git add app/config/__init__.py app/.env.example
git commit -m "chore(config): USERNAME_RESERVATION_DAYS setting"
```

---

## File Structure

**Backend:**
- Create `app/migrations/0044_hard_delete_account.sql` — reservations table, drop soft-delete columns (after dropping the view + RLS policy + partial index that depend on `users.deleted_at`), CASCADE the FKs still on `NO ACTION`.
- Modify `app/repositories/user_repo.py` — remove `soft_delete`, add `delete`, add `list_user_storage_keys`, add `insert_username_reservation`, update `check_username_availability` + `check_username_available_ci` to consult reservations, drop `deleted_at` / `username_reserved_until` from all `select(...)` lists, drop `.is_("deleted_at", "null")` filters in `get_profile_by_id` + `get_by_username_for_card`.
- Modify `app/api/auth.py` — rewrite `delete_account`; drop every `users.deleted_at` + `username_reserved_until` reference (including the registration-path dict inspection around line 266-282).
- Modify `app/repositories/feed_repo.py`, `app/repositories/post_repo.py` — drop `is_("deleted_at", "null")` guards.
- Modify `app/entitlement/service.py` — drop the two `.is_("deleted_at", "null")` sites.
- Modify `app/api/public.py` — drop BOTH shareable-card HTTP 410 branches and every `user.get("deleted_at")` check.
- Modify `app/workers/retention.py` — add nightly reservation cleanup.
- Modify `tests/test_public.py` — drop `deleted_at` keys from user fixtures.
- Delete `tests/test_user_repo_soft_delete.py` if it exists in the working branch — method is gone.
- Create `tests/test_hard_delete_account.py`, `tests/test_username_availability_with_reservations.py`, `tests/test_retention_reservation_cleanup.py`, `tests/test_migration_0044_hard_delete.py`.

**Mobile:**
- Modify `mobile/constants/config.ts` — add `ONBOARDING_COMPLETE` and `USERNAME` to `SECURE_STORE_KEYS`.
- Modify `mobile/app/_layout.tsx`, `mobile/app/onboarding.tsx`, `mobile/lib/auth-context.tsx` — reference the new constants.
- Create `mobile/lib/account-wipe.ts` — `wipeLocalDeviceState`.
- Create `mobile/lib/__tests__/account-wipe.test.ts`.
- Modify `mobile/app/settings.tsx` — wire `wipeLocalDeviceState` into `handleDeleteAccount`.
- Create `mobile/.maestro/flows/40-delete-and-resignup-onboarding.yaml`.

---

## Task 1: Migration — reservations table, drop soft-delete columns, CASCADE 11 FKs

**Files:**
- Create: `app/migrations/0044_hard_delete_account.sql`

- [ ] **Step 1: Write the migration**

Create `app/migrations/0044_hard_delete_account.sql`:

```sql
-- 0044_hard_delete_account.sql
--
-- Switches delete-account from soft-delete (tombstone + reservation column on
-- users) to hard-delete with a dedicated reservations table. All 11 FKs that
-- were ON DELETE NO ACTION are switched to ON DELETE CASCADE so a single
-- DELETE FROM users cascades the lot.
--
-- Pre-launch: destructive OK. No backfill. Local DB wiped via `make nuke`
-- before apply.

BEGIN;

-- 0. Drop dependents of users.deleted_at before DROP COLUMN can succeed.
--    Migration 0028 created `users_public_read` RLS policy + `v_feed_posts`
--    view filtering on `deleted_at IS NULL`; migration 0005 created a partial
--    index `idx_users_username_reserved` on (username, deleted_at,
--    username_reserved_until). All three must be dropped first.
DROP POLICY IF EXISTS users_public_read ON users;
DROP VIEW IF EXISTS v_feed_posts CASCADE;  -- feed_trending / feed_newest / feed_biggest_improvements recreate below
DROP INDEX IF EXISTS idx_users_username_reserved;

-- 1. Reservation table
CREATE TABLE username_reservations (
    username       TEXT PRIMARY KEY,
    reserved_until TIMESTAMPTZ NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_username_reservations_expiry
    ON username_reservations (reserved_until);

-- Case-insensitive uniqueness matches users.username availability semantics.
CREATE UNIQUE INDEX idx_username_reservations_username_lower
    ON username_reservations (lower(username));

-- 2. Drop soft-delete columns from users
ALTER TABLE users
    DROP COLUMN deleted_at,
    DROP COLUMN username_reserved_until;

-- 3. Switch 11 FK constraints to ON DELETE CASCADE.
ALTER TABLE images
    DROP CONSTRAINT images_user_id_fkey,
    ADD  CONSTRAINT images_user_id_fkey
         FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE credit_reservations
    DROP CONSTRAINT credit_reservations_user_id_fkey,
    ADD  CONSTRAINT credit_reservations_user_id_fkey
         FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE credit_ledger
    DROP CONSTRAINT credit_ledger_user_id_fkey,
    ADD  CONSTRAINT credit_ledger_user_id_fkey
         FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE subscriptions
    DROP CONSTRAINT subscriptions_user_id_fkey,
    ADD  CONSTRAINT subscriptions_user_id_fkey
         FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE posts
    DROP CONSTRAINT posts_user_id_fkey,
    ADD  CONSTRAINT posts_user_id_fkey
         FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE reactions
    DROP CONSTRAINT reactions_user_id_fkey,
    ADD  CONSTRAINT reactions_user_id_fkey
         FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE comments
    DROP CONSTRAINT comments_user_id_fkey,
    ADD  CONSTRAINT comments_user_id_fkey
         FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE shareable_cards
    DROP CONSTRAINT shareable_cards_user_id_fkey,
    ADD  CONSTRAINT shareable_cards_user_id_fkey
         FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

-- Moderation + safety: SET NULL (preserve the record, drop the identity)
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

-- RLS: username_reservations is service-role only. Deny all reads from
-- anon/authenticated to prevent a "who recently deleted an account" oracle.
ALTER TABLE username_reservations ENABLE ROW LEVEL SECURITY;
CREATE POLICY username_reservations_deny_all ON username_reservations
    FOR ALL TO anon, authenticated USING (false) WITH CHECK (false);

-- 4. Recreate the RLS policy + feed view WITHOUT the deleted_at filter.
--    Post-hard-delete, the row is gone — no need for a tombstone check.
CREATE POLICY users_public_read ON users
    FOR SELECT TO anon, authenticated USING (true);

-- Re-create v_feed_posts (copy of the 0028 definition with the
--   `AND u.deleted_at IS NULL` clause removed). If the 0028 view body
--   has diverged, run `\d+ v_feed_posts` before the migration to capture
--   the current definition, and drop `AND u.deleted_at IS NULL` only.
CREATE OR REPLACE VIEW v_feed_posts AS
    SELECT p.*, u.username, u.display_name, u.avatar_storage_key
      FROM posts p
      JOIN users u ON u.id = p.user_id
     WHERE p.published_at IS NOT NULL;

COMMIT;
```

> Cross-check the view body against the live DB before committing
> (`\d+ v_feed_posts` in `psql`). The shape above is the 0028 definition
> minus the `AND u.deleted_at IS NULL` clause; if later migrations widened
> the projection, copy that wider shape and only drop the `deleted_at`
> predicate.

> Verify the exact constraint names before running by inspecting the live DB:
> `\d images` (etc.) in `psql`. PostgREST / Supabase sometimes uses a different
> suffix than `_user_id_fkey`. If names differ, adjust the `DROP CONSTRAINT`
> lines in this file only — do not invent a new migration.

- [ ] **Step 2: Apply the migration**

```bash
make migrate
```

Expected: the runner prints `Applied migration 0044_hard_delete_account.sql`. No errors.

- [ ] **Step 3: Verify via psql**

```bash
rtk proxy docker exec -i supabase_db_nxme.ai psql -U postgres -d postgres -c \
  "SELECT conrelid::regclass AS table_name,
          CASE confdeltype WHEN 'c' THEN 'CASCADE' ELSE confdeltype::text END AS on_delete
     FROM pg_constraint
    WHERE contype='f' AND confrelid='public.users'::regclass
    ORDER BY 1;"
```

Expected: every row shows `on_delete = CASCADE`.

```bash
rtk proxy docker exec -i supabase_db_nxme.ai psql -U postgres -d postgres -c \
  "\d username_reservations"
```

Expected: table exists with three columns (`username`, `reserved_until`, `created_at`) and both indexes.

```bash
rtk proxy docker exec -i supabase_db_nxme.ai psql -U postgres -d postgres -c \
  "SELECT column_name FROM information_schema.columns
    WHERE table_name='users'
      AND column_name IN ('deleted_at','username_reserved_until');"
```

Expected: 0 rows.

- [ ] **Step 4: Commit**

```bash
git add app/migrations/0044_hard_delete_account.sql
git commit -m "feat(db): migration 0044 — hard-delete account (CASCADE + reservations)"
```

---

## Task 2: `UserRepository` — `insert_username_reservation` + `check_username_availability` consulting reservations

**Files:**
- Modify: `app/repositories/user_repo.py`
- Test: `tests/test_username_availability_with_reservations.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_username_availability_with_reservations.py`:

```python
"""Username availability must consult both users + username_reservations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.repositories.user_repo import UserRepository


def _make_sb_with_tables(
    users_rows: list[dict] | None = None,
    reservations_rows: list[dict] | None = None,
):
    """Return a MagicMock supabase that serves different rows per table name."""
    sb = MagicMock()

    def fake_table(name: str):
        qb = MagicMock()
        qb.select.return_value = qb
        qb.eq.return_value = qb
        qb.ilike.return_value = qb
        qb.gt.return_value = qb
        if name == "users":
            qb.execute.return_value = MagicMock(data=users_rows or [])
        elif name == "username_reservations":
            qb.execute.return_value = MagicMock(data=reservations_rows or [])
        else:
            qb.execute.return_value = MagicMock(data=[])
        return qb

    sb.table.side_effect = fake_table
    return sb


class TestCheckUsernameAvailability:
    def test_name_in_users_is_taken(self):
        sb = _make_sb_with_tables(users_rows=[{"id": "u-1", "username": "alice"}])
        repo = UserRepository(sb)
        result = repo.check_username_availability("alice")
        assert result == {"available": False, "reason": "taken"}

    def test_active_reservation_is_reserved(self):
        future = (datetime.now(tz=timezone.utc) + timedelta(days=30)).isoformat()
        sb = _make_sb_with_tables(
            users_rows=[],
            reservations_rows=[
                {"username": "alice", "reserved_until": future},
            ],
        )
        repo = UserRepository(sb)
        result = repo.check_username_availability("alice")
        assert result == {"available": False, "reason": "reserved"}

    def test_expired_reservation_is_available(self):
        # repo query filters `reserved_until > now()` server-side, so an
        # expired row never reaches the caller — simulate by returning [].
        sb = _make_sb_with_tables(users_rows=[], reservations_rows=[])
        repo = UserRepository(sb)
        result = repo.check_username_availability("alice")
        assert result == {"available": True}

    def test_name_absent_everywhere_is_available(self):
        sb = _make_sb_with_tables(users_rows=[], reservations_rows=[])
        repo = UserRepository(sb)
        result = repo.check_username_availability("alice")
        assert result == {"available": True}


class TestInsertUsernameReservation:
    def test_upserts_row_with_reserved_until(self):
        captured: list[dict] = []

        def fake_upsert(payload, **kwargs):
            captured.append(payload)
            chain = MagicMock()
            chain.execute.return_value = MagicMock(data=[payload])
            return chain

        sb = MagicMock()
        table = MagicMock()
        table.upsert.side_effect = fake_upsert
        sb.table.return_value = table
        repo = UserRepository(sb)

        reserved_until = datetime.now(tz=timezone.utc) + timedelta(days=180)
        repo.insert_username_reservation("alice", reserved_until)

        assert len(captured) == 1
        assert captured[0]["username"] == "alice"
        assert captured[0]["reserved_until"] == reserved_until.isoformat()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest -x -q tests/test_username_availability_with_reservations.py
```

Expected: FAIL with `AttributeError: ... has no attribute 'insert_username_reservation'` or `AssertionError` because current implementation only consults `users`.

- [ ] **Step 3: Implement**

First, add the normalization helper at the top of
`app/repositories/user_repo.py` (importing from the shared module defined
in Task 4's endpoint):

```python
from app.api.auth import _normalize_username
```

Replace BOTH `check_username_availability` AND `check_username_available_ci`
in `app/repositories/user_repo.py` so every caller (registration path,
mobile availability endpoint) consults reservations. Both methods also
normalize via NFKC + ASCII-fold so homographs can't bypass the
reservation. Also add `insert_username_reservation`:

```python
def check_username_availability(
    self, username: str, exclude_user_id: str | None = None
) -> dict:
    """Return { available: bool, reason?: str }.

    Checks (in order): active users, then active username_reservations.
    Normalizes via NFKC + ASCII-fold so homographs collide.
    """
    from datetime import timezone

    normalized = _normalize_username(username)

    users_result = (
        self._sb.table("users")
        .select("id, username")
        .ilike("username", normalized)
        .execute()
    )
    for row in users_result.data or []:
        if exclude_user_id and row["id"] == exclude_user_id:
            continue
        return {"available": False, "reason": "taken"}

    now_iso = datetime.now(tz=timezone.utc).isoformat()
    reservations_result = (
        self._sb.table("username_reservations")
        .select("username, reserved_until")
        .ilike("username", normalized)
        .gt("reserved_until", now_iso)
        .execute()
    )
    if reservations_result.data:
        return {"available": False, "reason": "reserved"}

    return {"available": True}


# check_username_available_ci previously duplicated the logic with a
# case-insensitive ilike. Post-normalization, both methods produce the
# same result for any input — keep as a thin alias so existing mobile
# callers don't break.
check_username_available_ci = check_username_availability


def insert_username_reservation(
    self, username: str, reserved_until: datetime
) -> None:
    """UPSERT a normalized reservation row, extending the window on conflict."""
    (
        self._sb.table("username_reservations")
        .upsert(
            {
                "username": _normalize_username(username),
                "reserved_until": reserved_until.isoformat(),
            },
            on_conflict="username",
        )
        .execute()
    )
```

Delete the now-obsolete `soft_delete` method from the same file.

Also update the registration path in `app/api/auth.py` (around line
266-282) that consumes `check_username_availability` — it currently
inspects `row.get("deleted_at")` / `row.get("username_reserved_until")`.
Replace that branch with the new return shape:

```python
# Before: inspected deleted_at / username_reserved_until on the returned row
# After:
result = await run_sync(user_repo.check_username_availability, body.username)
if not result["available"]:
    reason = result.get("reason", "taken")
    if reason == "reserved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username is reserved from a recent account deletion.",
        )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Username is taken.",
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest -x -q tests/test_username_availability_with_reservations.py
```

Expected: 5 passed.

- [ ] **Step 5: Delete the stale soft-delete test file (if present)**

```bash
if [ -f tests/test_user_repo_soft_delete.py ]; then
  git rm tests/test_user_repo_soft_delete.py
fi
```

The file shipped in PR #162 and may or may not be on the working branch.

- [ ] **Step 6: Commit**

```bash
git add app/repositories/user_repo.py tests/test_username_availability_with_reservations.py
git commit -m "feat(users): username reservations repo (availability + insert)"
```

---

## Task 3: `UserRepository` — `list_user_storage_keys` and `delete`

**Files:**
- Modify: `app/repositories/user_repo.py`
- Test: `tests/test_user_repo_hard_delete.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_user_repo_hard_delete.py`:

```python
"""Hard-delete user repository primitives."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.repositories.user_repo import UserRepository


def _build_sb_serving(
    *,
    uploads: list[dict] | None = None,
    jobs: list[dict] | None = None,
    users: list[dict] | None = None,
):
    deletes: list[str] = []

    def fake_table(name: str):
        qb = MagicMock()
        qb.select.return_value = qb
        qb.eq.return_value = qb
        if name == "uploads":
            qb.execute.return_value = MagicMock(data=uploads or [])
        elif name == "jobs":
            qb.execute.return_value = MagicMock(data=jobs or [])
        elif name == "users":
            qb.execute.return_value = MagicMock(data=users or [])

            def fake_delete():
                deletes.append("users")
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.execute.return_value = MagicMock(data=users or [])
                return chain

            qb.delete.side_effect = fake_delete
        else:
            qb.execute.return_value = MagicMock(data=[])
        return qb

    sb = MagicMock()
    sb.table.side_effect = fake_table
    return sb, deletes


class TestListUserStorageKeys:
    def test_groups_keys_by_bucket(self):
        sb, _ = _build_sb_serving(
            uploads=[
                {"image_url": "users/u-1/raw/a.jpg"},
                {"image_url": "users/u-1/raw/b.jpg"},
            ],
            jobs=[
                {
                    "before_image_url": "users/u-1/before.jpg",
                    "after_image_url": "users/u-1/after.jpg",
                }
            ],
            users=[{"avatar_storage_key": "avatars/u-1/v1.jpg"}],
        )
        repo = UserRepository(sb)
        result = repo.list_user_storage_keys("u-1")

        # raw-selfies bucket: uploads + jobs.before_image_url
        assert set(result["raw-selfies"]) == {
            "users/u-1/raw/a.jpg",
            "users/u-1/raw/b.jpg",
            "users/u-1/before.jpg",
        }
        # generated-images bucket: jobs.after_image_url
        assert result["generated-images"] == ["users/u-1/after.jpg"]
        assert result["avatars"] == ["avatars/u-1/v1.jpg"]

    def test_ignores_missing_urls(self):
        sb, _ = _build_sb_serving(
            uploads=[{"image_url": None}, {"image_url": "users/u-1/raw/c.jpg"}],
            jobs=[{"before_image_url": None, "after_image_url": None}],
            users=[{"avatar_storage_key": None}],
        )
        repo = UserRepository(sb)
        result = repo.list_user_storage_keys("u-1")

        assert result["raw-selfies"] == ["users/u-1/raw/c.jpg"]
        assert result["generated-images"] == []
        assert result["avatars"] == []

    def test_dedupes_before_image_against_upload_key(self):
        shared_key = "users/u-1/raw/a.jpg"
        sb, _ = _build_sb_serving(
            uploads=[{"image_url": shared_key}],
            jobs=[{"before_image_url": shared_key, "after_image_url": None}],
            users=[{"avatar_storage_key": None}],
        )
        repo = UserRepository(sb)
        result = repo.list_user_storage_keys("u-1")
        assert result["raw-selfies"] == [shared_key]


class TestUserRepoDelete:
    def test_returns_deleted_row_on_success(self):
        sb, deletes = _build_sb_serving(users=[{"id": "u-1"}])
        repo = UserRepository(sb)
        result = repo.delete("u-1")
        assert result == [{"id": "u-1"}]
        assert deletes == ["users"]

    def test_returns_empty_when_already_gone(self):
        sb, _ = _build_sb_serving(users=[])
        repo = UserRepository(sb)
        result = repo.delete("u-1")
        assert result == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest -x -q tests/test_user_repo_hard_delete.py
```

Expected: FAIL with `AttributeError: 'UserRepository' object has no attribute 'list_user_storage_keys'`.

- [ ] **Step 3: Implement**

Add the two methods to `app/repositories/user_repo.py`:

```python
_PAGINATION_PAGE_SIZE = 1000


def list_user_storage_keys(self, user_id: str) -> dict[str, list[str]]:
    """Group every blob this user owns by bucket name.

    Called before the DB hard-delete so the keys can be enumerated while
    the owning rows still exist. Any row with a null URL is skipped.
    Queries paginate in pages of ``_PAGINATION_PAGE_SIZE`` so a user with
    100k+ uploads does not OOM the process.

    Buckets returned:
      ``raw-selfies``      — uploads.image_url + jobs.before_image_url
      ``generated-images`` — jobs.after_image_url
      ``post-images``      — posts.before_storage_key + posts.after_storage_key
                             (public CDN copies from publication)
      ``avatars``          — users.avatar_storage_key
    """
    raw_selfies: list[str] = []
    generated_images: list[str] = []
    post_images: list[str] = []

    # uploads.image_url
    for page in self._paginate("uploads", "image_url", user_id):
        raw_selfies.extend(r["image_url"] for r in page if r.get("image_url"))

    # jobs.before_image_url / after_image_url
    for page in self._paginate("jobs", "before_image_url, after_image_url", user_id):
        for row in page:
            if row.get("before_image_url"):
                raw_selfies.append(row["before_image_url"])
            if row.get("after_image_url"):
                generated_images.append(row["after_image_url"])

    # posts — published-post CDN copies. Column names are best-guess; verify
    # via psql before implementing (Step 5 covers this).
    for page in self._paginate(
        "posts", "before_storage_key, after_storage_key", user_id
    ):
        for row in page:
            if row.get("before_storage_key"):
                post_images.append(row["before_storage_key"])
            if row.get("after_storage_key"):
                post_images.append(row["after_storage_key"])

    user = (
        self._sb.table("users")
        .select("avatar_storage_key")
        .eq("id", user_id)
        .execute()
    )
    avatars = [
        r["avatar_storage_key"]
        for r in (user.data or [])
        if r.get("avatar_storage_key")
    ]

    # Dedupe raw-selfies: the same key can appear in both uploads.image_url
    # and jobs.before_image_url (worker copies the raw reference).
    return {
        "raw-selfies": list(dict.fromkeys(raw_selfies)),
        "generated-images": list(dict.fromkeys(generated_images)),
        "post-images": list(dict.fromkeys(post_images)),
        "avatars": avatars,
    }


def _paginate(self, table: str, columns: str, user_id: str):
    """Yield rows from ``table`` scoped to ``user_id`` in pages of
    ``_PAGINATION_PAGE_SIZE``. Generator so callers stream the result.
    """
    offset = 0
    while True:
        result = (
            self._sb.table(table)
            .select(columns)
            .eq("user_id", user_id)
            .range(offset, offset + _PAGINATION_PAGE_SIZE - 1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return
        yield rows
        if len(rows) < _PAGINATION_PAGE_SIZE:
            return
        offset += _PAGINATION_PAGE_SIZE


def delete(self, user_id: str) -> list[dict]:
    """Hard-delete the user row. Cascading FKs drop all owned rows.

    Returns the deleted rows (empty if the user was already gone —
    callers treat that as idempotent success).
    """
    result = (
        self._sb.table("users").delete().eq("id", user_id).execute()
    )
    return result.data or []
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest -x -q tests/test_user_repo_hard_delete.py
```

Expected: 4 passed.

- [ ] **Step 5: Verify storage-key schema assumptions against the live DB**

```bash
rtk proxy docker exec -i supabase_db_nxme.ai psql -U postgres -d postgres -c \
  "SELECT table_name, column_name FROM information_schema.columns
    WHERE table_name IN ('uploads','jobs','users','posts')
      AND column_name IN (
        'image_url','before_image_url','after_image_url',
        'avatar_storage_key','before_storage_key','after_storage_key',
        'before_url','after_url'
      )
    ORDER BY table_name, column_name;"
```

Expected columns: `uploads.image_url`, `jobs.before_image_url`, `jobs.after_image_url`, `users.avatar_storage_key`, and a pair on `posts` that store the public CDN copies. The exact column names on `posts` may be `before_storage_key`/`after_storage_key` or `before_url`/`after_url` — adjust `list_user_storage_keys` + the test to match whatever the schema actually names them.

If the `posts` table stores only `share_hash` / URLs without explicit
storage-key columns, derive the bucket keys via the naming convention used
at publish time (`rtk grep "post-images" app` to find the upload site).

- [ ] **Step 6: Commit**

```bash
git add app/repositories/user_repo.py tests/test_user_repo_hard_delete.py
git commit -m "feat(users): hard-delete + list_user_storage_keys"
```

---

## Task 4: Rewrite `delete_account` endpoint

**Files:**
- Modify: `app/api/auth.py:1294-1397` (the `delete_account` block)
- Test: `tests/test_hard_delete_account.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_hard_delete_account.py`:

```python
"""delete_account endpoint (hard-delete flow).

Covers: reservation insertion, blob wipe (success + DLQ fallback),
DB delete, auth delete, Redis cleanup, idempotency.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status

from tests.conftest import requires_routers


@requires_routers
class TestDeleteAccount:
    def _make_user_repo(self, *, user_exists: bool = True):
        repo = MagicMock()
        repo.get_profile_by_id.return_value = (
            {"id": "u-1", "username": "alice"} if user_exists else None
        )
        repo.get_active_reservations.return_value = []
        repo.list_user_storage_keys.return_value = {
            "raw-selfies": ["users/u-1/raw/a.jpg"],
            "generated-images": ["users/u-1/after.jpg"],
            "avatars": [],
        }
        repo.delete.return_value = [{"id": "u-1"}] if user_exists else []
        return repo

    def _make_deps(self):
        """Common dep-kwargs dict that every test reuses."""

        async def empty_scan(match, count):
            for _ in ():
                yield _

        redis_client = MagicMock()
        redis_client.scan_iter = empty_scan
        redis_client.delete = AsyncMock(return_value=0)
        return dict(
            image_repo=MagicMock(),
            orphan_repo=MagicMock(),
            ledger=MagicMock(),
            redis_client=redis_client,
            arq_pool=MagicMock(enqueue_job=AsyncMock(return_value=None)),
        )

    @pytest.mark.asyncio
    async def test_happy_path_auth_delete_before_db_and_reservation_after(self):
        from app.api.auth import delete_account

        user_repo = self._make_user_repo()
        deps = self._make_deps()

        call_order: list[str] = []
        user_repo.auth_delete_user.side_effect = lambda *_: call_order.append("auth")
        deps["image_repo"].remove.side_effect = lambda *_: call_order.append("blob")
        user_repo.delete.side_effect = lambda *_: (
            call_order.append("db") or [{"id": "u-1"}]
        )
        user_repo.insert_username_reservation.side_effect = (
            lambda *_: call_order.append("reservation")
        )

        resp = await delete_account(
            claims={"sub": "u-1"}, user_repo=user_repo, **deps
        )

        # Order: auth → blob → db → reservation
        assert call_order.index("auth") < call_order.index("db")
        assert call_order.index("blob") < call_order.index("db")
        assert call_order.index("db") < call_order.index("reservation")
        assert resp.status_code == status.HTTP_204_NO_CONTENT

    @pytest.mark.asyncio
    async def test_reservation_uses_normalized_username(self):
        from app.api.auth import delete_account

        user_repo = self._make_user_repo()
        user_repo.get_profile_by_id.return_value = {
            "id": "u-1",
            "username": "Álicé",  # NFC composed + non-ASCII
        }
        deps = self._make_deps()

        await delete_account(
            claims={"sub": "u-1"}, user_repo=user_repo, **deps
        )

        args, _ = user_repo.insert_username_reservation.call_args
        assert args[0] == "alice"  # NFKC + unidecode + lower

    @pytest.mark.asyncio
    async def test_auth_delete_failure_raises_502_and_skips_db_delete(self):
        from app.api.auth import delete_account

        user_repo = self._make_user_repo()
        user_repo.auth_delete_user.side_effect = RuntimeError("supabase down")
        deps = self._make_deps()

        with pytest.raises(HTTPException) as exc:
            await delete_account(
                claims={"sub": "u-1"}, user_repo=user_repo, **deps
            )
        assert exc.value.status_code == status.HTTP_502_BAD_GATEWAY
        user_repo.delete.assert_not_called()
        user_repo.insert_username_reservation.assert_not_called()

    @pytest.mark.asyncio
    async def test_blob_wipe_failure_falls_through_to_dlq(self):
        from app.api.auth import delete_account

        user_repo = self._make_user_repo()
        deps = self._make_deps()
        deps["image_repo"].remove.side_effect = RuntimeError("boom")

        await delete_account(
            claims={"sub": "u-1"}, user_repo=user_repo, **deps
        )

        recorded = {
            (c.args[0], c.args[1])
            for c in deps["orphan_repo"].record.call_args_list
        }
        assert ("raw-selfies", "users/u-1/raw/a.jpg") in recorded
        assert ("generated-images", "users/u-1/after.jpg") in recorded
        # DB delete still happens because blob failure is best-effort.
        user_repo.delete.assert_called_once_with("u-1")

    @pytest.mark.asyncio
    async def test_large_user_offloads_blob_wipe_to_arq(self):
        from app.api.auth import delete_account

        user_repo = self._make_user_repo()
        user_repo.list_user_storage_keys.return_value = {
            "raw-selfies": [f"users/u-1/raw/{i}.jpg" for i in range(600)],
            "generated-images": [],
            "avatars": [],
        }
        deps = self._make_deps()

        await delete_account(
            claims={"sub": "u-1"}, user_repo=user_repo, **deps
        )

        # Inline remove not called; ARQ job enqueued.
        deps["image_repo"].remove.assert_not_called()
        deps["arq_pool"].enqueue_job.assert_called_once()
        job_args = deps["arq_pool"].enqueue_job.call_args
        assert job_args.args[0] == "wipe_deleted_user_blobs"
        assert job_args.kwargs["user_id"] == "u-1"

    @pytest.mark.asyncio
    async def test_already_deleted_is_idempotent_204(self):
        """Second call on an already-deleted user is a no-op success."""
        from app.api.auth import delete_account

        user_repo = self._make_user_repo(user_exists=False)
        deps = self._make_deps()

        resp = await delete_account(
            claims={"sub": "u-1"}, user_repo=user_repo, **deps
        )
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        user_repo.auth_delete_user.assert_not_called()
        user_repo.delete.assert_not_called()
        user_repo.insert_username_reservation.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest -x -q tests/test_hard_delete_account.py
```

Expected: FAIL — the current `delete_account` signature doesn't accept `image_repo` or `orphan_repo`; `user_repo.insert_username_reservation` does not exist on the real signature yet either.

- [ ] **Step 3: Add dependency providers for `image_repo` + `orphan_repo`**

If `get_image_repo` / `get_orphaned_storage_repo` already exist in `app/api/deps.py`, skip to Step 4. Otherwise add:

```python
from app.repositories.image_repo import ImageRepository
from app.repositories.orphaned_storage_repo import OrphanedStorageKeyRepository


def get_image_repo(sb: Client = Depends(get_supabase)) -> ImageRepository:
    return ImageRepository(sb)


def get_orphaned_storage_repo(
    sb: Client = Depends(get_supabase),
) -> OrphanedStorageKeyRepository:
    return OrphanedStorageKeyRepository(sb)
```

Run `rtk grep "def get_image_repo" app/api/deps.py` first to avoid duplicates.

- [ ] **Step 4: Rewrite `delete_account`**

Replace the entire block in `app/api/auth.py` (currently lines ~1294-1397) with:

```python
# ---------------------------------------------------------------------------
# Account Deletion — DELETE /auth/account (hard-delete with 180-day username
# reservation, blob wipe, CASCADE/SET NULL, and Redis cleanup).
#
# Ordering chosen so no single step leaves the system in a worse state than
# "user still exists and can retry":
#   - auth identity deleted first  → if it fails, row intact, user retries.
#   - blob wipe second             → orphaned blobs are safer than stale rows.
#   - DB DELETE third              → cascades/set-nulls drop/anonymize the rest.
#   - reservation inserted ONLY if the DELETE returned a row → never orphaned.
#   - Redis cleanup best-effort    → nightly retention is the backstop.
# ---------------------------------------------------------------------------

# Large-user threshold: above this blob count we enqueue an ARQ job instead of
# wiping inline, so the HTTP request doesn't time out or starve the worker.
_INLINE_BLOB_WIPE_THRESHOLD = 500


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_account(
    claims: UserClaims = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_user_repo),
    image_repo: ImageRepository = Depends(get_image_repo),
    orphan_repo: OrphanedStorageKeyRepository = Depends(get_orphaned_storage_repo),
    ledger: CreditLedger = Depends(get_credit_ledger),
    redis_client: aioredis.Redis = Depends(get_redis),
    arq_pool: ArqRedis = Depends(get_arq_pool),
) -> Response:
    """Permanently delete the authenticated user and every owned artifact.

    Idempotent: second call (user already gone) returns 204.
    """
    user_id: str = claims["sub"]
    now_utc = datetime.now(tz=timezone.utc)
    reserved_until = now_utc + timedelta(days=settings.USERNAME_RESERVATION_DAYS)

    user = await run_sync(user_repo.get_profile_by_id, user_id)
    if not user:
        # Idempotent: already deleted. No-op success.
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    username: str = user["username"]

    # 1. Release active credit reservations (unchanged from prior impl).
    try:
        active_reservations = user_repo.get_active_reservations(user_id)
        for res in active_reservations:
            try:
                from uuid import UUID as _UUID

                ledger.release(_UUID(res["id"]))
            except Exception as release_exc:  # noqa: BLE001
                logger.warning(
                    "Failed to release reservation %s: %s", res["id"], release_exc
                )
    except Exception as exc:
        logger.error("Failed to release reservations for %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account deletion failed — could not release credit reservations.",
        ) from exc

    # 2. Collect blob keys BEFORE cascade makes enumeration impossible.
    try:
        keys_by_bucket = await run_sync(user_repo.list_user_storage_keys, user_id)
    except Exception as exc:
        logger.error("Failed to enumerate storage keys for %s: %s", user_id, exc)
        keys_by_bucket = {}

    total_blobs = sum(len(k) for k in keys_by_bucket.values())

    # 3. Delete Supabase auth identity FIRST. If this fails, everything below
    #    is skipped — the user can retry.
    try:
        await run_sync(user_repo.auth_delete_user, user_id)
    except Exception as exc:
        logger.error("auth.admin.delete_user failed for %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication service error — account was not deleted.",
        ) from exc

    # 4. Blob wipe. Inline for small users; offload to ARQ for large users so
    #    the HTTP request finishes quickly and the worker can paginate.
    if total_blobs <= _INLINE_BLOB_WIPE_THRESHOLD:
        for bucket, keys in keys_by_bucket.items():
            if not keys:
                continue
            try:
                await run_sync(image_repo.remove, bucket, keys)
            except Exception as exc:  # noqa: BLE001 — fall through to DLQ per key
                logger.warning(
                    "Blob wipe failed for user %s in bucket %s: %s — enqueueing DLQ",
                    user_id,
                    bucket,
                    exc,
                )
                for key in keys:
                    await run_sync(
                        orphan_repo.record, bucket, key, "delete_account"
                    )
    else:
        # Offload to ARQ worker (wipe_deleted_user_blobs). The job collects the
        # remaining keys itself via cursor-paginated queries that now return
        # nothing for this user_id (they race; the pagination handles it).
        logger.info(
            "delete_account: %d blobs — offloading wipe to ARQ for user %s",
            total_blobs,
            user_id,
        )
        await arq_pool.enqueue_job(
            "wipe_deleted_user_blobs",
            user_id=user_id,
            keys_by_bucket=keys_by_bucket,
            _job_id=f"delete_account:{user_id}",  # dedupe concurrent calls
        )

    # 5. Hard-delete the user row. Cascade/set-null handle every FK.
    try:
        deleted = await run_sync(user_repo.delete, user_id)
    except Exception as exc:
        logger.error("users DELETE failed for %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account deletion failed.",
        ) from exc

    if not deleted:
        # Auth identity is gone but the row vanished between steps — treat as
        # idempotent success. No reservation (nothing to reserve).
        logger.info("delete_account: user %s row vanished mid-flow", user_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # 6. Reservation — only if the DELETE actually deleted something. Guards
    #    against orphan reservations blocking the user's own handle on a
    #    partial-failure retry.
    try:
        normalized_username = _normalize_username(username)
        await run_sync(
            user_repo.insert_username_reservation,
            normalized_username,
            reserved_until,
        )
    except Exception as exc:
        # DB is already gone; log and move on. Retention sweeper reconciles.
        logger.warning(
            "Reservation insert failed post-delete for user %s: %s",
            user_id,
            exc,
        )

    # Do NOT log the username — PII on a row the user asked to be forgotten.
    logger.info(
        "Account hard-deleted for user %s (reserved until %s)",
        user_id,
        reserved_until.date(),
    )

    # 7. Redis cleanup.
    try:
        redis_keys_to_delete = [
            f"advisor_chat_rate:{user_id}",
            f"concurrent:{user_id}",
        ]
        # SCAN (non-blocking) instead of KEYS — KEYS is O(N) on full keyspace.
        async for key in redis_client.scan_iter(
            match=f"gen:user_daily:{user_id}:*", count=100
        ):
            redis_keys_to_delete.append(key)
        if redis_keys_to_delete:
            await redis_client.delete(*redis_keys_to_delete)
    except Exception as exc:
        logger.warning("Redis cleanup failed for deleted user %s: %s", user_id, exc)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

**Username normalization helper** (used by both the endpoint and `user_repo`):

```python
# app/api/auth.py (top of file) or a shared helpers module.
import unicodedata
from unidecode import unidecode  # add to pyproject via `uv add unidecode`


def _normalize_username(username: str) -> str:
    """NFKC + ASCII-fold lowercase — homograph-safe availability key.

    Applied at registration, availability check, and reservation insert so
    Cyrillic 'а', fullwidth 'ａ', and diacritic variants ('café') all
    collide with their ASCII base forms.
    """
    return unidecode(unicodedata.normalize("NFKC", username)).lower()
```

`user_repo.check_username_availability`, `check_username_available_ci`, and
`insert_username_reservation` (Task 2) must all call `_normalize_username`
on their inputs before hitting the DB. The `lower(username)` unique index
on `username_reservations` then matches the normalized form naturally.

Add the two imports at the top of the file if not already present:

```python
from app.repositories.image_repo import ImageRepository
from app.repositories.orphaned_storage_repo import OrphanedStorageKeyRepository
from app.api.deps import get_image_repo, get_orphaned_storage_repo
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest -x -q tests/test_hard_delete_account.py
```

Expected: `6 passed` (not skipped). If pytest reports skipped tests
it means `@requires_routers` short-circuited — investigate
`tests/conftest.py` for what condition the decorator checks and register
the auth router in the test config before re-running.

- [ ] **Step 6: Run the full suite**

```bash
.venv/bin/python -m pytest -x -q
```

Expected: all pre-existing tests still pass. Fix any that relied on `soft_delete` or `is_("deleted_at", "null")` before continuing.

- [ ] **Step 7: Commit**

```bash
git add app/api/auth.py app/api/deps.py tests/test_hard_delete_account.py
git commit -m "feat(auth): rewrite delete_account as hard-delete with reservation + blob wipe"
```

---

## Task 5: Drop `deleted_at` guards across repos + shareable-card 410

**Files:**
- Modify: `app/repositories/user_repo.py`, `app/repositories/post_repo.py`, `app/repositories/feed_repo.py`, `app/api/public.py`, and any other file still referencing `deleted_at` or `username_reserved_until`.

- [ ] **Step 1: Find every call site**

```bash
rtk grep "deleted_at\|username_reserved_until\|soft_delete" app tests 2>&1 | tee /tmp/deleted_at_sites.txt
```

- [ ] **Step 2: Remove each `is_("deleted_at", "null")` guard**

For every match in `/tmp/deleted_at_sites.txt` inside `app/`, remove the `.is_("deleted_at", "null")` call from the query chain. Example before/after:

```python
# Before
result = (
    self._sb.table("users")
    .select("id, username")
    .eq("id", user_id)
    .is_("deleted_at", "null")
    .maybe_single()
    .execute()
)

# After
result = (
    self._sb.table("users")
    .select("id, username")
    .eq("id", user_id)
    .maybe_single()
    .execute()
)
```

Remove any `deleted_at` column selection from `select(...)` strings too (e.g. `"id, deleted_at, username_reserved_until"` → `"id"`).

- [ ] **Step 3: Drop the shareable-card HTTP 410 branch**

In `app/api/public.py`, find the shareable-card handler (search for `410` or `get_by_username_for_card`). Replace the branch that returns 410 when `deleted_at` is set with the natural 404 path — since the row no longer exists post-hard-delete, the normal "not found" branch covers it.

```bash
rtk grep "HTTP_410\|410\|user.get(\"deleted_at\")" app/api/public.py
```

Delete the matched 410 branch and any `deleted_at` reference in the same handler.

- [ ] **Step 4: Run full test suite**

```bash
make format && make lint && .venv/bin/python -m pytest -x -q
```

Expected: green. Fix anything red before moving on.

- [ ] **Step 5: Commit**

```bash
git add app/ tests/
git commit -m "refactor: drop deleted_at tombstone checks (no longer exists)"
```

---

## Task 5.5: ARQ worker — `wipe_deleted_user_blobs` (large-user offload)

**Files:**
- Modify: `app/workers/orphan_reclaim.py` OR new `app/workers/delete_account_blobs.py`
- Modify: `app/worker_settings.py` — register the new job
- Test: `tests/test_wipe_deleted_user_blobs_worker.py`

- [ ] **Step 1: Write the failing test**

```python
"""wipe_deleted_user_blobs — ARQ job that drains blob-wipe work for large users.

Invoked by delete_account when total blob count exceeds the inline threshold.
Chunks image_repo.remove into 250-key batches; failures go to the orphan DLQ.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.workers.delete_account_blobs import wipe_deleted_user_blobs


@pytest.mark.asyncio
async def test_chunks_remove_and_dlqs_failures():
    image_repo = MagicMock()
    orphan_repo = MagicMock()

    # 600 keys in raw-selfies; 200 in generated-images.
    image_repo.remove.side_effect = [
        None,                    # first 250 raw-selfies succeed
        RuntimeError("boom"),    # next 250 raw-selfies fail → DLQ each
        None,                    # last 100 raw-selfies succeed
        None,                    # 200 generated-images succeed
    ]

    ctx = {"image_repo": image_repo, "orphan_repo": orphan_repo}
    keys_by_bucket = {
        "raw-selfies": [f"u-1/raw/{i}.jpg" for i in range(600)],
        "generated-images": [f"u-1/gen/{i}.jpg" for i in range(200)],
        "post-images": [],
        "avatars": [],
    }

    await wipe_deleted_user_blobs(ctx, user_id="u-1", keys_by_bucket=keys_by_bucket)

    # 4 batched removes total (600/250 ceil=3 + 200/250 ceil=1)
    assert image_repo.remove.call_count == 4
    # The failed batch (250 keys) each went to DLQ
    assert orphan_repo.record.call_count == 250
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest -x -q tests/test_wipe_deleted_user_blobs_worker.py
```

Expected: `ModuleNotFoundError: No module named 'app.workers.delete_account_blobs'`.

- [ ] **Step 3: Implement the worker**

Create `app/workers/delete_account_blobs.py`:

```python
"""ARQ job: wipe a deleted user's blobs in chunked batches.

Invoked by DELETE /auth/account when the user's total blob count exceeds
the inline-wipe threshold. Chunks each bucket into batches of
_CHUNK_SIZE keys; failed batches enqueue every key in the orphan DLQ so
the nightly reclaim worker can retry.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 250


async def wipe_deleted_user_blobs(
    ctx: dict,
    *,
    user_id: str,
    keys_by_bucket: dict[str, list[str]],
) -> None:
    image_repo = ctx["image_repo"]
    orphan_repo = ctx["orphan_repo"]

    wiped = 0
    failed = 0
    for bucket, keys in keys_by_bucket.items():
        for start in range(0, len(keys), _CHUNK_SIZE):
            chunk = keys[start : start + _CHUNK_SIZE]
            try:
                image_repo.remove(bucket, chunk)
                wiped += len(chunk)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "wipe_deleted_user_blobs: bucket %s chunk [%d:%d] failed for %s: %s",
                    bucket,
                    start,
                    start + len(chunk),
                    user_id,
                    exc,
                )
                for key in chunk:
                    orphan_repo.record(bucket, key, "delete_account")
                failed += len(chunk)

    logger.info(
        "wipe_deleted_user_blobs: user=%s wiped=%d failed=%d",
        user_id,
        wiped,
        failed,
    )
```

Register in `app/worker_settings.py` (alongside the existing
`reclaim_orphaned_blobs` registration — follow the exact pattern there):

```python
from app.workers.delete_account_blobs import wipe_deleted_user_blobs

WorkerSettings.functions = [
    # ...existing jobs...
    wipe_deleted_user_blobs,
]
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/python -m pytest -x -q tests/test_wipe_deleted_user_blobs_worker.py
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add app/workers/delete_account_blobs.py app/worker_settings.py tests/test_wipe_deleted_user_blobs_worker.py
git commit -m "feat(workers): wipe_deleted_user_blobs ARQ job"
```

---

## Task 6: Nightly reservation cleanup in `retention.py`

**Files:**
- Modify: `app/workers/retention.py`
- Test: `tests/test_retention_reservation_cleanup.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_retention_reservation_cleanup.py`:

```python
"""Retention worker deletes username_reservations rows whose window has
elapsed. Expired rows never affect availability, but the table grows
forever if we don't prune it."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.workers.retention import purge_expired_username_reservations


@pytest.mark.asyncio
async def test_deletes_rows_where_reserved_until_lt_now():
    captured: dict[str, object] = {}

    def fake_delete():
        captured["delete_called"] = True
        chain = MagicMock()

        def fake_lt(col, val):
            captured["lt_col"] = col
            captured["lt_val"] = val
            return chain

        chain.lt.side_effect = fake_lt
        chain.execute.return_value = MagicMock(data=[{"username": "alice"}])
        return chain

    table = MagicMock()
    table.delete.side_effect = fake_delete
    supabase = MagicMock()
    supabase.table.return_value = table

    count = await purge_expired_username_reservations(supabase)

    assert captured["delete_called"] is True
    assert captured["lt_col"] == "reserved_until"
    assert count == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest -x -q tests/test_retention_reservation_cleanup.py
```

Expected: FAIL with `ImportError: cannot import name 'purge_expired_username_reservations'`.

- [ ] **Step 3: Implement**

Append to `app/workers/retention.py` (before the main retention entrypoint or at the bottom — pick a location consistent with the existing style):

```python
async def purge_expired_username_reservations(supabase: Client) -> int:
    """Delete username_reservations rows whose window has elapsed.

    Availability logic already ignores expired rows, so this is pure
    table-hygiene. Returns the number of rows deleted.
    """
    from datetime import datetime, timezone

    result = (
        supabase.table("username_reservations")
        .delete()
        .lt("reserved_until", datetime.now(tz=timezone.utc).isoformat())
        .execute()
    )
    return len(result.data or [])
```

Wire it into the existing retention entrypoint so it runs in the same nightly cron:

```python
# inside run_retention (or whatever the existing ARQ entrypoint is named),
# after the existing steps:
try:
    purged = await purge_expired_username_reservations(supabase)
    logger.info("Retention: purged %d expired username reservations", purged)
except Exception:
    logger.exception("username_reservations cleanup failed")
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/python -m pytest -x -q tests/test_retention_reservation_cleanup.py
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add app/workers/retention.py tests/test_retention_reservation_cleanup.py
git commit -m "feat(retention): nightly username_reservations cleanup"
```

---

## Task 7: Mobile — promote storage keys to constants

**Files:**
- Modify: `mobile/constants/config.ts`
- Modify: `mobile/app/_layout.tsx`, `mobile/app/onboarding.tsx`, `mobile/lib/auth-context.tsx` — replace string literals with the constants.

- [ ] **Step 1: Add two keys to `SECURE_STORE_KEYS`**

Edit `mobile/constants/config.ts`:

```ts
export const SECURE_STORE_KEYS = {
  GUEST_TOKEN: "nxme_guest_token",
  JWT: "nxme_jwt",
  REFRESH_TOKEN: "nxme_refresh_token",
  PENDING_EMAIL_VERIFICATION: "nxme_pending_email_verification",
  GUEST_PURGED_AT: "nxme_guest_purged_at",
  /** Device-local flag set once the onboarding screen has been completed. */
  ONBOARDING_COMPLETE: "nxme_onboarding_complete",
  /** Canonical location for the current user's username. */
  USERNAME: "nxme_username",
} as const;
```

- [ ] **Step 2: Replace the string literal in `_layout.tsx`**

In `mobile/app/_layout.tsx`, find the line:

```ts
getItem("nxme_onboarding_complete").then((value) => {
```

Replace with:

```ts
getItem(SECURE_STORE_KEYS.ONBOARDING_COMPLETE).then((value) => {
```

Add the import if not present:

```ts
import { SECURE_STORE_KEYS } from "../constants/config";
```

- [ ] **Step 3: Replace the string literal in `onboarding.tsx`**

In `mobile/app/onboarding.tsx`, find:

```ts
await setItem("nxme_onboarding_complete", "true");
```

Replace with:

```ts
await setItem(SECURE_STORE_KEYS.ONBOARDING_COMPLETE, "true");
```

Add the import.

- [ ] **Step 4: Replace `USERNAME_KEY` in `auth-context.tsx`**

In `mobile/lib/auth-context.tsx`, delete the local constant:

```ts
const USERNAME_KEY = "nxme_username";
```

Replace every `USERNAME_KEY` reference in that file with `SECURE_STORE_KEYS.USERNAME`. Import the constant from `../constants/config`.

- [ ] **Step 5: Verify nothing else references the raw strings**

```bash
cd mobile && rtk grep "nxme_onboarding_complete\|nxme_username" --type ts --type tsx 2>&1 | tee /tmp/raw_keys.txt
```

Expected: only hits are the three constant definitions. If any other file still uses the literal, update it.

- [ ] **Step 6: Run mobile lint + tests**

```bash
cd mobile && npx expo lint && npx jest -o
```

Expected: both clean.

- [ ] **Step 7: Commit**

```bash
git add mobile/constants/config.ts mobile/app/_layout.tsx mobile/app/onboarding.tsx mobile/lib/auth-context.tsx
git commit -m "refactor(mobile): promote onboarding + username storage keys to constants"
```

---

## Task 8: Mobile — `wipeLocalDeviceState` helper

**Files:**
- Create: `mobile/lib/account-wipe.ts`
- Test: `mobile/lib/__tests__/account-wipe.test.ts`

- [ ] **Step 1: Prerequisite — expose a `clear()` surface on each store**

Current state (verified via grep, 2026-04-18):

| Store | Export name | Has `clear()`? | Storage backend |
|---|---|---|---|
| `mobile/lib/dismissed-jobs-store.ts` | functions only (`loadDismissedJobIds`, `addDismissedJobId`, `__resetDismissedJobIdsForTests`) | **no** | AsyncStorage (`@nxme:dismissed_errored_jobs`) |
| `mobile/lib/refund-toast-store.ts` | functions only (`markRefundToastSeen`, `__resetRefundToastSeenForTests`) | **no** | AsyncStorage (`@nxme:refund_toasts_seen`) |
| `mobile/lib/offline-queue.ts` | `mutationQueue` (instance) | **yes** (`.clear()`) | MMKV |

Three sub-steps:

1. In `mobile/lib/dismissed-jobs-store.ts`, add a new module-level export:

```ts
export async function clearDismissedJobs(): Promise<void> {
  cache = new Set();
  hydratePromise = null;
  try {
    await AsyncStorage.removeItem(PROFILE_DISMISSED_ERRORED_JOBS_STORAGE_KEY);
  } catch (err) {
    if (__DEV__) console.warn("clearDismissedJobs: storage remove failed", err);
  }
}
```

Match the private state names used at the top of the existing file (rename `cache` / `hydratePromise` to whatever the file already uses).

2. In `mobile/lib/refund-toast-store.ts`, add the symmetric helper:

```ts
export async function clearRefundToastSeen(): Promise<void> {
  cache = new Set();
  hydratePromise = null;
  try {
    await AsyncStorage.removeItem(REFUND_TOAST_SEEN_STORAGE_KEY);
  } catch (err) {
    if (__DEV__) console.warn("clearRefundToastSeen: storage remove failed", err);
  }
}
```

3. `mutationQueue` already exposes `.clear()` — use it as-is. Note that it is backed by `react-native-mmkv` (not AsyncStorage), so `AsyncStorage.multiRemove` in the helper will NOT reach it; `mutationQueue.clear()` is the only way to wipe that backing store.

Commit these three store changes separately before proceeding:

```bash
git add mobile/lib/dismissed-jobs-store.ts mobile/lib/refund-toast-store.ts
git commit -m "feat(mobile): clearDismissedJobs + clearRefundToastSeen for wipe"
```

- [ ] **Step 2: Write the failing test**

Create `mobile/lib/__tests__/account-wipe.test.ts`:

```ts
import AsyncStorage from "@react-native-async-storage/async-storage";

import * as secureStorage from "../secure-storage";
import * as dismissedJobs from "../dismissed-jobs-store";
import * as refundToast from "../refund-toast-store";
import { mutationQueue } from "../offline-queue";
import { queryClient } from "../query-client";
import { SECURE_STORE_KEYS } from "../../constants/config";
import {
  PROFILE_DISMISSED_ERRORED_JOBS_STORAGE_KEY,
  REFUND_TOAST_SEEN_STORAGE_KEY,
} from "../../constants/config";
import { wipeLocalDeviceState } from "../account-wipe";

jest.mock("@react-native-async-storage/async-storage", () => ({
  multiRemove: jest.fn().mockResolvedValue(undefined),
  removeItem: jest.fn().mockResolvedValue(undefined),
}));

describe("wipeLocalDeviceState", () => {
  beforeEach(() => {
    jest.spyOn(secureStorage, "deleteItem").mockResolvedValue(undefined);
    jest.spyOn(dismissedJobs, "clearDismissedJobs").mockResolvedValue(undefined);
    jest.spyOn(refundToast, "clearRefundToastSeen").mockResolvedValue(undefined);
    jest.spyOn(mutationQueue, "clear").mockReturnValue(undefined);
    jest.spyOn(queryClient, "clear").mockReturnValue(undefined);
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("deletes every SecureStore key", async () => {
    await wipeLocalDeviceState();

    const deleted = (secureStorage.deleteItem as jest.Mock).mock.calls.map(
      (c) => c[0],
    );
    expect(deleted).toEqual(
      expect.arrayContaining(Object.values(SECURE_STORE_KEYS)),
    );
  });

  it("clears every AsyncStorage key", async () => {
    await wipeLocalDeviceState();

    expect(AsyncStorage.multiRemove).toHaveBeenCalledWith(
      expect.arrayContaining([
        PROFILE_DISMISSED_ERRORED_JOBS_STORAGE_KEY,
        REFUND_TOAST_SEEN_STORAGE_KEY,
      ]),
    );
  });

  it("resets in-memory singletons and the query cache", async () => {
    await wipeLocalDeviceState();

    expect(dismissedJobs.clearDismissedJobs).toHaveBeenCalledTimes(1);
    expect(refundToast.clearRefundToastSeen).toHaveBeenCalledTimes(1);
    expect(mutationQueue.clear).toHaveBeenCalledTimes(1);
    expect(queryClient.clear).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd mobile && npx jest lib/__tests__/account-wipe.test.ts
```

Expected: FAIL — `Cannot find module '../account-wipe'`.

- [ ] **Step 4: Implement the helper**

Create `mobile/lib/account-wipe.ts`:

```ts
/**
 * wipeLocalDeviceState — reset every user-owned device-local surface.
 *
 * Called ONLY by the delete-account flow. Logout stays narrow (tokens only).
 * Adding new client-local state? Wire it in here.
 *
 * Coverage map:
 *   SecureStore (Keychain / Keystore) — every SECURE_STORE_KEYS value
 *   AsyncStorage                      — every @nxme:* key we own
 *   MMKV (via mutationQueue)          — offline mutation queue
 *   In-process                        — dismissed-jobs-store, refund-toast-store,
 *                                       queryClient cache
 */
import AsyncStorage from "@react-native-async-storage/async-storage";

import {
  SECURE_STORE_KEYS,
  PROFILE_DISMISSED_ERRORED_JOBS_STORAGE_KEY,
  REFUND_TOAST_SEEN_STORAGE_KEY,
} from "../constants/config";
import { deleteItem } from "./secure-storage";
import { clearDismissedJobs } from "./dismissed-jobs-store";
import { clearRefundToastSeen } from "./refund-toast-store";
import { mutationQueue } from "./offline-queue";
import { queryClient } from "./query-client";

export async function wipeLocalDeviceState(): Promise<void> {
  // 1. SecureStore — every nxme_* key (includes JWT / refresh / guest / onboarding / username)
  await Promise.all(
    Object.values(SECURE_STORE_KEYS).map((key) => deleteItem(key)),
  );

  // 2. AsyncStorage — every @nxme:* key we own
  await AsyncStorage.multiRemove([
    PROFILE_DISMISSED_ERRORED_JOBS_STORAGE_KEY,
    REFUND_TOAST_SEEN_STORAGE_KEY,
  ]);

  // 3. Module-level caches (also idempotently purges their backing AsyncStorage keys)
  await Promise.all([clearDismissedJobs(), clearRefundToastSeen()]);

  // 4. MMKV-backed offline mutation queue — not reachable via AsyncStorage
  mutationQueue.clear();

  // 5. React Query cache
  queryClient.clear();
}
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd mobile && npx jest lib/__tests__/account-wipe.test.ts
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add mobile/lib/account-wipe.ts mobile/lib/__tests__/account-wipe.test.ts
git commit -m "feat(mobile): wipeLocalDeviceState — device-wide reset for delete-account"
```

---

## Task 9: Wire `wipeLocalDeviceState` into `handleDeleteAccount`

**Files:**
- Modify: `mobile/app/settings.tsx:146-171`
- Test: `mobile/app/__tests__/settings-delete.test.tsx` (create if missing)

- [ ] **Step 1: Write the failing test**

Create `mobile/app/__tests__/settings-delete.test.tsx`:

```tsx
import { fireEvent, render, waitFor } from "@testing-library/react-native";

import SettingsScreen from "../settings";
import * as api from "../../lib/api";
import * as accountWipe from "../../lib/account-wipe";
import * as authContext from "../../lib/auth-context";

jest.mock("../../lib/api");
jest.mock("../../lib/account-wipe");
jest.mock("../../lib/auth-context", () => {
  const actual = jest.requireActual("../../lib/auth-context");
  return {
    ...actual,
    useAuth: () => ({
      session: { isUser: true, isGuest: false, isAnon: false },
      setSessionMode: jest.fn(),
    }),
  };
});

describe("handleDeleteAccount", () => {
  it("calls wipeLocalDeviceState exactly once after a successful DELETE", async () => {
    const apiFetch = jest
      .spyOn(api, "apiFetch")
      .mockResolvedValue(undefined as unknown as void);
    const wipe = jest
      .spyOn(accountWipe, "wipeLocalDeviceState")
      .mockResolvedValue(undefined);

    const screen = render(<SettingsScreen />);
    const button = await screen.findByLabelText("Delete account");
    fireEvent.press(button);

    // Alert.alert confirmation is mocked to always call the destructive onPress
    // in jest setup — see mobile/jest.setup.ts. If that helper does not exist,
    // add it in a prerequisite step.
    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith("/v1/auth/account", {
        method: "DELETE",
      });
      expect(wipe).toHaveBeenCalledTimes(1);
    });
  });
});
```

**Prerequisite: Alert.alert auto-confirm helper.** Before Step 2, open
`mobile/jest.setup.ts` and grep for `Alert.alert` — if no auto-confirm
mock exists, append:

```ts
import { Alert } from "react-native";

jest.spyOn(Alert, "alert").mockImplementation((_title, _message, buttons) => {
  const destructive = buttons?.find((b) => b.style === "destructive");
  if (destructive?.onPress) destructive.onPress();
});
```

This mock is global and affects every test in the suite. Run the full
Jest suite after adding it to verify no pre-existing test relied on
Alert.alert staying un-mocked — fix any regression before continuing.

- [ ] **Step 2: Run test to verify it fails**

```bash
cd mobile && npx jest app/__tests__/settings-delete.test.tsx
```

Expected: FAIL — `wipeLocalDeviceState` is not imported yet in `settings.tsx`.

- [ ] **Step 3: Wire it in**

In `mobile/app/settings.tsx`:

Add imports:

```ts
import { useNavigation } from "@react-navigation/native";
import { wipeLocalDeviceState } from "../lib/account-wipe";
import { DeleteAccountOverlay } from "../components/settings/DeleteAccountOverlay";
```

**Client-side timeout constant** — add to `mobile/constants/config.ts`:

```ts
/**
 * Maximum wait for DELETE /v1/auth/account before surfacing a recoverable
 * error. Accounts with many blobs take time; 60s is 2× the observed p99.
 */
export const DELETE_ACCOUNT_TIMEOUT_MS = 60_000;
```

Update the confirmation dialog copy (currently: "This action is permanent
and cannot be undone. All your data will be deleted.") to reflect
hard-delete semantics, and add `usePreventRemove` so the user cannot
navigate away mid-operation via hardware back or iOS edge-swipe:

```ts
// Block hardware back + iOS edge-swipe while deleting. Alongside the
// full-screen DeleteAccountOverlay, this makes navigation-during-delete
// impossible.
const navigation = useNavigation();
useEffect(() => {
  if (!isDeleting) return undefined;
  const unsubscribe = navigation.addListener("beforeRemove", (e) => {
    e.preventDefault();
  });
  return unsubscribe;
}, [isDeleting, navigation]);

const handleDeleteAccount = useCallback(() => {
  Alert.alert(
    "Delete Account",
    "Your photos, glow-ups, and account data will be permanently deleted. Your username will be reserved for 180 days. This cannot be undone.",
    [
      { text: "Cancel", style: "cancel" },
      {
        text: "Delete",
        style: "destructive",
        onPress: async () => {
          setIsDeleting(true);
          try {
            // Client-side timeout — if the server is slow or hangs, we
            // unblock the UI with a recoverable error rather than trapping
            // the user behind usePreventRemove + the hidden back button.
            await Promise.race([
              apiFetch<void>("/v1/auth/account", { method: "DELETE" }),
              new Promise<never>((_, reject) =>
                setTimeout(
                  () => reject(new Error("delete-account-timeout")),
                  DELETE_ACCOUNT_TIMEOUT_MS,
                ),
              ),
            ]);
            await wipeLocalDeviceState();
            setSessionMode("anon");
            router.replace("/(auth)/login");
          } catch (err) {
            const appError = parseApiError(err);
            const message =
              (err as Error)?.message === "delete-account-timeout"
                ? "Deletion is taking longer than expected. Your account may still be deleted — check back in a few minutes or contact support if you see issues."
                : appError.message;
            showToast({ kind: "error", message });
            setIsDeleting(false);
          }
          // NOTE: no `finally { setIsDeleting(false) }` — on success the
          // screen unmounts via router.replace before the next tick.
        },
      },
    ],
  );
}, [router, setSessionMode]);
```

Render the overlay alongside the existing scroll view (outside it, so it
covers the full screen including the header):

```tsx
return (
  <View style={styles.container}>
    <PageBackground overlayOpacity={0.88} />
    <View style={[styles.header, { paddingTop: insets.top }]}>
      {/* Hide back button while deleting — user cannot navigate away. */}
      {isDeleting ? <HeaderBackButtonSpacer /> : <HeaderBackButton onPress={() => router.back()} />}
      <Heading ...>Settings</Heading>
      <HeaderBackButtonSpacer />
    </View>
    <ScrollView>
      {/* ...existing sections... */}
    </ScrollView>
    {isDeleting && <DeleteAccountOverlay />}
  </View>
);
```

Remove the old `clearAllTokens()` call — `wipeLocalDeviceState` covers token deletion via `SECURE_STORE_KEYS`. Leave `clearAllTokens` itself intact; logout still uses it.

Create `mobile/components/settings/DeleteAccountOverlay.tsx`:

```tsx
/**
 * Full-screen overlay shown while the delete-account server request is in
 * flight. Pairs with usePreventRemove in settings.tsx so the user cannot
 * navigate away mid-operation. A client-side timeout (DELETE_ACCOUNT_TIMEOUT_MS)
 * in the caller ensures the overlay cannot trap the user forever — on
 * timeout, the overlay dismisses and a toast surfaces a recovery message.
 */
import { ActivityIndicator, StyleSheet, View } from "react-native";

import { THEME } from "../../constants/theme";
import { Body, Heading } from "../ui/Text";

export function DeleteAccountOverlay() {
  return (
    <View
      style={styles.overlay}
      accessibilityRole="progressbar"
      accessibilityLabel="Deleting your account"
      // Trap VoiceOver/TalkBack focus inside the overlay so the underlying
      // settings list + header controls are not navigable while hidden.
      accessibilityViewIsModal
    >
      <ActivityIndicator size="large" color={THEME.colors.textPrimary} />
      <Heading
        size="md"
        style={styles.title}
        maxFontSizeMultiplier={1.3}
      >
        Deleting your account…
      </Heading>
      <Body
        color="secondary"
        style={styles.subtitle}
        maxFontSizeMultiplier={1.4}
      >
        This can take up to a minute while we remove your photos and data. Keep the app open.
      </Body>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0, 0, 0, 0.85)",
    alignItems: "center",
    justifyContent: "center",
    gap: THEME.spacing.lg,
    paddingHorizontal: THEME.spacing.xxl,
  },
  title: { textAlign: "center" },
  subtitle: { textAlign: "center" },
});
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd mobile && npx jest app/__tests__/settings-delete.test.tsx
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add mobile/app/settings.tsx mobile/app/__tests__/settings-delete.test.tsx mobile/jest.setup.ts
git commit -m "feat(mobile): delete-account calls wipeLocalDeviceState"
```

---

## Task 10: Maestro flow — delete, re-signup, onboarding visible

**Files:**
- Create: `mobile/.maestro/flows/40-delete-and-resignup-onboarding.yaml`

- [ ] **Step 1: Inspect existing flows for house style**

```bash
ls mobile/.maestro/flows | head
cat mobile/.maestro/flows/00-app-launch.yaml
cat mobile/.maestro/flows/31-login-wrong-credentials.yaml
```

- [ ] **Step 2: Write the new flow**

Create `mobile/.maestro/flows/40-delete-and-resignup-onboarding.yaml`:

```yaml
appId: host.exp.Exponent
---
# Test: after deleting the account and logging in again with the same Google
# identity on the same device, the onboarding screen is shown (stale
# nxme_onboarding_complete must not skip it).

- runFlow: 00-app-launch.yaml

# Precondition: must be logged in as the Maestro Google fixture account.
# If 00-app-launch leaves us logged out, the fixture login helper flow is
# expected at 10-google-login-fixture.yaml — run it here. Adjust the path if
# your repository names it differently.
- runFlow: 10-google-login-fixture.yaml

# Navigate to Settings → Delete Account.
- tapOn: "Profile"
- tapOn: "Settings"
- scrollUntilVisible:
    element: "Delete Account"
    direction: DOWN
    timeout: 5000
- tapOn: "Delete Account"
- tapOn: "Delete"   # destructive confirmation

# App returns to the login screen.
- extendedWaitUntil:
    visible: "Sign in or create an account"
    timeout: 15000
- takeScreenshot: delete_01_back_on_login

# Re-login with the same Google fixture account.
- runFlow: 10-google-login-fixture.yaml

# Onboarding screen must appear (it would not if the stale flag were still set).
- extendedWaitUntil:
    visible: "Upload Your Photo"
    timeout: 15000
- takeScreenshot: delete_02_onboarding_visible_after_resignup
```

- [ ] **Step 3: Dry-run the flow**

```bash
cd mobile && maestro test .maestro/flows/40-delete-and-resignup-onboarding.yaml
```

Expected: green. If the login-fixture flow (`10-google-login-fixture.yaml`) doesn't exist, create it or inline the login steps here — that's the only place where this flow depends on repository-specific helpers.

- [ ] **Step 4: Commit**

```bash
git add mobile/.maestro/flows/40-delete-and-resignup-onboarding.yaml
git commit -m "test(maestro): delete account then re-signup shows onboarding"
```

---

## Task 11: Full verification + PR

- [ ] **Step 1: Run the backend verification loop**

```bash
make format && make lint && make test
```

Expected: all green.

- [ ] **Step 2: Run the mobile verification loop**

```bash
cd mobile && npx expo lint && npx jest
```

Expected: all green.

- [ ] **Step 3: Manual smoke test on simulator**

```bash
cd mobile && npx expo run:ios
```

1. Sign in with Google, complete onboarding.
2. Settings → Delete Account → confirm.
3. Land on login screen.
4. Sign in with the same Google account.
5. Onboarding screen must appear.

Take a screenshot at step 5 and attach to the PR description.

- [ ] **Step 4: Commit the worktree-level artifacts (if any)**

Nothing left — all prior tasks committed.

- [ ] **Step 5: Push + open PR**

```bash
git push -u origin feat/delete-account-hard-reset
gh pr create --base dev --head feat/delete-account-hard-reset \
  --title "feat(auth): delete-account is a hard reset (server + device)" \
  --body "$(cat <<'EOF'
## Summary
- Replaces soft-delete with hard-delete across server and device.
- New migration 0044 adds username_reservations, drops users.deleted_at /
  users.username_reserved_until, and cascades the 11 NO ACTION FKs.
- delete_account endpoint now collects blob keys, inserts a 180-day
  reservation, wipes blobs inline (DLQ fallback), DELETEs the user
  (cascades everything owned), deletes the auth identity, and clears
  Redis.
- Mobile wipeLocalDeviceState helper clears every known SecureStore +
  AsyncStorage key, resets singletons + React Query cache, and is wired
  only into handleDeleteAccount. Logout stays narrow.
- Storage key string literals (nxme_onboarding_complete, nxme_username)
  promoted to SECURE_STORE_KEYS so every future client key is
  discoverable by grep for the reviewer rule.

## Spec
docs/superpowers/specs/2026-04-18-delete-account-hard-reset-design.md

## Test plan
- [x] make format / make lint / make test clean
- [x] mobile lint + jest clean
- [x] Maestro flow 40 passes locally
- [x] Manual smoke: delete → re-signup → onboarding appears (screenshot attached)
EOF
)"
```

- [ ] **Step 6: Wait for CI, merge, clean up**

```bash
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout dev && git pull origin dev
git branch -D feat/delete-account-hard-reset
```

---

## Self-Review Results

- **Spec coverage:** All five spec sections map to tasks:
  - Architecture / Backend steps → Tasks 1, 2, 3, 4, 5, 6
  - Mobile constants + wipe helper + wiring → Tasks 7, 8, 9
  - Logout non-goal → explicitly preserved in Task 9
  - Testing matrix → Tasks 2, 3, 4, 6, 8, 9, 10
  - Durable rule → recorded in memory (`feedback_delete_account_scope.md`) and referenced in the spec; Task 9 deliberately leaves `clearAllTokens` intact so logout can still use it.

- **Placeholder scan:** No "TBD" / "TODO" / "implement appropriate" patterns. Every code-changing step has the code inline.

- **Type consistency:** `UserRepository.delete`, `UserRepository.list_user_storage_keys`, `UserRepository.insert_username_reservation`, and the new FastAPI dependencies are referenced with the same names from the point of definition (Tasks 2-3) through the rewritten endpoint (Task 4) and in tests. Mobile helper is consistently `wipeLocalDeviceState` everywhere.
