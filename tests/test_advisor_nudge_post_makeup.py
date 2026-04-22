"""post_makeup nudge trigger — Plan 2026-04-21-001 Unit 10."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.config import settings as _settings


_TEST_USER_ID = str(uuid4())
_TEST_JOB_ID = str(uuid4())


def _image_block() -> dict[str, Any]:
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": "ZmFrZQ=="},
    }


def _fake_llm(response_text: str):
    async def _create(**_kwargs):
        from app.advisor.models import LLMResponse

        return LLMResponse(content=response_text, input_tokens=1, output_tokens=1)

    return SimpleNamespace(create_message=_create)


_GOOD_RESPONSE = (
    '{"body": "That lip color looks stunning on your complexion.", '
    '"next_step": {"label": "Ask Ada", "seed": "Which lip shades would suit me best?"}}'
)

_STYLE_PROFILE = {
    "content": {"face_shape": "oval", "symmetry_score": 0.9},
    "created_at": "2026-04-21T00:00:00Z",
}


def _make_redis(*, throttle_accepted: bool = True) -> AsyncMock:
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=throttle_accepted)
    return redis


def _patch_nudge_scheduler(monkeypatch, *, image_blocks=None, style_profile=None):
    from app.advisor import nudge_scheduler

    repo = MagicMock()
    repo.get_style_profile = MagicMock(return_value=style_profile)
    repo.get_recent_nudge_context = MagicMock(return_value=[])
    repo.insert_nudge = MagicMock()
    repo.find_duplicate_body = MagicMock(return_value=False)
    monkeypatch.setattr(
        nudge_scheduler, "AdvisorRepository", MagicMock(return_value=repo)
    )

    async def _makeup_handler(_ctx):
        if image_blocks is not None:
            return {"content": list(image_blocks), "is_error": False}
        return {
            "content": [{"type": "text", "text": "no completed makeup session"}],
            "is_error": True,
        }

    monkeypatch.setattr(nudge_scheduler, "_handle_get_latest_makeup", _makeup_handler)
    return repo


@pytest.mark.asyncio
async def test_makeup_nudge_fires_on_completion(monkeypatch):
    """Happy path: makeup job completion → nudge generated + saved."""
    from app.advisor import nudge_scheduler

    monkeypatch.setattr(_settings, "ADVISOR_ENABLED", True)
    repo = _patch_nudge_scheduler(
        monkeypatch,
        image_blocks=[_image_block()],
        style_profile=_STYLE_PROFILE,
    )
    monkeypatch.setattr(
        nudge_scheduler, "_get_llm_adapter", lambda: _fake_llm(_GOOD_RESPONSE)
    )

    redis = _make_redis(throttle_accepted=True)
    ctx = {"supabase": MagicMock(), "redis": redis}

    await nudge_scheduler.generate_nudge_makeup(ctx=ctx, user_id=_TEST_USER_ID)

    repo.insert_nudge.assert_called_once()
    nudge = repo.insert_nudge.call_args[0][0]
    assert "lip" in nudge["body"].lower() or "stun" in nudge["body"].lower()


@pytest.mark.asyncio
async def test_makeup_nudge_skipped_no_style_profile(monkeypatch, caplog):
    """No style_profile → nudge skipped with log."""
    from app.advisor import nudge_scheduler

    monkeypatch.setattr(_settings, "ADVISOR_ENABLED", True)
    repo = _patch_nudge_scheduler(
        monkeypatch,
        image_blocks=[_image_block()],
        style_profile=None,
    )
    monkeypatch.setattr(
        nudge_scheduler, "_get_llm_adapter", lambda: _fake_llm(_GOOD_RESPONSE)
    )

    redis = _make_redis(throttle_accepted=True)
    ctx = {"supabase": MagicMock(), "redis": redis}

    caplog.set_level(logging.INFO)
    await nudge_scheduler.generate_nudge_makeup(ctx=ctx, user_id=_TEST_USER_ID)

    repo.insert_nudge.assert_not_called()


@pytest.mark.asyncio
async def test_makeup_nudge_skipped_no_images(monkeypatch):
    """No image blocks returned → nudge skipped."""
    from app.advisor import nudge_scheduler

    monkeypatch.setattr(_settings, "ADVISOR_ENABLED", True)
    repo = _patch_nudge_scheduler(
        monkeypatch,
        image_blocks=None,  # makeup handler returns is_error=True
        style_profile=_STYLE_PROFILE,
    )
    monkeypatch.setattr(
        nudge_scheduler, "_get_llm_adapter", lambda: _fake_llm(_GOOD_RESPONSE)
    )

    redis = _make_redis(throttle_accepted=True)
    ctx = {"supabase": MagicMock(), "redis": redis}

    await nudge_scheduler.generate_nudge_makeup(ctx=ctx, user_id=_TEST_USER_ID)

    repo.insert_nudge.assert_not_called()


@pytest.mark.asyncio
async def test_makeup_nudge_advisor_disabled(monkeypatch):
    """ADVISOR_ENABLED=False → early return, no LLM call."""
    from app.advisor import nudge_scheduler

    monkeypatch.setattr(_settings, "ADVISOR_ENABLED", False)
    repo = _patch_nudge_scheduler(
        monkeypatch,
        image_blocks=[_image_block()],
        style_profile=_STYLE_PROFILE,
    )

    redis = _make_redis()
    ctx = {"supabase": MagicMock(), "redis": redis}

    await nudge_scheduler.generate_nudge_makeup(ctx=ctx, user_id=_TEST_USER_ID)

    repo.insert_nudge.assert_not_called()
    redis.set.assert_not_called()
