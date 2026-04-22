"""Nudge per-trigger 1/24h throttle — Plan 2026-04-21-001 Unit 10."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.config import settings as _settings


_TEST_USER_ID = str(uuid4())

_STYLE_PROFILE = {
    "content": {"face_shape": "oval", "symmetry_score": 0.9},
}

_GOOD_RESPONSE = (
    '{"body": "That lip color looks stunning on your complexion.", '
    '"next_step": {"label": "Ask Ada", "seed": "Which lip shades would suit me best?"}}'
)


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


def _patch_makeup_scheduler(monkeypatch, *, style_profile=None, image_blocks=None):
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
        return {"content": [{"type": "text", "text": "no completed makeup session"}], "is_error": True}

    monkeypatch.setattr(nudge_scheduler, "_handle_get_latest_makeup", _makeup_handler)
    monkeypatch.setattr(nudge_scheduler, "_get_llm_adapter", lambda: _fake_llm(_GOOD_RESPONSE))
    return repo


@pytest.mark.asyncio
async def test_second_makeup_within_24h_does_not_fire(monkeypatch):
    """Second post_makeup completion within 24h does NOT re-fire nudge."""
    from app.advisor import nudge_scheduler

    monkeypatch.setattr(_settings, "ADVISOR_ENABLED", True)
    repo = _patch_makeup_scheduler(
        monkeypatch,
        style_profile=_STYLE_PROFILE,
        image_blocks=[_image_block()],
    )

    redis = AsyncMock()
    # First call: SETNX returns True (accepted)
    # Second call: SETNX returns False (already set — within 24h)
    redis.set = AsyncMock(side_effect=[True, False])

    ctx = {"supabase": MagicMock(), "redis": redis}

    await nudge_scheduler.generate_nudge_makeup(ctx=ctx, user_id=_TEST_USER_ID)
    await nudge_scheduler.generate_nudge_makeup(ctx=ctx, user_id=_TEST_USER_ID)

    assert repo.insert_nudge.call_count == 1


@pytest.mark.asyncio
async def test_post_glowup_and_post_makeup_fire_independently(monkeypatch):
    """post_glowup and post_makeup throttle independently — no cross-throttle."""
    from app.advisor import nudge_scheduler

    monkeypatch.setattr(_settings, "ADVISOR_ENABLED", True)
    monkeypatch.setattr(_settings, "ADVISOR_POST_GLOWUP_RAPID_RETRY_MINUTES", 0)

    repo = MagicMock()
    repo.get_style_profile = MagicMock(return_value=_STYLE_PROFILE)
    repo.get_recent_nudge_context = MagicMock(return_value=[])
    repo.insert_nudge = MagicMock()
    repo.find_duplicate_body = MagicMock(return_value=False)
    monkeypatch.setattr(
        nudge_scheduler, "AdvisorRepository", MagicMock(return_value=repo)
    )

    async def _glowup_handler(_ctx):
        return {"content": [_image_block()], "is_error": False}

    async def _makeup_handler(_ctx):
        return {"content": [_image_block()], "is_error": False}

    monkeypatch.setattr(nudge_scheduler, "_handle_get_latest_glowup", _glowup_handler)
    monkeypatch.setattr(nudge_scheduler, "_handle_get_latest_makeup", _makeup_handler)
    monkeypatch.setattr(nudge_scheduler, "_get_llm_adapter", lambda: _fake_llm(_GOOD_RESPONSE))

    # Redis always accepts (separate keys per trigger)
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    ctx = {"supabase": MagicMock(), "redis": redis}

    await nudge_scheduler.generate_nudge(ctx=ctx, user_id=_TEST_USER_ID, job_id=None)
    await nudge_scheduler.generate_nudge_makeup(ctx=ctx, user_id=_TEST_USER_ID)

    assert repo.insert_nudge.call_count == 2


@pytest.mark.asyncio
async def test_makeup_throttle_key_uses_per_trigger_namespace(monkeypatch):
    """Makeup throttle Redis key uses ``post_makeup`` namespace, not ``post_glowup``."""
    from app.advisor import nudge_scheduler

    monkeypatch.setattr(_settings, "ADVISOR_ENABLED", True)
    _patch_makeup_scheduler(
        monkeypatch,
        style_profile=_STYLE_PROFILE,
        image_blocks=[_image_block()],
    )

    redis = AsyncMock()
    captured_keys: list[str] = []

    async def _set(key, *args, **kwargs):
        captured_keys.append(key)
        return True

    redis.set = _set
    ctx = {"supabase": MagicMock(), "redis": redis}

    await nudge_scheduler.generate_nudge_makeup(ctx=ctx, user_id=_TEST_USER_ID)

    assert any("post_makeup" in k for k in captured_keys)
    assert all("post_glowup" not in k for k in captured_keys)
