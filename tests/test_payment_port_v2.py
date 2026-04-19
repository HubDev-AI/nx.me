"""Tests for PaymentPort v2 additions: retrieve_subscription, delete_customer,
and the column-first ``_get_or_create_customer`` rewrite.

Exercises production code in:
  - app/payment/ports.py (SubscriptionSnapshot, PaymentFetchError)
  - app/payment/adapters/mock.py (MockPaymentAdapter)
  - app/payment/adapters/stripe_adapter.py (StripePaymentAdapter)

The StripePaymentAdapter tests replace ``adapter._stripe`` with a MagicMock
after construction rather than contacting the real API. A small fake Stripe
module supplies error classes (StripeError, InvalidRequestError) that the
adapter catches so test scenarios can simulate provider failures.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.payment.adapters.mock import MockPaymentAdapter
from app.payment.ports import (
    PaymentFetchError,
    SubscriptionSnapshot,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeStripeError(Exception):
    """Base class used by the fake stripe module below."""


class _FakeInvalidRequestError(_FakeStripeError):
    """Stand-in for stripe.error.InvalidRequestError.

    Exposes ``.code`` so the adapter's ``resource_missing`` branch can be
    exercised without pulling in the real Stripe SDK.
    """

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


def _install_fake_stripe(adapter) -> MagicMock:
    """Swap the adapter's lazily-imported stripe module for a mock.

    The mock exposes the exception classes the adapter catches plus a
    ``Customer``/``Subscription`` surface the tests can configure per call.
    """
    fake = MagicMock()
    fake.StripeError = _FakeStripeError
    fake.InvalidRequestError = _FakeInvalidRequestError
    fake.SignatureVerificationError = type("SigErr", (Exception,), {})
    adapter._stripe = fake
    return fake


def _make_snapshot(
    sub_id: str = "sub_test_123",
    customer_id: str = "cus_test_abc",
    status: str = "active",
    cancel_at_period_end: bool = False,
    cancel_at: int | None = None,
) -> SubscriptionSnapshot:
    now = int(time.time())
    return SubscriptionSnapshot(
        id=sub_id,
        status=status,
        current_period_start=now - 3600,
        current_period_end=now + 86400,
        cancel_at_period_end=cancel_at_period_end,
        customer_id=customer_id,
        cancel_at=cancel_at,
    )


def _build_stripe_adapter(monkeypatch, supabase_client=None):
    """Construct a StripePaymentAdapter with a non-empty webhook secret.

    The adapter's __init__ raises when ``STRIPE_WEBHOOK_SECRET`` is empty,
    and it does ``import stripe`` at construction time. We patch the
    setting, let the import run, then replace ``adapter._stripe`` with a
    MagicMock so no further real Stripe calls happen.
    """
    from app.payment.adapters import stripe_adapter as sa

    monkeypatch.setattr(sa.settings, "STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(sa.settings, "STRIPE_API_KEY", "sk_test_fake")
    monkeypatch.setattr(sa.settings, "STRIPE_PUBLISHABLE_KEY", "pk_test_fake")

    adapter = sa.StripePaymentAdapter(supabase_client=supabase_client)
    _install_fake_stripe(adapter)
    return adapter


# ---------------------------------------------------------------------------
# MockPaymentAdapter tests
# ---------------------------------------------------------------------------


class TestMockRetrieveSubscription:
    """Mock-adapter coverage for retrieve_subscription + delete_customer."""

    @pytest.mark.asyncio
    async def test_retrieve_seeded_subscription_returns_snapshot(self):
        adapter = MockPaymentAdapter()
        seeded = _make_snapshot(sub_id="sub_mock_1", customer_id="cus_mock_1")
        adapter.set_subscription(seeded)

        result = await adapter.retrieve_subscription("sub_mock_1")

        assert isinstance(result, SubscriptionSnapshot)
        assert result.id == "sub_mock_1"
        assert result.customer_id == "cus_mock_1"
        assert result.status == "active"
        assert result.current_period_end > result.current_period_start
        assert result.cancel_at_period_end is False
        assert result.cancel_at is None

    @pytest.mark.asyncio
    async def test_retrieve_unknown_subscription_raises_payment_fetch_error(self):
        adapter = MockPaymentAdapter()

        with pytest.raises(PaymentFetchError):
            await adapter.retrieve_subscription("sub_missing")

    @pytest.mark.asyncio
    async def test_delete_customer_is_noop_and_idempotent(self):
        adapter = MockPaymentAdapter()

        # First call succeeds.
        await adapter.delete_customer("cus_mock_x")
        # Second call also succeeds — no state to reject replay.
        await adapter.delete_customer("cus_mock_x")


# ---------------------------------------------------------------------------
# StripePaymentAdapter.retrieve_subscription
# ---------------------------------------------------------------------------


class TestStripeRetrieveSubscription:
    """Adapter-level coverage for retrieve_subscription with a fake stripe."""

    @pytest.mark.asyncio
    async def test_happy_path_returns_typed_snapshot(self, monkeypatch):
        adapter = _build_stripe_adapter(monkeypatch)
        now = int(time.time())
        adapter._stripe.Subscription.retrieve.return_value = {
            "id": "sub_live_1",
            "status": "active",
            "current_period_start": now - 100,
            "current_period_end": now + 86400,
            "cancel_at_period_end": False,
            "customer": "cus_live_1",
            "cancel_at": None,
        }

        snapshot = await adapter.retrieve_subscription("sub_live_1", timeout=2.0)

        assert isinstance(snapshot, SubscriptionSnapshot)
        assert snapshot.id == "sub_live_1"
        assert snapshot.status == "active"
        assert snapshot.customer_id == "cus_live_1"
        assert snapshot.cancel_at_period_end is False
        assert snapshot.cancel_at is None
        # Stripe SDK was called with request_timeout kwarg.
        adapter._stripe.Subscription.retrieve.assert_called_once()
        _, kwargs = adapter._stripe.Subscription.retrieve.call_args
        assert kwargs.get("request_timeout") == 2.0

    @pytest.mark.asyncio
    async def test_expanded_customer_dict_is_flattened_to_id(self, monkeypatch):
        adapter = _build_stripe_adapter(monkeypatch)
        now = int(time.time())
        adapter._stripe.Subscription.retrieve.return_value = {
            "id": "sub_expand",
            "status": "past_due",
            "current_period_start": now - 100,
            "current_period_end": now + 100,
            "cancel_at_period_end": True,
            "customer": {"id": "cus_nested_2", "email": "x@example.com"},
            "cancel_at": now + 50,
        }

        snapshot = await adapter.retrieve_subscription("sub_expand")

        assert snapshot.customer_id == "cus_nested_2"
        assert snapshot.cancel_at_period_end is True
        assert snapshot.cancel_at == now + 50

    @pytest.mark.asyncio
    async def test_stripe_error_is_wrapped_in_payment_fetch_error(self, monkeypatch):
        adapter = _build_stripe_adapter(monkeypatch)
        adapter._stripe.Subscription.retrieve.side_effect = _FakeStripeError(
            "provider blew up"
        )

        with pytest.raises(PaymentFetchError) as exc_info:
            await adapter.retrieve_subscription("sub_bad")
        assert "sub_bad" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_timeout_raises_payment_fetch_error_within_upper_bound(
        self, monkeypatch
    ):
        adapter = _build_stripe_adapter(monkeypatch)

        def _slow_retrieve(*_args, **_kwargs):
            # Sleep long enough to blow the wait_for upper bound
            # (timeout + 0.5s slack).
            time.sleep(5.0)
            return {}

        adapter._stripe.Subscription.retrieve.side_effect = _slow_retrieve

        timeout = 0.2  # keep the test fast
        started = time.monotonic()
        with pytest.raises(PaymentFetchError):
            await adapter.retrieve_subscription("sub_slow", timeout=timeout)
        elapsed = time.monotonic() - started

        # Upper bound is timeout + 0.5s slack — give generous headroom
        # for the executor/dispatch overhead but fail if the adapter
        # silently blocked the full 5s sleep.
        assert elapsed < timeout + 1.5, (
            f"expected timeout within {timeout + 1.5:.2f}s, took {elapsed:.2f}s"
        )


# ---------------------------------------------------------------------------
# StripePaymentAdapter.delete_customer
# ---------------------------------------------------------------------------


class TestStripeDeleteCustomer:
    """Adapter-level coverage for delete_customer idempotency."""

    @pytest.mark.asyncio
    async def test_happy_path_calls_stripe_and_returns_none(self, monkeypatch):
        adapter = _build_stripe_adapter(monkeypatch)
        adapter._stripe.Customer.delete.return_value = {"id": "cus_x", "deleted": True}

        result = await adapter.delete_customer("cus_x")

        assert result is None
        adapter._stripe.Customer.delete.assert_called_once_with("cus_x")

    @pytest.mark.asyncio
    async def test_resource_missing_via_code_attribute_treated_as_success(
        self, monkeypatch
    ):
        adapter = _build_stripe_adapter(monkeypatch)
        adapter._stripe.Customer.delete.side_effect = _FakeInvalidRequestError(
            "No such customer: cus_gone",
            code="resource_missing",
        )

        # Must not raise — idempotent.
        await adapter.delete_customer("cus_gone")

    @pytest.mark.asyncio
    async def test_resource_missing_via_message_treated_as_success(self, monkeypatch):
        """Belt-and-braces: when ``.code`` isn't populated, the adapter
        still accepts the Stripe error message as the success signal."""
        adapter = _build_stripe_adapter(monkeypatch)
        adapter._stripe.Customer.delete.side_effect = _FakeInvalidRequestError(
            "resource_missing for cus_gone"
        )

        await adapter.delete_customer("cus_gone")

    @pytest.mark.asyncio
    async def test_other_invalid_request_errors_propagate(self, monkeypatch):
        adapter = _build_stripe_adapter(monkeypatch)
        adapter._stripe.Customer.delete.side_effect = _FakeInvalidRequestError(
            "invalid API key",
            code="invalid_request_error",
        )

        with pytest.raises(_FakeInvalidRequestError):
            await adapter.delete_customer("cus_x")


# ---------------------------------------------------------------------------
# StripePaymentAdapter._get_or_create_customer (column-first rewrite)
# ---------------------------------------------------------------------------


class _FakeSupabaseUsersTable:
    """Minimal supabase-shaped client for the ``users`` table.

    Supports the chains the adapter actually uses:
      .table('users').select(...).eq('id', ...).maybe_single().execute()
      .table('users').update({...}).eq('id', ...).execute()
    """

    def __init__(self, rows: dict[str, dict]) -> None:
        # user_id -> row dict (may contain stripe_customer_id)
        self.rows = rows
        # Track writes so tests can assert write-back.
        self.updates: list[tuple[str, dict]] = []

    def table(self, name: str) -> "_TableBuilder":
        assert name == "users", f"unexpected table {name}"
        return _TableBuilder(self)


class _TableBuilder:
    def __init__(self, parent: _FakeSupabaseUsersTable) -> None:
        self._parent = parent
        self._mode: str | None = None
        self._update_payload: dict | None = None
        self._eq_id: str | None = None

    def select(self, *_args, **_kwargs) -> "_TableBuilder":
        self._mode = "select"
        return self

    def update(self, payload: dict, **_kwargs) -> "_TableBuilder":
        self._mode = "update"
        self._update_payload = payload
        return self

    def eq(self, column: str, value: str) -> "_TableBuilder":
        assert column == "id", f"unexpected eq column {column}"
        self._eq_id = value
        return self

    def maybe_single(self) -> "_TableBuilder":
        return self

    def execute(self):
        if self._mode == "select":
            row = self._parent.rows.get(self._eq_id or "")
            return SimpleNamespace(data=row)
        if self._mode == "update":
            self._parent.updates.append(
                (self._eq_id or "", dict(self._update_payload or {}))
            )
            return SimpleNamespace(data=None)
        raise AssertionError(f"unexpected mode {self._mode!r}")


class TestGetOrCreateCustomer:
    """Column-first customer resolution with lazy-write-back."""

    @pytest.mark.asyncio
    async def test_populated_column_returns_immediately_no_stripe_calls(
        self, monkeypatch
    ):
        user_id = "11111111-2222-3333-4444-555555555555"
        fake_sb = _FakeSupabaseUsersTable(
            rows={user_id: {"stripe_customer_id": "cus_cached_hot"}}
        )
        adapter = _build_stripe_adapter(monkeypatch, supabase_client=fake_sb)

        result = await adapter._get_or_create_customer(user_id)

        assert result == "cus_cached_hot"
        # Zero Stripe calls on the fast path.
        adapter._stripe.Customer.search.assert_not_called()
        adapter._stripe.Customer.create.assert_not_called()
        # No write-back on hit — we already had the id.
        assert fake_sb.updates == []

    @pytest.mark.asyncio
    async def test_null_column_falls_back_to_search_and_writes_back(self, monkeypatch):
        user_id = "aaaa1111-bbbb-2222-cccc-3333dddd4444"
        fake_sb = _FakeSupabaseUsersTable(rows={user_id: {"stripe_customer_id": None}})
        adapter = _build_stripe_adapter(monkeypatch, supabase_client=fake_sb)
        adapter._stripe.Customer.search.return_value = {
            "data": [{"id": "cus_found_via_search"}]
        }

        result = await adapter._get_or_create_customer(user_id)

        assert result == "cus_found_via_search"
        adapter._stripe.Customer.search.assert_called_once()
        adapter._stripe.Customer.create.assert_not_called()
        # Column was written back with the discovered id.
        assert fake_sb.updates == [
            (user_id, {"stripe_customer_id": "cus_found_via_search"})
        ]

    @pytest.mark.asyncio
    async def test_missing_row_creates_customer_and_writes_back(self, monkeypatch):
        user_id = "bbbbcccc-dddd-eeee-ffff-000011112222"
        fake_sb = _FakeSupabaseUsersTable(rows={})  # no row at all
        adapter = _build_stripe_adapter(monkeypatch, supabase_client=fake_sb)
        adapter._stripe.Customer.search.return_value = {"data": []}
        adapter._stripe.Customer.create.return_value = {"id": "cus_fresh_create"}

        result = await adapter._get_or_create_customer(user_id)

        assert result == "cus_fresh_create"
        adapter._stripe.Customer.search.assert_called_once()
        adapter._stripe.Customer.create.assert_called_once()
        assert fake_sb.updates == [
            (user_id, {"stripe_customer_id": "cus_fresh_create"})
        ]

    @pytest.mark.asyncio
    async def test_adapter_without_supabase_client_uses_search_fallback(
        self, monkeypatch
    ):
        """Safety net: contexts without DB access still resolve customers."""
        adapter = _build_stripe_adapter(monkeypatch, supabase_client=None)
        adapter._stripe.Customer.search.return_value = {
            "data": [{"id": "cus_search_only"}]
        }

        result = await adapter._get_or_create_customer("user-without-db")

        assert result == "cus_search_only"
        adapter._stripe.Customer.search.assert_called_once()
        adapter._stripe.Customer.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_adapter_without_supabase_client_creates_on_search_miss(
        self, monkeypatch
    ):
        adapter = _build_stripe_adapter(monkeypatch, supabase_client=None)
        adapter._stripe.Customer.search.return_value = {"data": []}
        adapter._stripe.Customer.create.return_value = {"id": "cus_legacy_create"}

        result = await adapter._get_or_create_customer("user-legacy")

        assert result == "cus_legacy_create"
        adapter._stripe.Customer.search.assert_called_once()
        adapter._stripe.Customer.create.assert_called_once()


# ---------------------------------------------------------------------------
# Sanity: MockPaymentAdapter still satisfies the PaymentPort shape.
# ---------------------------------------------------------------------------


class TestProtocolShape:
    """Guard against drift: port additions must be present on both adapters."""

    @pytest.mark.asyncio
    async def test_mock_adapter_implements_new_methods(self):
        adapter = MockPaymentAdapter()
        # New methods exist and are awaitable.
        assert asyncio.iscoroutinefunction(adapter.retrieve_subscription)
        assert asyncio.iscoroutinefunction(adapter.delete_customer)

    def test_stripe_adapter_accepts_supabase_client_kwarg(self, monkeypatch):
        """Constructor signature accepts the new optional kwarg without
        breaking callers that construct it positionally."""
        adapter = _build_stripe_adapter(monkeypatch, supabase_client=None)
        assert adapter._supabase is None
        # With a client:
        sentinel = object()
        adapter2 = _build_stripe_adapter(monkeypatch, supabase_client=sentinel)
        assert adapter2._supabase is sentinel
