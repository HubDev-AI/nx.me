"""Tests for COR-001 — social/TikTok signup must honor username reservations.

Both the Google/Apple social-login retry loop and the TikTok login retry loop
now call ``check_username_availability`` (which consults both the users table
and username_reservations) instead of ``check_username_taken`` (users table
only).  These tests verify that a "reserved" result triggers a suffix-retry,
preventing a deleted user's handle from being silently claimed.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

try:
    from app.api.auth import social_login, tiktok_login

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


async def _passthrough_run_sync(fn, *args, **kwargs):
    return fn(*args, **kwargs)


class _MockRedis:
    """Minimal Redis stub with async pipeline for rate-limiter calls."""

    class _Pipeline:
        def __init__(self) -> None:
            self._count = 1

        def incr(self, key: str) -> "_MockRedis._Pipeline":
            return self

        def expire(self, key: str, ttl: int, nx: bool = False) -> "_MockRedis._Pipeline":
            return self

        async def execute(self) -> list:
            return [self._count, True]

    def pipeline(self) -> "_MockRedis._Pipeline":
        return self._Pipeline()

    async def ttl(self, key: str) -> int:
        return 0


def _make_google_request() -> MagicMock:
    req = MagicMock()
    req.headers = {}
    return req


def _patch_google_common(monkeypatch, user_id: str, email: str, fake_session) -> None:
    monkeypatch.setattr("app.api.auth.run_sync", _passthrough_run_sync)
    monkeypatch.setattr("app.api.auth.get_client_ip", lambda request: "203.0.113.1")
    monkeypatch.setattr(
        "app.api.auth.check_login_rate_limit",
        AsyncMock(return_value=(True, 0)),
    )
    monkeypatch.setattr("app.config.settings.AUTH_PROVIDER_GOOGLE_ENABLED", True)
    fake_login_client = MagicMock()
    fake_login_client.auth.sign_in_with_id_token.return_value = fake_session
    monkeypatch.setattr("app.db.client.get_supabase_service", lambda: fake_login_client)


def _make_google_session(user_id: str, email: str):
    fake_user = MagicMock()
    fake_user.id = user_id
    fake_user.email = email
    fake_user.user_metadata = {}
    fake_session = MagicMock()
    fake_session.user = fake_user
    fake_session.session = MagicMock(
        access_token="at", refresh_token="rt", expires_at=9999
    )
    return fake_session


def _patch_tiktok_common(
    monkeypatch, open_id: str, display_name: str
) -> None:
    monkeypatch.setattr("app.api.auth.run_sync", _passthrough_run_sync)
    monkeypatch.setattr("app.api.auth.get_client_ip", lambda request: "203.0.113.3")
    monkeypatch.setattr(
        "app.api.auth.check_login_rate_limit",
        AsyncMock(return_value=(True, 0)),
    )
    monkeypatch.setattr("app.config.settings.AUTH_PROVIDER_TIKTOK_ENABLED", True)
    monkeypatch.setattr("app.config.settings.TIKTOK_CLIENT_KEY", "fake_key")
    monkeypatch.setattr("app.config.settings.TIKTOK_CLIENT_SECRET", "fake_secret")
    monkeypatch.setattr(
        "app.config.settings.TIKTOK_SYNTHETIC_EMAIL_DOMAIN", "tiktok.nxme.test"
    )

    # authenticate is imported from tiktok_auth inside the function body
    fake_tiktok_user = SimpleNamespace(display_name=display_name, avatar_url=None)
    monkeypatch.setattr(
        "app.services.tiktok_auth.authenticate",
        AsyncMock(return_value=(open_id, fake_tiktok_user)),
    )

    # get_supabase_service is imported from db.client inside the function body
    fake_svc = MagicMock()
    fake_svc.auth.admin.create_user.return_value = MagicMock(
        user=MagicMock(id=f"u-{open_id}")
    )
    fake_svc.auth.sign_in_with_password.return_value = MagicMock(
        session=MagicMock(access_token="at", refresh_token="rt", expires_at=9999)
    )
    monkeypatch.setattr("app.db.client.get_supabase_service", lambda: fake_svc)


# ---------------------------------------------------------------------------
# Social (Google/Apple) login — reservation bypass fix
# ---------------------------------------------------------------------------


class TestSocialLoginReservationBypass:
    """Check that the Google/Apple login retry loop uses check_username_availability."""

    @pytest.mark.asyncio
    async def test_reserved_username_triggers_suffix_retry(self, monkeypatch):
        """When check_username_availability returns ``reserved``, a new suffix is tried."""
        fake_session = _make_google_session("u-google-1", "alice@example.com")
        fake_supabase = MagicMock()
        fake_supabase.auth.sign_in_with_id_token.return_value = fake_session
        _patch_google_common(monkeypatch, "u-google-1", "alice@example.com", fake_session)

        # username availability: first call -> reserved, second call -> available
        availability_calls: list[dict] = []

        def _avail(username: str, exclude_user_id: str | None = None) -> dict:
            availability_calls.append({"username": username})
            if len(availability_calls) == 1:
                return {"available": False, "reason": "reserved"}
            return {"available": True}

        user_repo = MagicMock()
        user_repo.check_username_availability.side_effect = _avail
        user_repo.upsert.return_value = None
        user_repo.get_profile_by_id.return_value = {"username": "alice_abc123"}

        tier_repo = SimpleNamespace(
            get_default=AsyncMock(return_value=SimpleNamespace(id="tier-1"))
        )

        from app.api.auth import LoginRequest

        result = await social_login(
            request=_make_google_request(),
            body=LoginRequest(provider="google", id_token="tok"),
            supabase=fake_supabase,
            r=_MockRedis(),
            user_repo=user_repo,
            tier_repo=tier_repo,
        )

        # Two availability checks happened: first "reserved", then "available"
        assert len(availability_calls) == 2
        # The second attempt used a different (suffixed) username
        assert availability_calls[0]["username"] != availability_calls[1]["username"]
        assert result.username == "alice_abc123"

    @pytest.mark.asyncio
    async def test_check_username_availability_called_not_check_username_taken(
        self, monkeypatch
    ):
        """Ensures the social-login loop does NOT call check_username_taken."""
        fake_session = _make_google_session("u-google-2", "bob@example.com")
        fake_supabase = MagicMock()
        fake_supabase.auth.sign_in_with_id_token.return_value = fake_session
        _patch_google_common(monkeypatch, "u-google-2", "bob@example.com", fake_session)

        user_repo = MagicMock()
        user_repo.check_username_availability.return_value = {"available": True}
        user_repo.upsert.return_value = None
        user_repo.get_profile_by_id.return_value = {"username": "bob"}

        tier_repo = SimpleNamespace(
            get_default=AsyncMock(return_value=SimpleNamespace(id="tier-1"))
        )

        from app.api.auth import LoginRequest

        await social_login(
            request=_make_google_request(),
            body=LoginRequest(provider="google", id_token="tok"),
            supabase=fake_supabase,
            r=_MockRedis(),
            user_repo=user_repo,
            tier_repo=tier_repo,
        )

        user_repo.check_username_availability.assert_called()
        user_repo.check_username_taken.assert_not_called()


# ---------------------------------------------------------------------------
# TikTok login — reservation bypass fix
# ---------------------------------------------------------------------------


class TestTikTokLoginReservationBypass:
    """Check that the TikTok login retry loop uses check_username_availability."""

    @pytest.mark.asyncio
    async def test_reserved_username_triggers_suffix_retry(self, monkeypatch):
        """When check_username_availability returns ``reserved``, a new suffix is tried."""
        _patch_tiktok_common(monkeypatch, open_id="ot-1", display_name="chloé")

        # availability: first call reserved, second available
        availability_calls: list[dict] = []

        def _avail(username: str, exclude_user_id: str | None = None) -> dict:
            availability_calls.append({"username": username})
            if len(availability_calls) == 1:
                return {"available": False, "reason": "reserved"}
            return {"available": True}

        user_repo = MagicMock()
        user_repo.check_username_availability.side_effect = _avail
        user_repo.find_by_tiktok_open_id.return_value = None
        user_repo.insert.return_value = None
        user_repo.get_profile_by_id.return_value = {"username": "chloe_abc123"}

        tier_repo = SimpleNamespace(
            get_default=AsyncMock(return_value=SimpleNamespace(id="tier-1"))
        )

        from app.api.auth import TikTokLoginRequest

        result = await tiktok_login(
            request=MagicMock(),
            body=TikTokLoginRequest(auth_code="tk-code"),
            supabase=MagicMock(),
            r=_MockRedis(),
            user_repo=user_repo,
            tier_repo=tier_repo,
        )

        assert len(availability_calls) == 2
        assert availability_calls[0]["username"] != availability_calls[1]["username"]
        assert result.username == "chloe_abc123"

    @pytest.mark.asyncio
    async def test_check_username_taken_not_called_in_tiktok_loop(self, monkeypatch):
        """Ensures the TikTok login loop does NOT call check_username_taken."""
        _patch_tiktok_common(monkeypatch, open_id="ot-2", display_name="dana")

        user_repo = MagicMock()
        user_repo.check_username_availability.return_value = {"available": True}
        user_repo.find_by_tiktok_open_id.return_value = None
        user_repo.insert.return_value = None
        user_repo.get_profile_by_id.return_value = {"username": "dana"}

        tier_repo = SimpleNamespace(
            get_default=AsyncMock(return_value=SimpleNamespace(id="tier-1"))
        )

        from app.api.auth import TikTokLoginRequest

        await tiktok_login(
            request=MagicMock(),
            body=TikTokLoginRequest(auth_code="tk-code2"),
            supabase=MagicMock(),
            r=_MockRedis(),
            user_repo=user_repo,
            tier_repo=tier_repo,
        )

        user_repo.check_username_availability.assert_called()
        user_repo.check_username_taken.assert_not_called()
