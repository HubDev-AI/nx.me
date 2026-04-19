"""Pure-function tests for derive_subscription_status state machine.

Exercises app/entitlement/service.py::derive_subscription_status.
No I/O, no mocks — just the state machine.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


from app.entitlement.models import SubscriptionStatus
from app.entitlement.service import derive_subscription_status

_NOW = datetime(2026, 4, 19, 12, 0, 0, tzinfo=timezone.utc)
_FUTURE = _NOW + timedelta(days=30)
_PAST = _NOW - timedelta(days=1)
_GRACE_FUTURE = _NOW + timedelta(days=7)


class TestDeriveLocked:
    def test_locked_overrides_active_sub(self):
        sub = {
            "status": "active",
            "billing_period_end": _FUTURE.isoformat(),
            "grace_until": None,
        }
        result = derive_subscription_status(
            sub, locked_at="2026-04-18T00:00:00Z", now=_NOW
        )
        assert result == SubscriptionStatus.LOCKED

    def test_locked_overrides_no_sub(self):
        result = derive_subscription_status(
            None, locked_at="2026-04-18T00:00:00Z", now=_NOW
        )
        assert result == SubscriptionStatus.LOCKED


class TestDeriveNoSub:
    def test_none_sub_no_lock_returns_none(self):
        result = derive_subscription_status(None, locked_at=None, now=_NOW)
        assert result == SubscriptionStatus.NONE


class TestDeriveCanceled:
    def test_cancelled_status_returns_canceled(self):
        sub = {
            "status": "cancelled",
            "billing_period_end": _FUTURE.isoformat(),
            "grace_until": None,
        }
        result = derive_subscription_status(sub, locked_at=None, now=_NOW)
        assert result == SubscriptionStatus.CANCELED

    def test_cancelled_with_past_period_still_canceled(self):
        sub = {
            "status": "cancelled",
            "billing_period_end": _PAST.isoformat(),
            "grace_until": None,
        }
        result = derive_subscription_status(sub, locked_at=None, now=_NOW)
        assert result == SubscriptionStatus.CANCELED


class TestDeriveActive:
    def test_active_future_period_end_returns_active(self):
        sub = {
            "status": "active",
            "billing_period_end": _FUTURE.isoformat(),
            "grace_until": None,
        }
        result = derive_subscription_status(sub, locked_at=None, now=_NOW)
        assert result == SubscriptionStatus.ACTIVE

    def test_active_no_period_end_returns_active(self):
        sub = {
            "status": "active",
            "billing_period_end": None,
            "grace_until": None,
        }
        result = derive_subscription_status(sub, locked_at=None, now=_NOW)
        assert result == SubscriptionStatus.ACTIVE


class TestDeriveGrace:
    def test_active_past_period_end_with_future_grace_returns_grace(self):
        sub = {
            "status": "active",
            "billing_period_end": _PAST.isoformat(),
            "grace_until": _GRACE_FUTURE.isoformat(),
        }
        result = derive_subscription_status(sub, locked_at=None, now=_NOW)
        assert result == SubscriptionStatus.GRACE


class TestDeriveExpired:
    def test_active_past_period_end_no_grace_returns_none(self):
        sub = {
            "status": "active",
            "billing_period_end": _PAST.isoformat(),
            "grace_until": None,
        }
        result = derive_subscription_status(sub, locked_at=None, now=_NOW)
        assert result == SubscriptionStatus.NONE

    def test_active_past_period_end_past_grace_returns_none(self):
        sub = {
            "status": "active",
            "billing_period_end": _PAST.isoformat(),
            "grace_until": (_NOW - timedelta(hours=1)).isoformat(),
        }
        result = derive_subscription_status(sub, locked_at=None, now=_NOW)
        assert result == SubscriptionStatus.NONE


class TestDeriveNaiveDatetimes:
    def test_naive_billing_period_end_treated_as_utc(self):
        # Naive datetime (no tzinfo) must be treated as UTC
        naive_future = (_NOW + timedelta(days=10)).replace(tzinfo=None).isoformat()
        sub = {
            "status": "active",
            "billing_period_end": naive_future,
            "grace_until": None,
        }
        result = derive_subscription_status(sub, locked_at=None, now=_NOW)
        assert result == SubscriptionStatus.ACTIVE
