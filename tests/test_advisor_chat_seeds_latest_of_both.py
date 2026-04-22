"""Chat seeds latest-of-{glowup, makeup} tie-break — Plan 2026-04-21-001 Unit 10."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


_TEST_USER_ID = str(uuid4())
_GLOWUP_JOB_ID = str(uuid4())
_MAKEUP_JOB_ID = str(uuid4())


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    async def get(self, key: str) -> Any:
        return self.store.get(key)

    async def set(
        self, key: str, value: Any, ex: int | None = None, nx: bool = False, **_: Any
    ) -> Any:
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def delete(self, key: str) -> int:
        return self.store.pop(key, None) and 1 or 0


def _fake_llm():
    async def _create(**_kwargs):
        from app.advisor.models import LLMResponse

        seeds_json = json.dumps(
            {
                "seeds": [
                    {"label": "Label 1", "text": "Question one?"},
                    {"label": "Label 2", "text": "Question two?"},
                    {"label": "Label 3", "text": "Question three?"},
                ]
            }
        )
        return LLMResponse(content=seeds_json, input_tokens=5, output_tokens=20)

    return SimpleNamespace(create_message=_create)


def _image_block() -> dict[str, Any]:
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": "ZmFrZQ=="},
    }


def _make_row(job_id: str, source_type: str, updated_at: str) -> dict[str, Any]:
    return {
        "id": job_id,
        "source_type": source_type,
        "status": "completed",
        "updated_at": updated_at,
        "before_image_url": "raw-selfies/before.jpg",
        "after_image_url": "generated/after.jpg",
    }


def _make_repo(anchor_row: dict | None) -> MagicMock:
    repo = MagicMock()
    repo.get_latest_completed_job_with_images.return_value = anchor_row
    repo.get_style_profile.return_value = None
    return repo


@pytest.mark.asyncio
async def test_makeup_newer_uses_makeup_handler(monkeypatch):
    """Anchor is makeup (most recent) → makeup handler is called."""
    from app.advisor import chat_seeds

    makeup_row = _make_row(_MAKEUP_JOB_ID, "makeup_session", "2026-04-21T10:01:00Z")
    repo = _make_repo(makeup_row)

    called_handlers: list[str] = []

    async def _makeup_handler(_ctx):
        called_handlers.append("makeup")
        return {"content": [_image_block()], "is_error": False}

    async def _glowup_handler(_ctx):
        called_handlers.append("glowup")
        return {"content": [_image_block()], "is_error": False}

    with (
        patch("app.advisor.chat_seeds.AdvisorRepository", return_value=repo),
        patch("app.advisor.chat_seeds._handle_get_latest_makeup", _makeup_handler),
        patch("app.advisor.chat_seeds._handle_get_latest_glowup", _glowup_handler),
    ):
        await chat_seeds.build_chat_seeds(
            user_id=_TEST_USER_ID,
            supabase=MagicMock(),
            redis=_FakeRedis(),
            llm=_fake_llm(),
        )

    assert "makeup" in called_handlers


@pytest.mark.asyncio
async def test_glowup_newer_uses_glowup_handler(monkeypatch):
    """Anchor is glowup (most recent) → glowup handler is called."""
    from app.advisor import chat_seeds

    glowup_row = _make_row(_GLOWUP_JOB_ID, "glowup_analysis", "2026-04-21T10:00:00Z")
    repo = _make_repo(glowup_row)

    called_handlers: list[str] = []

    async def _makeup_handler(_ctx):
        called_handlers.append("makeup")
        return {"content": [_image_block()], "is_error": False}

    async def _glowup_handler(_ctx):
        called_handlers.append("glowup")
        return {"content": [_image_block()], "is_error": False}

    with (
        patch("app.advisor.chat_seeds.AdvisorRepository", return_value=repo),
        patch("app.advisor.chat_seeds._handle_get_latest_makeup", _makeup_handler),
        patch("app.advisor.chat_seeds._handle_get_latest_glowup", _glowup_handler),
    ):
        await chat_seeds.build_chat_seeds(
            user_id=_TEST_USER_ID,
            supabase=MagicMock(),
            redis=_FakeRedis(),
            llm=_fake_llm(),
        )

    assert "glowup" in called_handlers


@pytest.mark.asyncio
async def test_neither_returns_fallback(monkeypatch):
    """User with neither glowup nor makeup → FALLBACK_SEEDS."""
    from app.advisor import chat_seeds
    from app.advisor.chat_seed_fallback import FALLBACK_SEEDS

    repo = _make_repo(anchor_row=None)

    with patch("app.advisor.chat_seeds.AdvisorRepository", return_value=repo):
        result = await chat_seeds.build_chat_seeds(
            user_id=_TEST_USER_ID,
            supabase=MagicMock(),
            redis=_FakeRedis(),
            llm=_fake_llm(),
        )

    assert len(result.seeds) == len(FALLBACK_SEEDS)
