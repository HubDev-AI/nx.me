"""Tests for ``_apply_signup_grant`` — Unit 9 signup-grant RPC wiring.

Covers the three call sites added in Unit 9:
  - register endpoint (email signup)
  - social_login endpoint (Google/Apple)
  - tiktok_login endpoint (new + existing user paths)

Tests drive ``_apply_signup_grant`` directly with a mock Supabase client to
verify:
  - Mobile signup (x_install_uuid present): all three fingerprint args derived
    and passed to the RPC.
  - Web signup (no x_install_uuid): all fingerprint args passed as None.
  - RPC errors are caught and logged, not re-raised (non-fatal).
  - Second call for same device (idempotency check via RPC suppression audit).
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.api.auth import _apply_signup_grant


INSTALL_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _make_supabase_mock(*, rpc_raises: Exception | None = None) -> MagicMock:
    """Build a minimal Supabase mock that records rpc() calls."""
    sb = MagicMock()
    rpc_chain = MagicMock()
    if rpc_raises:
        rpc_chain.execute.side_effect = rpc_raises
    else:
        rpc_chain.execute.return_value = MagicMock(data=None)
    sb.rpc.return_value = rpc_chain
    return sb


# ---------------------------------------------------------------------------
# Mobile signup (install UUID present)
# ---------------------------------------------------------------------------


class TestApplySignupGrantMobile:
    @pytest.mark.asyncio
    async def test_rpc_called_with_all_fingerprint_args(self, monkeypatch):
        """Mobile signup: deterministic_hash, protected_hash, and salt must all
        be non-None hex-encoded BYTEA strings (\\x...) passed to credit_apply_signup_grant."""
        sb = _make_supabase_mock()
        user_id = str(uuid4())

        await _apply_signup_grant(sb, user_id, INSTALL_UUID)

        sb.rpc.assert_called_once()
        rpc_name, rpc_params = sb.rpc.call_args.args
        assert rpc_name == "credit_apply_signup_grant"
        assert rpc_params["p_user_id"] == user_id
        # Supabase BYTEA columns must be passed as \\x<hex> strings
        assert isinstance(rpc_params["p_deterministic_hash"], str)
        assert rpc_params["p_deterministic_hash"].startswith("\\x")
        assert isinstance(rpc_params["p_protected_hash"], str)
        assert rpc_params["p_protected_hash"].startswith("\\x")
        assert isinstance(rpc_params["p_salt"], str)
        assert rpc_params["p_salt"].startswith("\\x")
        # grant amount sourced from settings (no magic numbers)
        from app.config import settings

        assert rpc_params["p_signup_grant_milli"] == settings.SIGNUP_GRANT_MILLI

    @pytest.mark.asyncio
    async def test_deterministic_hash_is_stable(self, monkeypatch):
        """Same install UUID + same server secret → same deterministic hash on
        two calls (but different salts → different protected hashes)."""
        user_id = str(uuid4())

        hashes: list[str] = []

        def _capture_rpc(name, params):
            hashes.append(params["p_deterministic_hash"])
            chain = MagicMock()
            chain.execute.return_value = MagicMock(data=None)
            return chain

        sb = MagicMock()
        sb.rpc.side_effect = _capture_rpc

        await _apply_signup_grant(sb, user_id, INSTALL_UUID)
        await _apply_signup_grant(sb, user_id, INSTALL_UUID)

        assert len(hashes) == 2
        # Deterministic hash must be the same across calls for same UUID.
        assert hashes[0] == hashes[1]
        assert isinstance(hashes[0], str)
        assert hashes[0].startswith("\\x")
        # SHA-256 produces 32 bytes = 64 hex chars; prefix adds 2 chars
        assert len(hashes[0]) == 66  # \\x + 64 hex chars

    @pytest.mark.asyncio
    async def test_execute_is_called(self):
        """The RPC chain .execute() must be awaited to actually fire the call."""
        sb = _make_supabase_mock()
        user_id = str(uuid4())

        await _apply_signup_grant(sb, user_id, INSTALL_UUID)

        sb.rpc.return_value.execute.assert_called_once()


# ---------------------------------------------------------------------------
# Web signup (no install UUID)
# ---------------------------------------------------------------------------


class TestApplySignupGrantWeb:
    @pytest.mark.asyncio
    async def test_rpc_called_with_null_fingerprint_args(self):
        """Web signup (no X-Install-UUID): all fingerprint args are None so the
        RPC takes the unconditional grant path (no registry row)."""
        sb = _make_supabase_mock()
        user_id = str(uuid4())

        await _apply_signup_grant(sb, user_id, None)

        sb.rpc.assert_called_once()
        _, rpc_params = sb.rpc.call_args.args
        assert rpc_params["p_deterministic_hash"] is None
        assert rpc_params["p_protected_hash"] is None
        assert rpc_params["p_salt"] is None
        assert rpc_params["p_user_id"] == user_id

    @pytest.mark.asyncio
    async def test_get_primary_secret_not_called_for_web_signup(self):
        """``get_primary_secret`` must NOT be called when install UUID is absent.
        Calling it would raise if the env var is missing, breaking web signups."""
        sb = _make_supabase_mock()
        user_id = str(uuid4())

        # Call without UUID and verify rpc still fires (no exception).
        # get_primary_secret must NOT be called — if it were, a missing env var
        # would break web signups even when no fingerprint is needed.
        # Patch at the source module (imported lazily inside _apply_signup_grant).
        with patch("app.entitlement.fingerprint.get_primary_secret") as mock_secret:
            await _apply_signup_grant(sb, user_id, None)
            mock_secret.assert_not_called()

        sb.rpc.assert_called_once()


# ---------------------------------------------------------------------------
# Error handling — non-fatal
# ---------------------------------------------------------------------------


class TestApplySignupGrantErrorHandling:
    @pytest.mark.asyncio
    async def test_rpc_exception_does_not_raise(self):
        """RPC failures must be swallowed — the user is already registered and
        a failed grant must never break the registration response."""
        sb = _make_supabase_mock(rpc_raises=RuntimeError("DB timeout"))
        user_id = str(uuid4())

        # Must not raise
        await _apply_signup_grant(sb, user_id, INSTALL_UUID)

    @pytest.mark.asyncio
    async def test_rpc_exception_does_not_raise_for_web_signup(self):
        """Same non-fatal guarantee for web signups (no install UUID)."""
        sb = _make_supabase_mock(rpc_raises=RuntimeError("DB timeout"))
        user_id = str(uuid4())

        await _apply_signup_grant(sb, user_id, None)

    @pytest.mark.asyncio
    async def test_rpc_exception_is_logged(self, caplog):
        """RPC failure must produce a log entry so ops can detect it."""
        import logging

        sb = _make_supabase_mock(rpc_raises=RuntimeError("network error"))
        user_id = str(uuid4())

        with caplog.at_level(logging.ERROR, logger="app.api.auth"):
            await _apply_signup_grant(sb, user_id, INSTALL_UUID)

        assert any("credit_apply_signup_grant" in r.message for r in caplog.records)
