"""Tests for app.entitlement.tier.has_active_pro."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.entitlement.tier import has_active_pro


def _make_supabase_with_subscription(data: list | None):
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
    return sb


class TestHasActivePro:
    def test_returns_true_for_active_subscription(self):
        sb = _make_supabase_with_subscription(
            [{"provider_subscription_id": "sub_active", "status": "active"}]
        )
        assert has_active_pro("user-1", sb) is True

    def test_returns_true_for_trialing_subscription(self):
        sb = _make_supabase_with_subscription(
            [{"provider_subscription_id": "sub_trial", "status": "trialing"}]
        )
        assert has_active_pro("user-1", sb) is True

    def test_returns_false_when_no_subscription(self):
        sb = _make_supabase_with_subscription([])
        assert has_active_pro("user-1", sb) is False

    def test_delegates_to_subscription_repo(self):
        """has_active_pro must go through SubscriptionRepository, not raw table access."""
        sb = _make_supabase_with_subscription(None)
        with patch(
            "app.entitlement.tier.SubscriptionRepository.get_active_subscription",
            return_value={"status": "active"},
        ) as mock_get:
            result = has_active_pro("user-42", sb)
        mock_get.assert_called_once_with("user-42")
        assert result is True
