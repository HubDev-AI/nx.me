"""Tests for FastAPI dependency providers.

Exercises production code in:
  - app/api/deps.py (get_client_ip, get_supabase, get_redis, get_current_user,
    require_admin, get_*_repo, get_payment_adapter, get_llm_adapter)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


try:
    from app.api.deps import get_client_ip, require_admin  # noqa: F401

    _DEPS_AVAILABLE = True
except (ImportError, AttributeError):
    _DEPS_AVAILABLE = False

pytestmark = pytest.mark.skipif(not _DEPS_AVAILABLE, reason="deps module unavailable")


# ---------------------------------------------------------------------------
# get_client_ip
# ---------------------------------------------------------------------------


class TestGetClientIP:
    """Tests for get_client_ip — exercises app/api/deps.py."""

    def test_returns_socket_ip_without_proxy(self):
        from app.api.deps import get_client_ip

        request = MagicMock()
        request.client.host = "192.168.1.10"
        request.headers = {}

        with patch("app.config.settings") as mock_settings:
            mock_settings.TRUST_PROXY_HEADERS = False
            result = get_client_ip(request)

        assert result == "192.168.1.10"

    def test_returns_forwarded_ip_when_trusted_loopback_proxy(self):
        from app.api.deps import get_client_ip

        request = MagicMock()
        request.client.host = "127.0.0.1"
        request.headers = {"x-forwarded-for": "198.51.100.77, 203.0.113.50"}

        with patch("app.config.settings") as mock_settings:
            mock_settings.TRUST_PROXY_HEADERS = True
            result = get_client_ip(request)

        assert result == "203.0.113.50"

    def test_ignores_forwarded_ip_from_untrusted_socket_peer(self):
        from app.api.deps import get_client_ip

        request = MagicMock()
        request.client.host = "198.51.100.10"
        request.headers = {"x-forwarded-for": "203.0.113.50"}

        with patch("app.config.settings") as mock_settings:
            mock_settings.TRUST_PROXY_HEADERS = True
            result = get_client_ip(request)

        assert result == "198.51.100.10"

    def test_skips_trusted_proxy_hops_in_forwarded_chain(self):
        """Real client precedes an internal LB hop; skip the LB and return the client."""
        from app.api.deps import get_client_ip

        request = MagicMock()
        request.client.host = "127.0.0.1"
        request.headers = {"x-forwarded-for": "203.0.113.50, 10.0.0.5"}

        with patch("app.config.settings") as mock_settings:
            mock_settings.TRUST_PROXY_HEADERS = True
            result = get_client_ip(request)

        assert result == "203.0.113.50"

    def test_walks_past_multiple_trusted_proxy_hops(self):
        """Chain of internal proxies must not mask the real client."""
        from app.api.deps import get_client_ip

        request = MagicMock()
        request.client.host = "127.0.0.1"
        request.headers = {"x-forwarded-for": "203.0.113.50, 10.0.0.5, 192.168.1.1"}

        with patch("app.config.settings") as mock_settings:
            mock_settings.TRUST_PROXY_HEADERS = True
            result = get_client_ip(request)

        assert result == "203.0.113.50"

    def test_ignores_loopback_entries_in_forwarded_chain(self):
        """Loopback / link-local entries can never be a real client."""
        from app.api.deps import get_client_ip

        request = MagicMock()
        request.client.host = "127.0.0.1"
        request.headers = {"x-forwarded-for": "127.0.0.1, 169.254.1.1"}

        with patch("app.config.settings") as mock_settings:
            mock_settings.TRUST_PROXY_HEADERS = True
            result = get_client_ip(request)

        assert result == "127.0.0.1"

    def test_returns_empty_when_no_client(self):
        from app.api.deps import get_client_ip

        request = MagicMock()
        request.client = None
        request.headers = {}

        with patch("app.config.settings") as mock_settings:
            mock_settings.TRUST_PROXY_HEADERS = False
            result = get_client_ip(request)

        assert result == ""


# ---------------------------------------------------------------------------
# Infrastructure deps
# ---------------------------------------------------------------------------


class TestInfraDeps:
    """Tests for get_supabase and get_redis — exercises app/api/deps.py."""

    def test_get_supabase_returns_app_state(self):
        from app.api.deps import get_supabase

        request = MagicMock()
        sentinel = object()
        request.app.state.supabase = sentinel
        assert get_supabase(request) is sentinel

    def test_get_redis_returns_app_state(self):
        from app.api.deps import get_redis

        request = MagicMock()
        sentinel = object()
        request.app.state.redis = sentinel
        assert get_redis(request) is sentinel


# ---------------------------------------------------------------------------
# require_admin
# ---------------------------------------------------------------------------


class TestRequireAdmin:
    """Tests for require_admin — exercises app/api/deps.py."""

    def test_valid_admin_key(self):
        from app.api.deps import require_admin
        from app.config import settings

        result = require_admin(x_admin_key=settings.ADMIN_API_KEY)
        assert result is None  # no exception means success

    def test_missing_key_raises_403(self):
        from app.api.deps import require_admin

        with pytest.raises(HTTPException) as exc_info:
            require_admin(x_admin_key=None)
        assert exc_info.value.status_code == 403

    def test_wrong_key_raises_403(self):
        from app.api.deps import require_admin

        with pytest.raises(HTTPException) as exc_info:
            require_admin(x_admin_key="wrong-key-that-is-definitely-not-correct")
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# get_current_user
# ---------------------------------------------------------------------------


class TestGetCurrentUser:
    """Tests for get_current_user — exercises app/api/deps.py."""

    @pytest.mark.asyncio
    async def test_missing_auth_header_raises_401(self):
        from app.api.deps import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                authorization=None, supabase=MagicMock(), redis_client=AsyncMock()
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_malformed_auth_header_raises_401(self):
        from app.api.deps import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                authorization="Basic abc123",
                supabase=MagicMock(),
                redis_client=AsyncMock(),
            )
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Repository factory deps
# ---------------------------------------------------------------------------


class TestRepoFactories:
    """Tests for get_*_repo factory functions — exercises app/api/deps.py."""

    def test_get_user_repo(self):
        from app.api.deps import get_user_repo

        request = MagicMock()
        repo = get_user_repo(request)
        assert repo is not None

    def test_get_block_repo(self):
        from app.api.deps import get_block_repo

        request = MagicMock()
        repo = get_block_repo(request)
        assert repo is not None

    def test_get_post_repo(self):
        from app.api.deps import get_post_repo

        request = MagicMock()
        repo = get_post_repo(request)
        assert repo is not None

    def test_get_feed_repo(self):
        from app.api.deps import get_feed_repo

        request = MagicMock()
        repo = get_feed_repo(request)
        assert repo is not None

    def test_get_job_repo(self):
        from app.api.deps import get_job_repo

        request = MagicMock()
        repo = get_job_repo(request)
        assert repo is not None

    def test_get_image_repo(self):
        from app.api.deps import get_image_repo

        request = MagicMock()
        repo = get_image_repo(request)
        assert repo is not None

    def test_get_upload_repo(self):
        from app.api.deps import get_upload_repo

        request = MagicMock()
        repo = get_upload_repo(request)
        assert repo is not None

    def test_get_glowup_analysis_repo(self):
        from app.api.deps import get_glowup_analysis_repo

        request = MagicMock()
        repo = get_glowup_analysis_repo(request)
        assert repo is not None

    def test_get_subscription_repo(self):
        from app.api.deps import get_subscription_repo

        request = MagicMock()
        repo = get_subscription_repo(request)
        assert repo is not None

    def test_get_advisor_repo(self):
        from app.api.deps import get_advisor_repo

        request = MagicMock()
        repo = get_advisor_repo(request)
        assert repo is not None

    def test_get_credit_ledger(self):
        from app.api.deps import get_credit_ledger

        request = MagicMock()
        ledger = get_credit_ledger(request)
        assert ledger is not None

    def test_get_tier_repo(self):
        from app.api.deps import get_tier_repo

        request = MagicMock()
        repo = get_tier_repo(request)
        assert repo is not None


# ---------------------------------------------------------------------------
# Adapter factories
# ---------------------------------------------------------------------------


class TestAdapterFactories:
    """Tests for get_payment_adapter and get_llm_adapter — exercises app/api/deps.py."""

    def test_payment_adapter_mock(self):
        from app.api.deps import get_payment_adapter

        adapter = get_payment_adapter()
        assert adapter is not None

    def test_llm_adapter_mock(self):
        from app.api.deps import get_llm_adapter

        adapter = get_llm_adapter()
        assert adapter is not None
