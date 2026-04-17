"""Regression guards for the Plan 2026-04-17-003 Unit 2 vision retirement.

Asserts that:

- ``AdvisorService._fetch_vision_content`` no longer exists.
- The eager ``has_visual_trigger`` / ``VISUAL_TRIGGER_KEYWORDS`` path is
  gone from ``app.advisor.context_builder``.
- ``send_message``'s happy path calls ``create_message`` with
  ``vision_content=None`` — vision now arrives ONLY via model-driven
  tool calls (Unit 9 adapter loop), never pre-attached.
- The kill switch ``ADVISOR_TOOLS_ENABLED=False`` is honored — tools are
  not advertised to the adapter and the turn runs text-only without
  crashing.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.advisor import context_builder
from app.advisor import service as service_module
from app.advisor.models import LLMResponse


_TEST_USER_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_TEST_CONVERSATION_ID = "11111111-2222-3333-4444-555555555555"


# ---------------------------------------------------------------------------
# Static invariants — the retired surface must no longer exist.
# ---------------------------------------------------------------------------


def test_fetch_vision_content_attribute_removed_from_service() -> None:
    """``_fetch_vision_content`` must be gone from AdvisorService."""
    assert not hasattr(service_module.AdvisorService, "_fetch_vision_content"), (
        "AdvisorService._fetch_vision_content should be removed in Unit 2 — "
        "vision is model-driven via the MCP tool surface now."
    )


def test_has_visual_trigger_removed_from_context_builder() -> None:
    """``has_visual_trigger`` must be gone from context_builder."""
    assert not hasattr(context_builder, "has_visual_trigger"), (
        "context_builder.has_visual_trigger should be removed — the decision "
        "to fetch vision is now the model's, not a keyword match."
    )


def test_visual_trigger_keywords_removed_from_context_builder() -> None:
    """The keyword tuple must be gone too — no orphan constants."""
    assert not hasattr(context_builder, "VISUAL_TRIGGER_KEYWORDS"), (
        "context_builder.VISUAL_TRIGGER_KEYWORDS should be removed in Unit 2."
    )


def test_has_visual_trigger_not_imported_in_service() -> None:
    """Service module must not re-import the retired trigger function."""
    # Grab the raw module source via its file path to catch even a
    # commented-in import that doesn't hit the namespace.
    from pathlib import Path

    source = Path(service_module.__file__).read_text(encoding="utf-8")
    assert "has_visual_trigger" not in source, (
        "service.py should not reference has_visual_trigger — the eager path is gone."
    )


# ---------------------------------------------------------------------------
# Runtime invariants — send_message does not thread vision_content
# ---------------------------------------------------------------------------


def _build_service_with_captured_adapter(llm_response_text: str) -> tuple[Any, Any]:
    """Return (service, llm_stub) where ``llm_stub.calls`` captures kwargs."""
    repo = MagicMock()
    repo.get_latest_conversation.return_value = {
        "id": _TEST_CONVERSATION_ID,
        "updated_at": "2026-04-17T00:00:00+00:00",
    }
    repo.get_messages.return_value = []
    repo.get_style_profile.return_value = None
    repo.get_latest_analysis_insight.return_value = None
    repo.count_analysis_insights.return_value = 0
    repo.get_recent_nudges_for_context.return_value = []
    repo.insert_message.return_value = {
        "id": "msg_1",
        "role": "advisor",
        "content": llm_response_text,
        "created_at": "2026-04-17T00:00:01+00:00",
    }
    repo.update_conversation_timestamp.return_value = None

    redis_client = MagicMock()
    redis_client.get = AsyncMock(return_value=None)
    redis_client.delete = AsyncMock(return_value=None)
    redis_client.set = AsyncMock(return_value=True)

    llm = MagicMock()
    calls: list[dict[str, Any]] = []

    async def _create_message(**kwargs: Any) -> LLMResponse:
        calls.append(kwargs)
        return LLMResponse(content=llm_response_text)

    llm.create_message = _create_message
    llm.calls = calls

    embedding = MagicMock()

    svc = service_module.AdvisorService(
        advisor_repo=repo,
        redis_client=redis_client,
        llm_adapter=llm,
        embedding_adapter=embedding,
    )

    return svc, llm


@pytest.mark.asyncio
async def test_send_message_passes_vision_content_none_to_adapter(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Happy path: adapter is called without an eager ``vision_content`` payload.

    The retired path always attached image URLs via ``vision_content=``
    whenever any styling keyword hit. Post-Unit-2, the service must
    pass ``None`` — model-driven tool calls are the only vision
    delivery mechanism.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_DEGRADATION_THRESHOLD", 1_000_000)
    monkeypatch.setattr(settings, "ADVISOR_DEBUG_LOG_PROMPT", False)

    svc, llm = _build_service_with_captured_adapter("Yeah, that works.")

    # Sidestep rate-limit Redis path entirely
    async def _no_limit(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr("app.advisor.content_filter.check_rate_limit", _no_limit)

    with caplog.at_level(logging.INFO):
        await svc.send_message(
            _TEST_USER_ID,
            "What hairstyle would suit me?",  # canonical styling query
        )

    assert llm.calls, "adapter was never invoked"
    for call in llm.calls:
        assert call.get("vision_content") is None, (
            f"adapter was handed an eager vision payload: {call.get('vision_content')!r} "
            "— Unit 2 requires vision_content=None on every call."
        )


@pytest.mark.asyncio
async def test_send_message_never_calls_fetch_vision_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_fetch_vision_content`` is fully retired — it must not be called.

    Since the method no longer exists on the service class, an inadvertent
    re-introduction via a helper wrapper would be the only way this test
    could regress. We guard against that by asserting that the retired
    attribute never materializes mid-turn.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_DEGRADATION_THRESHOLD", 1_000_000)

    svc, _llm = _build_service_with_captured_adapter("ok")

    async def _no_limit(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr("app.advisor.content_filter.check_rate_limit", _no_limit)

    await svc.send_message(_TEST_USER_ID, "look at this photo")

    assert not hasattr(svc, "_fetch_vision_content")


# ---------------------------------------------------------------------------
# Kill switch — ADVISOR_TOOLS_ENABLED=False leaves the adapter text-only.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kill_switch_disables_tool_schemas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``ADVISOR_TOOLS_ENABLED=False`` no tool schemas are advertised.

    The service layer still runs, the model is text-only, and no crash
    occurs. Vision simply does not arrive this turn — the plan accepts
    this as a rollback knob, not a parity guarantee.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_TOOLS_ENABLED", False)
    monkeypatch.setattr(settings, "ADVISOR_DEGRADATION_THRESHOLD", 1_000_000)

    svc, llm = _build_service_with_captured_adapter("Yeah, that works.")

    async def _no_limit(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr("app.advisor.content_filter.check_rate_limit", _no_limit)

    await svc.send_message(_TEST_USER_ID, "What hairstyle would suit me?")

    assert llm.calls, "adapter was never invoked"
    for call in llm.calls:
        assert call.get("tools") is None, (
            "kill switch should prevent tool schemas from reaching the adapter"
        )
        assert call.get("tool_registry") is None, (
            "kill switch should prevent the registry from reaching the adapter"
        )
        assert call.get("vision_content") is None, (
            "kill switch should NOT re-enable the eager vision path"
        )
