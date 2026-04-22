"""Tests that SubscriptionRepository.get_active_subscription covers trialing status."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.repositories.subscription_repo import SubscriptionRepository


def _make_supabase(data: list | None):
    """Return a minimal Supabase mock whose table chain returns *data*."""
    execute_result = MagicMock()
    execute_result.data = data

    builder = MagicMock()
    builder.select.return_value = builder
    builder.eq.return_value = builder
    builder.in_.return_value = builder
    builder.limit.return_value = builder
    builder.execute.return_value = execute_result

    sb = MagicMock()
    sb.table.return_value = builder
    return sb, builder


class TestGetActiveSubscriptionStatusFilter:
    def test_returns_active_row(self):
        row = {"provider_subscription_id": "sub_active", "status": "active"}
        sb, _ = _make_supabase([row])
        repo = SubscriptionRepository(sb)
        result = repo.get_active_subscription("user-1")
        assert result == row

    def test_returns_trialing_row(self):
        row = {"provider_subscription_id": "sub_trial", "status": "trialing"}
        sb, _ = _make_supabase([row])
        repo = SubscriptionRepository(sb)
        result = repo.get_active_subscription("user-1")
        assert result == row

    def test_returns_none_when_no_row(self):
        sb, _ = _make_supabase([])
        repo = SubscriptionRepository(sb)
        assert repo.get_active_subscription("user-1") is None

    def test_uses_in_filter_not_eq(self):
        """Query must use .in_() with both statuses, not a single .eq()."""
        sb, builder = _make_supabase(None)
        repo = SubscriptionRepository(sb)
        repo.get_active_subscription("user-1")

        # .in_() should be called with the status column and both statuses
        builder.in_.assert_called_once()
        call_args = builder.in_.call_args
        column, statuses = call_args[0]
        assert column == "status"
        assert set(statuses) == {"active", "trialing"}

        # .eq() should NOT be called with "status" (old single-eq pattern)
        for call in builder.eq.call_args_list:
            col = call[0][0]
            assert col != "status", (
                "eq('status', ...) must not be used — use in_() instead"
            )
