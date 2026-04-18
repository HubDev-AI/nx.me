# Delete Account — Hard Reset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current soft-delete account flow with a hard-delete that wipes every user-owned surface (DB rows, blobs, Redis keys, device-local storage, in-memory singletons, React Query cache), while preserving a 180-day username reservation in a dedicated table.

**Architecture:** One migration switches 11 NO-ACTION FKs to ON DELETE CASCADE, creates a `username_reservations` table, and drops `users.deleted_at` + `users.username_reserved_until`. The `DELETE /v1/auth/account` endpoint is rewritten to collect blob keys, insert a reservation row, wipe blobs inline (with DLQ fallback), `DELETE FROM users` (cascades all owned data), delete the auth identity, and clean Redis. Client adds a `wipeLocalDeviceState` helper that clears every known SecureStore / AsyncStorage key and resets singletons + the React Query cache; it is called only from `handleDeleteAccount`, never from logout.

**Tech Stack:** Python 3.12, FastAPI, Supabase (Postgres via supabase-py + PostgREST), ARQ, pytest. Mobile: TypeScript, React Native, Expo, expo-secure-store, @react-native-async-storage/async-storage, @tanstack/react-query, Maestro.

**Branch:** `feat/delete-account-hard-reset`

**Pre-flight (run once, before Task 1):**

```bash
git checkout dev
git pull origin dev
git checkout -b feat/delete-account-hard-reset
make nuke    # pre-launch: wipe local DB so drop-column + FK changes have no stale rows to worry about
```

---

## File Structure

**Backend:**
- Create `app/migrations/0044_hard_delete_account.sql` — reservations table, drop soft-delete columns, CASCADE 11 FKs.
- Modify `app/repositories/user_repo.py` — remove `soft_delete`, add `delete`, add `list_user_storage_keys`, add `insert_username_reservation`, update `check_username_availability` to consult reservations.
- Modify `app/api/auth.py` — rewrite `delete_account`; drop `users.deleted_at` references; drop `username_reserved_until` usage.
- Modify `app/repositories/feed_repo.py`, `app/repositories/post_repo.py` — drop `is_("deleted_at", "null")` guards (no more tombstones).
- Modify `app/api/public.py` — drop shareable-card HTTP 410 branch.
- Modify `app/workers/retention.py` — add nightly reservation cleanup.
- Delete `tests/test_user_repo_soft_delete.py` — method is gone.
- Create `tests/test_hard_delete_account.py`, `tests/test_username_availability_with_reservations.py`, `tests/test_retention_reservation_cleanup.py`.

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

ALTER TABLE reports
    DROP CONSTRAINT reports_reporter_user_id_fkey,
    ADD  CONSTRAINT reports_reporter_user_id_fkey
         FOREIGN KEY (reporter_user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE blocked_users
    DROP CONSTRAINT blocked_users_blocker_id_fkey,
    ADD  CONSTRAINT blocked_users_blocker_id_fkey
         FOREIGN KEY (blocker_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE blocked_users
    DROP CONSTRAINT blocked_users_blocked_id_fkey,
    ADD  CONSTRAINT blocked_users_blocked_id_fkey
         FOREIGN KEY (blocked_id) REFERENCES users(id) ON DELETE CASCADE;

COMMIT;
```

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

Replace the existing `check_username_availability` and add `insert_username_reservation` in `app/repositories/user_repo.py`:

```python
def check_username_availability(
    self, username: str, exclude_user_id: str | None = None
) -> dict:
    """Return { available: bool, reason?: str }.

    Checks (in order): active users, then username_reservations still
    within the reservation window.
    """
    from datetime import timezone

    users_result = (
        self._sb.table("users")
        .select("id, username")
        .ilike("username", username)
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
        .ilike("username", username)
        .gt("reserved_until", now_iso)
        .execute()
    )
    if reservations_result.data:
        return {"available": False, "reason": "reserved"}

    return {"available": True}


def insert_username_reservation(
    self, username: str, reserved_until: datetime
) -> None:
    """UPSERT a reservation row, extending the window on conflict."""
    (
        self._sb.table("username_reservations")
        .upsert(
            {
                "username": username,
                "reserved_until": reserved_until.isoformat(),
            },
            on_conflict="username",
        )
        .execute()
    )
```

Delete the now-obsolete `soft_delete` method from the same file.

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest -x -q tests/test_username_availability_with_reservations.py
```

Expected: 5 passed.

- [ ] **Step 5: Delete the stale soft-delete test file**

```bash
git rm tests/test_user_repo_soft_delete.py
```

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
    glowup_analyses: list[dict] | None = None,
    users: list[dict] | None = None,
):
    deletes: list[str] = []

    def fake_table(name: str):
        qb = MagicMock()
        qb.select.return_value = qb
        qb.eq.return_value = qb
        if name == "uploads":
            qb.execute.return_value = MagicMock(data=uploads or [])
        elif name == "glowup_analyses":
            qb.execute.return_value = MagicMock(data=glowup_analyses or [])
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
            glowup_analyses=[
                {
                    "before_image_url": "users/u-1/before.jpg",
                    "after_image_url": "users/u-1/after.jpg",
                }
            ],
            users=[{"avatar_storage_key": "avatars/u-1/v1.jpg"}],
        )
        repo = UserRepository(sb)
        result = repo.list_user_storage_keys("u-1")

        assert set(result["raw-selfies"]) == {
            "users/u-1/raw/a.jpg",
            "users/u-1/raw/b.jpg",
        }
        assert set(result["images"]) == {
            "users/u-1/before.jpg",
            "users/u-1/after.jpg",
        }
        assert result["avatars"] == ["avatars/u-1/v1.jpg"]

    def test_ignores_missing_urls(self):
        sb, _ = _build_sb_serving(
            uploads=[{"image_url": None}, {"image_url": "users/u-1/raw/c.jpg"}],
            glowup_analyses=[{"before_image_url": None, "after_image_url": None}],
            users=[{"avatar_storage_key": None}],
        )
        repo = UserRepository(sb)
        result = repo.list_user_storage_keys("u-1")

        assert result["raw-selfies"] == ["users/u-1/raw/c.jpg"]
        assert result["images"] == []
        assert result["avatars"] == []


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
def list_user_storage_keys(self, user_id: str) -> dict[str, list[str]]:
    """Group every blob this user owns by bucket name.

    Called before the DB hard-delete so the keys can be enumerated while
    the owning rows still exist. Any row with a null URL is skipped.
    Buckets returned: ``raw-selfies`` (uploads), ``images`` (glowup
    before/after), ``avatars`` (profile avatar).
    """
    uploads = (
        self._sb.table("uploads")
        .select("image_url")
        .eq("user_id", user_id)
        .execute()
    )
    raw_selfies = [r["image_url"] for r in (uploads.data or []) if r.get("image_url")]

    glowups = (
        self._sb.table("glowup_analyses")
        .select("before_image_url, after_image_url")
        .eq("user_id", user_id)
        .execute()
    )
    images: list[str] = []
    for row in glowups.data or []:
        if row.get("before_image_url"):
            images.append(row["before_image_url"])
        if row.get("after_image_url"):
            images.append(row["after_image_url"])

    user = (
        self._sb.table("users")
        .select("avatar_storage_key")
        .eq("id", user_id)
        .execute()
    )
    avatars: list[str] = []
    for row in user.data or []:
        if row.get("avatar_storage_key"):
            avatars.append(row["avatar_storage_key"])

    return {"raw-selfies": raw_selfies, "images": images, "avatars": avatars}


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
  "SELECT column_name FROM information_schema.columns
    WHERE table_name IN ('uploads','glowup_analyses','users')
      AND column_name IN ('image_url','before_image_url','after_image_url','avatar_storage_key')
    ORDER BY table_name, column_name;"
```

Expected: all four column names appear on the matching tables. If a column is missing or named differently, update `list_user_storage_keys` + the test before continuing.

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
        repo.get_active_reservations.return_value = []
        repo.list_user_storage_keys.return_value = {
            "raw-selfies": ["users/u-1/raw/a.jpg"],
            "images": ["users/u-1/before.jpg"],
            "avatars": [],
        }
        repo.delete.return_value = [{"id": "u-1"}] if user_exists else []
        return repo

    @pytest.mark.asyncio
    async def test_happy_path_wipes_everything(self, monkeypatch):
        from app.api.auth import delete_account

        user_repo = self._make_user_repo()
        ledger = MagicMock()
        image_repo = MagicMock()
        orphan_repo = MagicMock()

        redis_client = MagicMock()
        redis_client.keys = AsyncMock(return_value=[])
        redis_client.delete = AsyncMock(return_value=1)

        resp = await delete_account(
            claims={"sub": "u-1"},
            user_repo=user_repo,
            image_repo=image_repo,
            orphan_repo=orphan_repo,
            ledger=ledger,
            redis_client=redis_client,
        )

        # Reservation inserted
        assert user_repo.insert_username_reservation.call_count == 1
        args, _ = user_repo.insert_username_reservation.call_args
        assert args[0] == user_repo.get_by_id.return_value["username"]
        reserved_until: datetime = args[1]
        assert reserved_until > datetime.now(tz=timezone.utc) + timedelta(days=179)

        # Blob wipe called per bucket
        assert image_repo.remove.call_args_list[0].args == (
            "raw-selfies",
            ["users/u-1/raw/a.jpg"],
        )
        assert image_repo.remove.call_args_list[1].args == (
            "images",
            ["users/u-1/before.jpg"],
        )
        orphan_repo.record.assert_not_called()

        # DB delete + auth delete
        user_repo.delete.assert_called_once_with("u-1")
        user_repo.auth_delete_user.assert_called_once_with("u-1")

        # 204
        assert resp.status_code == status.HTTP_204_NO_CONTENT

    @pytest.mark.asyncio
    async def test_blob_wipe_failure_falls_through_to_dlq(self):
        from app.api.auth import delete_account

        user_repo = self._make_user_repo()
        image_repo = MagicMock()
        image_repo.remove.side_effect = RuntimeError("boom")
        orphan_repo = MagicMock()
        ledger = MagicMock()

        redis_client = MagicMock()
        redis_client.keys = AsyncMock(return_value=[])
        redis_client.delete = AsyncMock(return_value=0)

        await delete_account(
            claims={"sub": "u-1"},
            user_repo=user_repo,
            image_repo=image_repo,
            orphan_repo=orphan_repo,
            ledger=ledger,
            redis_client=redis_client,
        )

        # Each failed key recorded in DLQ
        recorded = {
            (c.args[0], c.args[1]) for c in orphan_repo.record.call_args_list
        }
        assert ("raw-selfies", "users/u-1/raw/a.jpg") in recorded
        assert ("images", "users/u-1/before.jpg") in recorded

        # Delete still happens
        user_repo.delete.assert_called_once_with("u-1")

    @pytest.mark.asyncio
    async def test_already_deleted_raises_404(self):
        from app.api.auth import delete_account

        user_repo = self._make_user_repo(user_exists=False)
        image_repo = MagicMock()
        orphan_repo = MagicMock()
        ledger = MagicMock()
        redis_client = MagicMock()
        redis_client.keys = AsyncMock(return_value=[])
        redis_client.delete = AsyncMock(return_value=0)

        with pytest.raises(HTTPException) as exc:
            await delete_account(
                claims={"sub": "u-1"},
                user_repo=user_repo,
                image_repo=image_repo,
                orphan_repo=orphan_repo,
                ledger=ledger,
                redis_client=redis_client,
            )

        assert exc.value.status_code == status.HTTP_404_NOT_FOUND
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
# reservation, blob wipe, CASCADE, and Redis cleanup).
# ---------------------------------------------------------------------------


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_account(
    claims: UserClaims = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_user_repo),
    image_repo: ImageRepository = Depends(get_image_repo),
    orphan_repo: OrphanedStorageKeyRepository = Depends(get_orphaned_storage_repo),
    ledger: CreditLedger = Depends(get_credit_ledger),
    redis_client: aioredis.Redis = Depends(get_redis),
) -> Response:
    """Permanently delete the authenticated user and every owned artifact.

    Steps (all best-effort after the reservation is in place):
      1. Release active credit reservations.
      2. Collect blob keys from uploads + glowup_analyses + avatar.
      3. Insert 180-day username_reservations row (UPSERT).
      4. Wipe blobs per bucket; failures are recorded in the orphan DLQ.
      5. DELETE FROM users — cascades every owned row.
      6. Delete the Supabase auth identity.
      7. Clean Redis keys for the user.
    """
    user_id: str = claims["sub"]
    now_utc = datetime.now(tz=timezone.utc)
    reserved_until = now_utc + timedelta(days=settings.USERNAME_RESERVATION_DAYS)

    user = await run_sync(user_repo.get_by_id, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found.",
        )
    username: str = user["username"]

    # 1. Release active credit reservations
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

    # 2. Collect blob keys BEFORE the DB delete (cascade would make this
    #    impossible afterwards).
    try:
        keys_by_bucket = await run_sync(user_repo.list_user_storage_keys, user_id)
    except Exception as exc:
        logger.error("Failed to enumerate storage keys for %s: %s", user_id, exc)
        keys_by_bucket = {}

    # 3. Reserve the username (UPSERT — extends window on re-delete).
    try:
        await run_sync(user_repo.insert_username_reservation, username, reserved_until)
    except Exception as exc:
        logger.error("Reservation insert failed for %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account deletion failed — could not reserve username.",
        ) from exc

    # 4. Inline blob wipe, DLQ fallback on failure.
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

    # 5. Hard-delete the user row (cascades to every owned table).
    try:
        deleted = await run_sync(user_repo.delete, user_id)
        if not deleted:
            # Rare race: row disappeared between get_by_id and delete.
            # Reservation is already in place, so treat as idempotent 204.
            logger.info("delete_account: user %s already gone", user_id)
            return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as exc:
        logger.error("users DELETE failed for %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account deletion failed.",
        ) from exc

    # 6. Remove Supabase auth identity.
    try:
        await run_sync(user_repo.auth_delete_user, user_id)
        logger.info(
            "Account hard-deleted for user %s (username=%s reserved until %s)",
            user_id,
            username,
            reserved_until.date(),
        )
    except Exception as exc:
        logger.error("auth.admin.delete_user failed for %s: %s", user_id, exc)
        # DB already committed; nightly cleanup can retry via auth admin later.

    # 7. Redis cleanup.
    try:
        redis_keys_to_delete = [
            f"advisor_chat_rate:{user_id}",
            f"concurrent:{user_id}",
        ]
        daily_keys = await redis_client.keys(f"gen:user_daily:{user_id}:*")
        if daily_keys:
            redis_keys_to_delete.extend(daily_keys)
        if redis_keys_to_delete:
            await redis_client.delete(*redis_keys_to_delete)
    except Exception as exc:
        logger.warning("Redis cleanup failed for deleted user %s: %s", user_id, exc)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

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

Expected: 3 passed.

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

- [ ] **Step 1: Confirm which singletons expose `clear()`**

```bash
cd mobile && rtk grep "export.*clear\b\|clear(): void\|clear(): Promise" lib --type ts
```

Expected: hits in `dismissed-jobs-store.ts`, `refund-toast-store.ts`, `offline-queue.ts`. If any file does not expose a `clear()` method, add one at the top of that file as a prerequisite step — the unit test below will enforce it.

- [ ] **Step 2: Write the failing test**

Create `mobile/lib/__tests__/account-wipe.test.ts`:

```ts
import AsyncStorage from "@react-native-async-storage/async-storage";

import * as secureStorage from "../secure-storage";
import * as dismissedJobs from "../dismissed-jobs-store";
import * as refundToast from "../refund-toast-store";
import * as offlineQueue from "../offline-queue";
import { queryClient } from "../query-client";
import { SECURE_STORE_KEYS } from "../../constants/config";
import {
  PROFILE_DISMISSED_ERRORED_JOBS_STORAGE_KEY,
  REFUND_TOAST_SEEN_STORAGE_KEY,
} from "../../constants/config";
import { wipeLocalDeviceState } from "../account-wipe";

jest.mock("@react-native-async-storage/async-storage", () => ({
  multiRemove: jest.fn().mockResolvedValue(undefined),
}));

describe("wipeLocalDeviceState", () => {
  beforeEach(() => {
    jest.spyOn(secureStorage, "deleteItem").mockResolvedValue(undefined);
    jest.spyOn(dismissedJobs.dismissedJobsStore, "clear").mockReturnValue(undefined);
    jest.spyOn(refundToast.refundToastStore, "clear").mockReturnValue(undefined);
    jest.spyOn(offlineQueue.offlineQueue, "clear").mockReturnValue(undefined);
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

    expect(dismissedJobs.dismissedJobsStore.clear).toHaveBeenCalledTimes(1);
    expect(refundToast.refundToastStore.clear).toHaveBeenCalledTimes(1);
    expect(offlineQueue.offlineQueue.clear).toHaveBeenCalledTimes(1);
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
 * Adding new client-local state?  Wire it in here.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";

import { SECURE_STORE_KEYS } from "../constants/config";
import {
  PROFILE_DISMISSED_ERRORED_JOBS_STORAGE_KEY,
  REFUND_TOAST_SEEN_STORAGE_KEY,
} from "../constants/config";
import { deleteItem } from "./secure-storage";
import { dismissedJobsStore } from "./dismissed-jobs-store";
import { refundToastStore } from "./refund-toast-store";
import { offlineQueue } from "./offline-queue";
import { queryClient } from "./query-client";

export async function wipeLocalDeviceState(): Promise<void> {
  await Promise.all(
    Object.values(SECURE_STORE_KEYS).map((key) => deleteItem(key)),
  );

  await AsyncStorage.multiRemove([
    PROFILE_DISMISSED_ERRORED_JOBS_STORAGE_KEY,
    REFUND_TOAST_SEEN_STORAGE_KEY,
  ]);

  dismissedJobsStore.clear();
  refundToastStore.clear();
  offlineQueue.clear();
  queryClient.clear();
}
```

> If any of `dismissedJobsStore` / `refundToastStore` / `offlineQueue` is exported under a different name, update the import + the test to match. Do not rename the singletons in other files as part of this task.

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

If `mobile/jest.setup.ts` does not auto-confirm destructive `Alert.alert` prompts, add:

```ts
import { Alert } from "react-native";

jest.spyOn(Alert, "alert").mockImplementation((_title, _message, buttons) => {
  buttons?.find((b) => b.style === "destructive")?.onPress?.();
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd mobile && npx jest app/__tests__/settings-delete.test.tsx
```

Expected: FAIL — `wipeLocalDeviceState` is not imported yet in `settings.tsx`.

- [ ] **Step 3: Wire it in**

In `mobile/app/settings.tsx`:

Add import:

```ts
import { wipeLocalDeviceState } from "../lib/account-wipe";
```

Replace the body of `handleDeleteAccount`'s `onPress` with:

```ts
onPress: async () => {
  setIsDeleting(true);
  try {
    await apiFetch<void>("/v1/auth/account", { method: "DELETE" });
    await wipeLocalDeviceState();
    setSessionMode("anon");
    router.replace("/(auth)/login");
  } catch (err) {
    const appError = parseApiError(err);
    showToast({ kind: "error", message: appError.message });
  } finally {
    setIsDeleting(false);
  }
},
```

Remove the old `clearAllTokens()` call — `wipeLocalDeviceState` covers token deletion via `SECURE_STORE_KEYS`. Leave `clearAllTokens` itself intact; logout still uses it.

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
