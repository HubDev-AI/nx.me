"""Tests for the hard-delete ``delete_account`` endpoint.

Validates the critical ordering guaranteed by ``app/api/auth.py::delete_account``:

1. Supabase auth identity is deleted **before** any DB row write.
2. Blob wipe runs **before** the DB ``DELETE`` (so cascade loss is irrelevant).
3. ``insert_username_reservation`` runs **only after** the DB ``DELETE`` returned a row.

Also covers the DLQ fall-through on blob errors, the large-user ARQ offload,
and idempotent 204 for a user that was already deleted.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

try:
    from app.api.auth import delete_account, _INLINE_BLOB_WIPE_THRESHOLD
    from fastapi import HTTPException, status

    _AUTH_AVAILABLE = True
except (ImportError, AttributeError):
    _AUTH_AVAILABLE = False

from tests.conftest import requires_routers

pytestmark = [
    pytest.mark.skipif(not _AUTH_AVAILABLE, reason="auth module unavailable"),
    requires_routers,
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_USER_ID = "u-1"
_USERNAME = "alice"


def _make_user_repo(user_exists: bool = True) -> MagicMock:
    """Build a UserRepository mock with happy-path defaults."""
    repo = MagicMock()
    repo.get_profile_by_id.return_value = (
        {"id": _USER_ID, "username": _USERNAME} if user_exists else None
    )
    repo.get_active_reservations.return_value = []
    repo.list_user_storage_keys.return_value = {
        "raw-selfies": ["a.jpg"],
        "generated-images": ["b.jpg"],
        "post-images": [],
        "avatars": [],
    }
    repo.auth_delete_user.return_value = None
    repo.delete.return_value = [{"id": _USER_ID}] if user_exists else []
    repo.insert_username_reservation.return_value = None
    return repo


class _EmptyScanIter:
    """Async iterator that yields no Redis keys — used for scan_iter mock."""

    def __aiter__(self) -> "_EmptyScanIter":
        return self

    async def __anext__(self) -> str:
        raise StopAsyncIteration


class _FakeRedisPipeline:
    """Minimal async-compatible pipeline stub for rate-limiter tests.

    `pipeline()` chains incr/expire synchronously; `execute()` is awaitable
    and returns ``[1, True]`` so the first call is always within the limit.
    """

    def __init__(self) -> None:
        self._count = 1  # INCR return value — always 1 (first attempt)

    def incr(self, key: str) -> "_FakeRedisPipeline":
        return self

    def expire(self, key: str, ttl: int, nx: bool = False) -> "_FakeRedisPipeline":
        return self

    async def execute(self) -> list:
        return [self._count, True]


def _make_deps() -> SimpleNamespace:
    """Build image/orphan/ledger/redis/arq mocks with safe defaults."""
    image_repo = MagicMock()
    image_repo.remove.return_value = None
    orphan_repo = MagicMock()
    orphan_repo.record.return_value = None
    ledger = MagicMock()
    ledger.release.return_value = None

    redis_client = MagicMock()
    redis_client.scan_iter = MagicMock(return_value=_EmptyScanIter())
    redis_client.delete = AsyncMock(return_value=None)
    # Rate-limiter pipeline — returns count=1 (always within limit by default)
    redis_client.pipeline = MagicMock(side_effect=lambda: _FakeRedisPipeline())
    redis_client.ttl = AsyncMock(return_value=0)

    arq_pool = MagicMock()
    arq_pool.enqueue_job = AsyncMock(return_value=None)

    return SimpleNamespace(
        image_repo=image_repo,
        orphan_repo=orphan_repo,
        ledger=ledger,
        redis_client=redis_client,
        arq_pool=arq_pool,
    )


def _make_claims() -> dict:
    return {"sub": _USER_ID}


async def _passthrough_run_sync(fn, *args, **kwargs):
    return fn(*args, **kwargs)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHardDeleteAccount:
    """Endpoint-level tests — call ``delete_account`` directly with mocked deps."""

    @pytest.mark.asyncio
    async def test_happy_path_auth_delete_before_db_and_reservation_after(
        self, monkeypatch
    ):
        """Critical ordering: auth -> blob -> db -> reservation."""
        monkeypatch.setattr("app.api.auth.run_sync", _passthrough_run_sync)

        user_repo = _make_user_repo(user_exists=True)
        deps = _make_deps()
        call_order: list[str] = []

        def _auth(*_a, **_k):
            call_order.append("auth")

        def _blob(*_a, **_k):
            call_order.append("blob")

        def _db(*_a, **_k):
            call_order.append("db")
            return [{"id": _USER_ID}]

        def _reservation(*_a, **_k):
            call_order.append("reservation")

        user_repo.auth_delete_user.side_effect = _auth
        deps.image_repo.remove.side_effect = _blob
        user_repo.delete.side_effect = _db
        user_repo.insert_username_reservation.side_effect = _reservation

        response = await delete_account(
            claims=_make_claims(),
            user_repo=user_repo,
            image_repo=deps.image_repo,
            orphan_repo=deps.orphan_repo,
            ledger=deps.ledger,
            redis_client=deps.redis_client,
            arq_pool=deps.arq_pool,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        # Auth identity must die before the DB row.
        assert call_order.index("auth") < call_order.index("db")
        # Blob wipe must run before the DB row so keys are still enumerated.
        assert call_order.index("blob") < call_order.index("db")
        # Reservation only after the DB DELETE returned a row.
        assert call_order.index("db") < call_order.index("reservation")

    @pytest.mark.asyncio
    async def test_reservation_uses_profile_username(self, monkeypatch):
        """insert_username_reservation must use the username fetched from the profile."""
        monkeypatch.setattr("app.api.auth.run_sync", _passthrough_run_sync)

        user_repo = _make_user_repo(user_exists=True)
        deps = _make_deps()

        await delete_account(
            claims=_make_claims(),
            user_repo=user_repo,
            image_repo=deps.image_repo,
            orphan_repo=deps.orphan_repo,
            ledger=deps.ledger,
            redis_client=deps.redis_client,
            arq_pool=deps.arq_pool,
        )

        user_repo.insert_username_reservation.assert_called_once()
        assert user_repo.insert_username_reservation.call_args.args[0] == _USERNAME

    @pytest.mark.asyncio
    async def test_auth_delete_failure_raises_502_and_skips_db_delete(
        self, monkeypatch
    ):
        """Auth identity failure must leave the DB row intact so the client can retry."""
        monkeypatch.setattr("app.api.auth.run_sync", _passthrough_run_sync)

        user_repo = _make_user_repo(user_exists=True)
        deps = _make_deps()
        user_repo.auth_delete_user.side_effect = RuntimeError("supabase boom")

        with pytest.raises(HTTPException) as exc_info:
            await delete_account(
                claims=_make_claims(),
                user_repo=user_repo,
                image_repo=deps.image_repo,
                orphan_repo=deps.orphan_repo,
                ledger=deps.ledger,
                redis_client=deps.redis_client,
                arq_pool=deps.arq_pool,
            )

        assert exc_info.value.status_code == status.HTTP_502_BAD_GATEWAY
        user_repo.delete.assert_not_called()
        user_repo.insert_username_reservation.assert_not_called()

    @pytest.mark.asyncio
    async def test_blob_wipe_failure_falls_through_to_dlq(self, monkeypatch):
        """Blob wipe failure must DLQ each key and still run the DB DELETE."""
        monkeypatch.setattr("app.api.auth.run_sync", _passthrough_run_sync)

        user_repo = _make_user_repo(user_exists=True)
        deps = _make_deps()
        deps.image_repo.remove.side_effect = RuntimeError("s3 down")

        response = await delete_account(
            claims=_make_claims(),
            user_repo=user_repo,
            image_repo=deps.image_repo,
            orphan_repo=deps.orphan_repo,
            ledger=deps.ledger,
            redis_client=deps.redis_client,
            arq_pool=deps.arq_pool,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        # Each key that couldn't be removed must be recorded in the DLQ.
        recorded = {
            (call.args[0], call.args[1])
            for call in deps.orphan_repo.record.call_args_list
        }
        assert ("raw-selfies", "a.jpg") in recorded
        assert ("generated-images", "b.jpg") in recorded
        # DB DELETE is best-effort after a blob failure.
        user_repo.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_large_user_offloads_blob_wipe_to_arq(self, monkeypatch):
        """Above the inline threshold the wipe must be offloaded to ARQ."""
        monkeypatch.setattr("app.api.auth.run_sync", _passthrough_run_sync)

        big_user_blobs = _INLINE_BLOB_WIPE_THRESHOLD + 100
        user_repo = _make_user_repo(user_exists=True)
        keys_by_bucket = {
            "raw-selfies": [f"k-{i}.jpg" for i in range(big_user_blobs)],
            "generated-images": [],
            "post-images": [],
            "avatars": [],
        }
        user_repo.list_user_storage_keys.return_value = keys_by_bucket
        deps = _make_deps()

        response = await delete_account(
            claims=_make_claims(),
            user_repo=user_repo,
            image_repo=deps.image_repo,
            orphan_repo=deps.orphan_repo,
            ledger=deps.ledger,
            redis_client=deps.redis_client,
            arq_pool=deps.arq_pool,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        deps.image_repo.remove.assert_not_called()
        deps.arq_pool.enqueue_job.assert_called_once()
        call = deps.arq_pool.enqueue_job.call_args
        assert call.args[0] == "wipe_deleted_user_blobs"
        assert call.kwargs["user_id"] == _USER_ID
        assert call.kwargs["keys_by_bucket"] == keys_by_bucket
        assert call.kwargs["_job_id"] == f"delete_account:{_USER_ID}"

    @pytest.mark.asyncio
    async def test_already_deleted_is_idempotent_204(self, monkeypatch):
        """Second call on a user that's already gone must 204 without side effects."""
        monkeypatch.setattr("app.api.auth.run_sync", _passthrough_run_sync)

        user_repo = _make_user_repo(user_exists=False)
        deps = _make_deps()

        response = await delete_account(
            claims=_make_claims(),
            user_repo=user_repo,
            image_repo=deps.image_repo,
            orphan_repo=deps.orphan_repo,
            ledger=deps.ledger,
            redis_client=deps.redis_client,
            arq_pool=deps.arq_pool,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        user_repo.auth_delete_user.assert_not_called()
        user_repo.delete.assert_not_called()
        user_repo.insert_username_reservation.assert_not_called()

    @pytest.mark.asyncio
    async def test_db_delete_failure_raises_500(self, monkeypatch):
        """DB-level failure after auth-delete must surface as HTTP 500."""
        monkeypatch.setattr("app.api.auth.run_sync", _passthrough_run_sync)

        user_repo = _make_user_repo(user_exists=True)
        deps = _make_deps()
        user_repo.delete.side_effect = RuntimeError("postgres down")

        with pytest.raises(HTTPException) as exc_info:
            await delete_account(
                claims=_make_claims(),
                user_repo=user_repo,
                image_repo=deps.image_repo,
                orphan_repo=deps.orphan_repo,
                ledger=deps.ledger,
                redis_client=deps.redis_client,
                arq_pool=deps.arq_pool,
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        # Auth-delete ran first; reservation must NOT run because no row
        # actually got deleted.
        user_repo.auth_delete_user.assert_called_once()
        user_repo.insert_username_reservation.assert_not_called()

    @pytest.mark.asyncio
    async def test_row_vanished_mid_flow_returns_204_without_reservation(
        self, monkeypatch
    ):
        """Auth-delete succeeds but ``user_repo.delete`` returns [] — benign race.

        Some other actor (another delete request, a DB trigger) already
        dropped the row between ``get_profile_by_id`` and the DELETE. We
        return 204 without writing a reservation — because no row was
        deleted here, writing one now would collide with the reservation
        that the winning request already inserted.
        """
        monkeypatch.setattr("app.api.auth.run_sync", _passthrough_run_sync)

        user_repo = _make_user_repo(user_exists=True)
        deps = _make_deps()
        user_repo.delete.return_value = []  # Row vanished between steps.

        response = await delete_account(
            claims=_make_claims(),
            user_repo=user_repo,
            image_repo=deps.image_repo,
            orphan_repo=deps.orphan_repo,
            ledger=deps.ledger,
            redis_client=deps.redis_client,
            arq_pool=deps.arq_pool,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        user_repo.auth_delete_user.assert_called_once()
        user_repo.insert_username_reservation.assert_not_called()

    @pytest.mark.asyncio
    async def test_blob_enumeration_failure_raises_500_before_auth_delete(
        self, monkeypatch
    ):
        """Storage enumeration failure must HALT the flow — do NOT auth-delete."""
        monkeypatch.setattr("app.api.auth.run_sync", _passthrough_run_sync)

        user_repo = _make_user_repo(user_exists=True)
        user_repo.list_user_storage_keys.side_effect = RuntimeError("listing failed")
        deps = _make_deps()

        with pytest.raises(HTTPException) as exc_info:
            await delete_account(
                claims=_make_claims(),
                user_repo=user_repo,
                image_repo=deps.image_repo,
                orphan_repo=deps.orphan_repo,
                ledger=deps.ledger,
                redis_client=deps.redis_client,
                arq_pool=deps.arq_pool,
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        # The point of failing fast: auth-delete must NOT run — otherwise
        # the account goes away with zero blob wipes and the user has no
        # way to retry the wipe from the client.
        user_repo.auth_delete_user.assert_not_called()
        user_repo.delete.assert_not_called()
        user_repo.insert_username_reservation.assert_not_called()

    @pytest.mark.asyncio
    async def test_rate_limit_returns_429_after_threshold(self, monkeypatch):
        """Fourth call within 10 minutes → 429 before any DB work."""
        monkeypatch.setattr("app.api.auth.run_sync", _passthrough_run_sync)

        from app.services.rate_limiter import _DELETE_ACCOUNT_MAX_ATTEMPTS

        user_repo = _make_user_repo()
        deps = _make_deps()

        # Wire a stateful pipeline that increments a real counter so we can
        # drive it past the threshold without actually running Redis.
        call_count = 0

        class _CountingPipeline:
            def __init__(self) -> None:
                nonlocal call_count
                call_count += 1
                self._count = call_count

            def incr(self, key: str) -> "_CountingPipeline":
                return self

            def expire(self, key: str, ttl: int, nx: bool = False) -> "_CountingPipeline":
                return self

            async def execute(self) -> list:
                return [self._count, True]

        deps.redis_client.pipeline = MagicMock(
            side_effect=lambda: _CountingPipeline()
        )
        deps.redis_client.ttl = AsyncMock(return_value=120)

        # First `threshold` calls should succeed (rate limit not exceeded)
        for _ in range(_DELETE_ACCOUNT_MAX_ATTEMPTS):
            user_repo.get_profile_by_id.return_value = {
                "id": _USER_ID,
                "username": _USERNAME,
            }
            user_repo.delete.return_value = [{"id": _USER_ID}]
            user_repo.insert_username_reservation.return_value = None
            user_repo.get_active_reservations.return_value = []
            user_repo.list_user_storage_keys.return_value = {
                "raw-selfies": [],
                "generated-images": [],
                "post-images": [],
                "avatars": [],
            }
            await delete_account(
                claims={"sub": _USER_ID},
                user_repo=user_repo,
                image_repo=deps.image_repo,
                orphan_repo=deps.orphan_repo,
                ledger=deps.ledger,
                redis_client=deps.redis_client,
                arq_pool=deps.arq_pool,
            )

        # The next call should be rate-limited
        with pytest.raises(HTTPException) as exc:
            await delete_account(
                claims={"sub": _USER_ID},
                user_repo=user_repo,
                image_repo=deps.image_repo,
                orphan_repo=deps.orphan_repo,
                ledger=deps.ledger,
                redis_client=deps.redis_client,
                arq_pool=deps.arq_pool,
            )
        assert exc.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert exc.value.headers.get("Retry-After") == "120"

    @pytest.mark.asyncio
    async def test_arq_dedup_none_return_logs_warning_and_continues(
        self, monkeypatch, caplog
    ):
        """ARQ dedup (enqueue_job returns None) must not abort the delete flow."""
        monkeypatch.setattr("app.api.auth.run_sync", _passthrough_run_sync)

        big_user_blobs = _INLINE_BLOB_WIPE_THRESHOLD + 1
        user_repo = _make_user_repo(user_exists=True)
        user_repo.list_user_storage_keys.return_value = {
            "raw-selfies": [f"k-{i}.jpg" for i in range(big_user_blobs)],
            "generated-images": [],
            "post-images": [],
            "avatars": [],
        }
        deps = _make_deps()
        deps.arq_pool.enqueue_job = AsyncMock(return_value=None)

        with caplog.at_level(logging.WARNING, logger="app.api.auth"):
            response = await delete_account(
                claims=_make_claims(),
                user_repo=user_repo,
                image_repo=deps.image_repo,
                orphan_repo=deps.orphan_repo,
                ledger=deps.ledger,
                redis_client=deps.redis_client,
                arq_pool=deps.arq_pool,
            )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        # DB delete + reservation must still run — the dedup is only a
        # blob-wipe scheduling concern, not a showstopper.
        user_repo.delete.assert_called_once()
        user_repo.insert_username_reservation.assert_called_once()
        assert any(
            "deduped" in rec.message and rec.levelno == logging.WARNING
            for rec in caplog.records
        )
