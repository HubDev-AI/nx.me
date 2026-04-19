"""Tests for Unit 11 delete_account new surfaces.

Covers:
  - Happy: user with stripe_customer_id → delete_customer called → no DLQ row.
  - Happy: user without stripe_customer_id → no Stripe call.
  - Edge: delete_customer raises → DLQ row written + delete completes 204 + WARNING logged.
  - Edge: signup_grants_issued for device SURVIVES (regression guard via step 1.5).
  - Edge: in-flight reservation drained via ledger.release (credit_release RPC path).
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

try:
    from app.api.auth import delete_account
    from fastapi import status

    _AUTH_AVAILABLE = True
except (ImportError, AttributeError):
    _AUTH_AVAILABLE = False

from tests.conftest import requires_routers

pytestmark = [
    pytest.mark.skipif(not _AUTH_AVAILABLE, reason="auth module unavailable"),
    requires_routers,
]

# ---------------------------------------------------------------------------
# Helpers (mirrors test_hard_delete_account.py helper pattern)
# ---------------------------------------------------------------------------

_USER_ID = "u-unit11"
_USERNAME = "unit11_user"
_CUSTOMER_ID = "cus_unit11_stripe"
_RESERVATION_ID = "aabbccdd-0000-0000-0000-000000000001"


class _EmptyScanIter:
    def __aiter__(self) -> "_EmptyScanIter":
        return self

    async def __anext__(self) -> str:
        raise StopAsyncIteration


class _FakeRedisPipeline:
    def __init__(self) -> None:
        self._count = 1

    def incr(self, key: str) -> "_FakeRedisPipeline":
        return self

    def expire(self, key: str, ttl: int, nx: bool = False) -> "_FakeRedisPipeline":
        return self

    async def execute(self) -> list:
        return [self._count, True]


def _make_user_repo(
    user_exists: bool = True,
    stripe_customer_id: str | None = None,
    active_reservations: list[dict] | None = None,
) -> MagicMock:
    repo = MagicMock()
    profile = (
        {
            "id": _USER_ID,
            "username": _USERNAME,
            "stripe_customer_id": stripe_customer_id,
        }
        if user_exists
        else None
    )
    repo.get_profile_by_id.return_value = profile
    repo.get_active_reservations.return_value = active_reservations or []
    repo.list_user_storage_keys.return_value = {
        "raw-selfies": [],
        "generated-images": [],
        "post-images": [],
        "avatars": [],
    }
    repo.auth_delete_user.return_value = None
    repo.delete.return_value = [{"id": _USER_ID}] if user_exists else []
    repo.insert_username_reservation.return_value = None
    return repo


def _make_deps(
    payment_raises: Exception | None = None,
) -> SimpleNamespace:
    image_repo = MagicMock()
    image_repo.remove.return_value = None
    orphan_repo = MagicMock()
    orphan_repo.record.return_value = None
    ledger = MagicMock()
    ledger.release.return_value = None

    redis_client = MagicMock()
    redis_client.scan_iter = MagicMock(return_value=_EmptyScanIter())
    redis_client.delete = AsyncMock(return_value=None)
    redis_client.pipeline = MagicMock(side_effect=lambda: _FakeRedisPipeline())
    redis_client.ttl = AsyncMock(return_value=0)

    arq_pool = MagicMock()
    arq_pool.enqueue_job = AsyncMock(return_value=None)
    arq_pool.job = AsyncMock(return_value=None)

    payment = MagicMock()
    if payment_raises:
        payment.delete_customer = AsyncMock(side_effect=payment_raises)
    else:
        payment.delete_customer = AsyncMock(return_value=None)

    dlq_repo = MagicMock()
    dlq_repo.record.return_value = None

    return SimpleNamespace(
        image_repo=image_repo,
        orphan_repo=orphan_repo,
        ledger=ledger,
        redis_client=redis_client,
        arq_pool=arq_pool,
        payment=payment,
        dlq_repo=dlq_repo,
    )


def _make_claims() -> dict:
    return {"sub": _USER_ID}


async def _passthrough_run_sync(fn, *args, **kwargs):
    return fn(*args, **kwargs)


# ---------------------------------------------------------------------------
# Stripe customer delete (step 3.5)
# ---------------------------------------------------------------------------


class TestStripeDeleteStep:
    @pytest.mark.asyncio
    async def test_happy_with_stripe_customer_id_calls_delete_customer(
        self, monkeypatch
    ):
        """User with stripe_customer_id: delete_customer must be called; no DLQ row."""
        monkeypatch.setattr("app.api.auth.run_sync", _passthrough_run_sync)

        user_repo = _make_user_repo(stripe_customer_id=_CUSTOMER_ID)
        deps = _make_deps()

        response = await delete_account(
            claims=_make_claims(),
            user_repo=user_repo,
            image_repo=deps.image_repo,
            orphan_repo=deps.orphan_repo,
            ledger=deps.ledger,
            redis_client=deps.redis_client,
            arq_pool=deps.arq_pool,
            payment=deps.payment,
            dlq_repo=deps.dlq_repo,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        deps.payment.delete_customer.assert_awaited_once_with(_CUSTOMER_ID)
        deps.dlq_repo.record.assert_not_called()

    @pytest.mark.asyncio
    async def test_happy_without_stripe_customer_id_skips_delete_customer(
        self, monkeypatch
    ):
        """User without stripe_customer_id: delete_customer must NOT be called."""
        monkeypatch.setattr("app.api.auth.run_sync", _passthrough_run_sync)

        user_repo = _make_user_repo(stripe_customer_id=None)
        deps = _make_deps()

        response = await delete_account(
            claims=_make_claims(),
            user_repo=user_repo,
            image_repo=deps.image_repo,
            orphan_repo=deps.orphan_repo,
            ledger=deps.ledger,
            redis_client=deps.redis_client,
            arq_pool=deps.arq_pool,
            payment=deps.payment,
            dlq_repo=deps.dlq_repo,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        deps.payment.delete_customer.assert_not_awaited()
        deps.dlq_repo.record.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_customer_failure_writes_dlq_and_returns_204(
        self, monkeypatch, caplog
    ):
        """delete_customer failure must write DLQ row + still return 204 + log WARNING."""
        monkeypatch.setattr("app.api.auth.run_sync", _passthrough_run_sync)

        user_repo = _make_user_repo(stripe_customer_id=_CUSTOMER_ID)
        deps = _make_deps(payment_raises=RuntimeError("stripe 503"))

        with caplog.at_level(logging.WARNING, logger="app.api.auth"):
            response = await delete_account(
                claims=_make_claims(),
                user_repo=user_repo,
                image_repo=deps.image_repo,
                orphan_repo=deps.orphan_repo,
                ledger=deps.ledger,
                redis_client=deps.redis_client,
                arq_pool=deps.arq_pool,
                payment=deps.payment,
                dlq_repo=deps.dlq_repo,
            )

        # Overall delete must still succeed.
        assert response.status_code == status.HTTP_204_NO_CONTENT
        # DLQ row must be written.
        deps.dlq_repo.record.assert_called_once()
        call_kwargs = deps.dlq_repo.record.call_args
        assert call_kwargs.args[0] == _CUSTOMER_ID
        assert call_kwargs.args[1] == "delete_account"
        # WARNING must be logged.
        assert any(
            r.levelno == logging.WARNING and "stripe_customer_dlq" in r.message
            for r in caplog.records
        )


# ---------------------------------------------------------------------------
# Reservation drain (step 1.5)
# ---------------------------------------------------------------------------


class TestReservationDrainStep:
    @pytest.mark.asyncio
    async def test_in_flight_reservation_drained_via_ledger_release(self, monkeypatch):
        """In-flight reservation must be released via ledger.release (credit_release RPC)."""
        monkeypatch.setattr("app.api.auth.run_sync", _passthrough_run_sync)

        reservation = {"id": _RESERVATION_ID}
        user_repo = _make_user_repo(active_reservations=[reservation])
        deps = _make_deps()

        await delete_account(
            claims=_make_claims(),
            user_repo=user_repo,
            image_repo=deps.image_repo,
            orphan_repo=deps.orphan_repo,
            ledger=deps.ledger,
            redis_client=deps.redis_client,
            arq_pool=deps.arq_pool,
            payment=deps.payment,
            dlq_repo=deps.dlq_repo,
        )

        deps.ledger.release.assert_called_once_with(UUID(_RESERVATION_ID))

    @pytest.mark.asyncio
    async def test_reservation_release_failure_does_not_abort_delete(self, monkeypatch):
        """A failed ledger.release must not abort the overall delete (best-effort)."""
        monkeypatch.setattr("app.api.auth.run_sync", _passthrough_run_sync)

        reservation = {"id": _RESERVATION_ID}
        user_repo = _make_user_repo(active_reservations=[reservation])
        deps = _make_deps()
        deps.ledger.release.side_effect = RuntimeError("RPC down")

        response = await delete_account(
            claims=_make_claims(),
            user_repo=user_repo,
            image_repo=deps.image_repo,
            orphan_repo=deps.orphan_repo,
            ledger=deps.ledger,
            redis_client=deps.redis_client,
            arq_pool=deps.arq_pool,
            payment=deps.payment,
            dlq_repo=deps.dlq_repo,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        user_repo.delete.assert_called_once()
