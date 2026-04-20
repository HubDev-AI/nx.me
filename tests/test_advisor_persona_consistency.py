"""Persona consistency — SOUL.md is the system prompt for chat, nudge, summary.

Spec §1, §12: Ada's voice must be consistent across every surface.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.advisor.persona import SOUL_MD


def _soul_phrase() -> str:
    """Pick a distinctive phrase that only appears in SOUL.md, for system-prompt asserts."""
    # "Never use bullet lists" is unique to SOUL.md Rules section.
    return "Never use bullet lists"


@pytest.mark.asyncio
async def test_nudge_uses_soul_md_as_system(monkeypatch):
    """generate_nudge sends SOUL.md in the Anthropic `system` field."""
    from app.advisor import nudge_scheduler
    from app.advisor.models import LLMResponse

    captured: dict = {}

    async def _capturing_create(**kwargs):
        captured.update(kwargs)
        return LLMResponse(
            content=(
                '{"body": "Your look feels so warm and polished.", '
                '"next_step": {"label": "Ask Ada", '
                '"seed": "What can I do to keep this warmth in my look?"}}'
            ),
            input_tokens=1,
            output_tokens=1,
        )

    fake_llm = SimpleNamespace(create_message=_capturing_create)

    monkeypatch.setattr(nudge_scheduler, "_get_llm_adapter", lambda: fake_llm)

    fake_repo = MagicMock()
    fake_repo.insert_nudge = MagicMock(return_value={"id": str(uuid4())})
    fake_repo.get_style_profile = MagicMock(
        return_value={"content": {"face_shape": "oval"}, "created_at": "2026-01-01"}
    )
    fake_repo.get_recent_nudge_context = MagicMock(return_value=[])
    fake_repo.find_duplicate_body = MagicMock(return_value=False)
    monkeypatch.setattr(
        nudge_scheduler, "AdvisorRepository", MagicMock(return_value=fake_repo)
    )

    # Patch image handlers to return one image block so vision path proceeds.
    async def _fake_glowup(_ctx):
        return {
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": "abc",
                    },
                }
            ],
            "is_error": False,
        }

    monkeypatch.setattr(nudge_scheduler, "_handle_get_latest_glowup", _fake_glowup)

    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis},
        str(uuid4()),
        nudge_scheduler.TRIGGER_POST_GLOWUP,
    )

    assert captured, "LLM adapter was not called"
    assert captured["system"] == SOUL_MD, (
        "Nudge must use SOUL.md as system prompt, not a short mini-persona"
    )
    assert _soul_phrase() in captured["system"]


@pytest.mark.asyncio
async def test_summary_uses_soul_md_as_system(monkeypatch):
    """_summarize_conversation sends SOUL.md in the Anthropic `system` field."""
    from app.advisor import service as advisor_service
    from app.advisor.models import LLMResponse

    captured: dict = {}

    async def _capturing_create(**kwargs):
        captured.update(kwargs)
        return LLMResponse(content="summary text", input_tokens=1, output_tokens=1)

    fake_llm = SimpleNamespace(create_message=_capturing_create)
    fake_repo = MagicMock()
    fake_repo.update_conversation_summary = MagicMock()
    fake_repo.soft_delete_messages = MagicMock()

    # Build a real AdvisorService via __new__ to skip heavy DI.
    svc = advisor_service.AdvisorService.__new__(advisor_service.AdvisorService)
    svc._llm = fake_llm
    svc._repo = fake_repo

    await svc._summarize_conversation(
        str(uuid4()),
        [
            {"role": "user", "content": "hi"},
            {"role": "advisor", "content": "hey"},
        ],
    )

    assert captured["system"] == SOUL_MD
    assert _soul_phrase() in captured["system"]


def test_soul_md_is_nontrivial():
    """Guard against accidental empty/missing file."""
    assert len(SOUL_MD) > 500
    assert "Ada" in SOUL_MD
