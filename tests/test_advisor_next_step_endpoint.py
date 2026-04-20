"""Tests for POST /v1/advisor/nudges/{nudge_id}/next-step (Unit 4).

Exercises app/api/advisor.py::get_nudge_next_step.

Strategy: direct-handler-call pattern (mirrors test_admin.py).
  - Patch ``app.api.advisor.run_sync`` with an async passthrough.
  - Supply a fake AdvisorRepository with controlled get_nudge_by_id behaviour.
  - Use MockRedis from conftest for rate-limit state.
  - No TestClient needed; avoids the _ROUTERS_AVAILABLE skip guard.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from tests.conftest import MockRedis


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run_sync(fn, *args, **kwargs):
    """Synchronous-function passthrough for async tests."""
    return fn(*args, **kwargs)


def _make_claims(user_id: str) -> dict:
    """Minimal UserClaims dict (mirrors what get_current_user returns)."""
    return {"sub": user_id}


def _fake_repo(nudge_row: dict | None, owner_user_id: str) -> MagicMock:
    """Return a mock AdvisorRepository whose get_nudge_by_id filters by owner."""

    def _get_nudge_by_id(nudge_id: str, user_id: str) -> dict | None:
        if row := nudge_row:
            if row.get("user_id") == user_id and row.get("id") == nudge_id:
                return row
        return None

    repo = MagicMock()
    repo.get_nudge_by_id.side_effect = _get_nudge_by_id
    return repo


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_returns_seed_text():
    """Owner calls with their nudge → 200 + seed_text."""
    from app.api.advisor import get_nudge_next_step

    user_id = str(uuid4())
    nudge_id = str(uuid4())
    seed = "Try blending your contour with a damp sponge for a softer finish."
    nudge_row = {
        "id": nudge_id,
        "user_id": user_id,
        "next_step_seed": seed,
        "body": "Your highlight could be more blended.",
        "read_at": None,
        "created_at": "2026-04-20T10:00:00+00:00",
    }

    mock_supabase = MagicMock()
    mock_redis = MockRedis()
    claims = _make_claims(user_id)

    with (
        patch("app.api.advisor.run_sync", side_effect=_run_sync),
        patch(
            "app.api.advisor.AdvisorRepository",
            return_value=_fake_repo(nudge_row, user_id),
        ),
    ):
        result = await get_nudge_next_step(
            nudge_id=nudge_id,  # type: ignore[arg-type]
            claims=claims,
            supabase=mock_supabase,
            redis_client=mock_redis,
        )

    assert result.seed_text == seed


# ---------------------------------------------------------------------------
# IDOR — user A calls with nudge owned by user B → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_idor_returns_404():
    """User A calling with B's nudge_id must get 404, not 403."""
    from app.api.advisor import get_nudge_next_step

    user_a = str(uuid4())
    user_b = str(uuid4())
    nudge_id = str(uuid4())
    nudge_row = {
        "id": nudge_id,
        "user_id": user_b,
        "next_step_seed": "some seed",
        "body": "b's nudge",
        "read_at": None,
        "created_at": "2026-04-20T10:00:00+00:00",
    }

    mock_supabase = MagicMock()
    mock_redis = MockRedis()
    claims = _make_claims(user_a)  # calling as user A

    with (
        patch("app.api.advisor.run_sync", side_effect=_run_sync),
        patch(
            "app.api.advisor.AdvisorRepository",
            return_value=_fake_repo(nudge_row, user_b),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_nudge_next_step(
                nudge_id=nudge_id,  # type: ignore[arg-type]
                claims=claims,
                supabase=mock_supabase,
                redis_client=mock_redis,
            )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"]["code"] == "nudge_not_found"


# ---------------------------------------------------------------------------
# Unknown nudge_id → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_nudge_id_returns_404():
    """Nudge does not exist at all → 404 nudge_not_found."""
    from app.api.advisor import get_nudge_next_step

    user_id = str(uuid4())
    mock_supabase = MagicMock()
    mock_redis = MockRedis()
    claims = _make_claims(user_id)

    with (
        patch("app.api.advisor.run_sync", side_effect=_run_sync),
        patch(
            "app.api.advisor.AdvisorRepository",
            return_value=_fake_repo(None, user_id),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_nudge_next_step(
                nudge_id=str(uuid4()),  # type: ignore[arg-type]
                claims=claims,
                supabase=mock_supabase,
                redis_client=mock_redis,
            )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"]["code"] == "nudge_not_found"


# ---------------------------------------------------------------------------
# Rate limit: 61st call → 429
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_exceeded_on_61st_call():
    """61st call within the window returns 429 rate_limited."""
    from app.api.advisor import get_nudge_next_step
    from app.config import settings

    user_id = str(uuid4())
    nudge_id = str(uuid4())
    nudge_row = {
        "id": nudge_id,
        "user_id": user_id,
        "next_step_seed": "seed",
        "body": "body",
        "read_at": None,
        "created_at": "2026-04-20T10:00:00+00:00",
    }

    mock_supabase = MagicMock()
    mock_redis = MockRedis()
    claims = _make_claims(user_id)

    # Pre-fill the counter to the limit so the next call overflows.
    rl_key = f"advisor:next_step_rl:{user_id}"
    mock_redis._store[rl_key] = settings.ADVISOR_NEXT_STEP_RL_LIMIT

    with (
        patch("app.api.advisor.run_sync", side_effect=_run_sync),
        patch(
            "app.api.advisor.AdvisorRepository",
            return_value=_fake_repo(nudge_row, user_id),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_nudge_next_step(
                nudge_id=nudge_id,  # type: ignore[arg-type]
                claims=claims,
                supabase=mock_supabase,
                redis_client=mock_redis,
            )

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["error"]["code"] == "rate_limited"


# ---------------------------------------------------------------------------
# advisor_enabled flag off → 403 FEATURE_DISABLED (router-level dep)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feature_disabled_raises_403():
    """When advisor_enabled is off, require_app_feature raises 403."""
    from app.api.deps import require_app_feature
    from app.config import settings as real_settings

    dep = require_app_feature("advisor_enabled")
    with patch.object(real_settings, "ADVISOR_ENABLED", False):
        with pytest.raises(HTTPException) as exc_info:
            await dep()

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error"]["code"] == "FEATURE_DISABLED"


# ---------------------------------------------------------------------------
# No rows written to advisor_conversations or advisor_messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_conversation_or_message_rows_written():
    """Successful call must not touch advisor_conversations or advisor_messages."""
    from app.api.advisor import get_nudge_next_step

    user_id = str(uuid4())
    nudge_id = str(uuid4())
    nudge_row = {
        "id": nudge_id,
        "user_id": user_id,
        "next_step_seed": "seed text here",
        "body": "body",
        "read_at": None,
        "created_at": "2026-04-20T10:00:00+00:00",
    }

    mock_supabase = MagicMock()
    mock_redis = MockRedis()
    claims = _make_claims(user_id)

    with (
        patch("app.api.advisor.run_sync", side_effect=_run_sync),
        patch(
            "app.api.advisor.AdvisorRepository",
            return_value=_fake_repo(nudge_row, user_id),
        ),
    ):
        await get_nudge_next_step(
            nudge_id=nudge_id,  # type: ignore[arg-type]
            claims=claims,
            supabase=mock_supabase,
            redis_client=mock_redis,
        )

    # supabase.table should never have been called (no DB writes at all via mock_supabase).
    # The repo is fully mocked so the real supabase client is untouched.
    mock_supabase.table.assert_not_called()
