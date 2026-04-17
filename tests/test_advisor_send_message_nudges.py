"""End-to-end wiring — ``send_message`` threads nudges into ``build_context``.

Plan 2026-04-17-003 Unit 4, integration. Asserts:

- ``_fetch_context_nudges`` pulls newest-N nudges within the configured
  age window from the repo helper, using ISO ``since`` computed from
  ``settings.ADVISOR_CONTEXT_NUDGE_AGE_DAYS``.
- The resulting 4th system block lands in the ``messages`` list the
  mock LLM adapter sees.
- The payload-logger INFO record's ``nudge_count`` matches the number
  of nudges returned (respects the explicit-count path added alongside
  Unit 4).
- When the user has zero recent nudges, the 3-block shape is preserved
  and ``nudge_count == 0``.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.advisor.models import LLMResponse
from app.advisor.payload_logger import METRIC_KEY_INFO, PAYLOAD_LOGGER_NAME

# The service passes the PRE-STRIP ``messages`` list to ``log_llm_call``,
# then strips system rows before the LLM adapter. Tests intercept the
# logger call to inspect the exact system-block ordering the builder
# emitted (the adapter alone cannot see it).

_TEST_USER_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_CONVERSATION_ID = "11111111-2222-3333-4444-555555555555"


def _stub_repo(
    *,
    nudges: list[dict[str, Any]] | None = None,
    latest_insight: dict | None = None,
) -> MagicMock:
    """Build a repo mock wired for the happy-path ``send_message`` flow."""
    repo = MagicMock()
    # Conversation bootstrap — existing conversation, no inactivity timeout.
    repo.get_latest_conversation.return_value = {
        "id": _CONVERSATION_ID,
        "updated_at": "2099-01-01T00:00:00+00:00",
        "created_at": "2099-01-01T00:00:00+00:00",
    }
    repo.get_messages.return_value = []  # Empty history
    # User-data block: latest analysis insight is optional.
    repo.get_latest_analysis_insight.return_value = latest_insight
    repo.count_analysis_insights.return_value = 0
    # The unit under test.
    repo.get_recent_nudges_for_context.return_value = list(nudges or [])
    # Memory retrieval — pgvector returns nothing so nothing else lands in context.
    repo.match_memories.return_value = []
    # Save path — return a minimal row shape.
    repo.insert_message.return_value = {
        "id": "msg-1",
        "role": "advisor",
        "content": "short reply",
        "created_at": "2026-04-17T00:00:00+00:00",
    }
    return repo


def _build_service(
    repo: MagicMock, llm_response_text: str = "short reply"
) -> tuple[Any, MagicMock]:
    """Construct an AdvisorService with a captured-messages mock LLM."""
    from app.advisor.service import AdvisorService

    redis_client = MagicMock()
    redis_client.get = AsyncMock(return_value=None)
    redis_client.set = AsyncMock(return_value=True)
    redis_client.delete = AsyncMock(return_value=1)
    # Content-filter rate limiter uses ``pipeline`` → override with a
    # minimal stub so the rate check is a no-op.
    redis_client.pipeline = MagicMock()

    llm = MagicMock()
    captured: dict[str, Any] = {}

    async def _create_message(**kwargs: Any) -> LLMResponse:
        # Record only the FIRST call — post-check retries get their own
        # payload log record but the service passes the same messages on
        # the happy path (no hint appended).
        captured.setdefault("kwargs", kwargs)
        return LLMResponse(content=llm_response_text)

    llm.create_message = _create_message

    embedding = MagicMock()
    embedding.compute_embedding = AsyncMock(return_value=[0.0] * 8)

    service = AdvisorService(
        advisor_repo=repo,
        redis_client=redis_client,
        llm_adapter=llm,
        embedding_adapter=embedding,
    )
    return service, type("_Captured", (), {"kwargs": captured})


@pytest.mark.asyncio
async def test_send_message_threads_nudges_into_context(caplog, monkeypatch):
    """3 recent nudges → 4th system block lands in LLM call; nudge_count=3."""
    from app.advisor import content_filter, service as service_module
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_DEBUG_LOG_PROMPT", False)
    monkeypatch.setattr(settings, "ADVISOR_DEGRADATION_THRESHOLD", 1_000_000)
    # Keep the post-check quiet — one call, no retry.
    monkeypatch.setattr(service_module, "_post_check", lambda text, recent: None)
    # Rate-limit check is noisy — short-circuit.
    monkeypatch.setattr(
        content_filter, "check_rate_limit", AsyncMock(return_value=None)
    )

    nudges = [
        {
            "content": "oval face shapes are versatile",
            "trigger": "post_analysis",
            "created_at": "2026-04-17T00:00:00+00:00",
        },
        {
            "content": "loving how the new fringe lands",
            "trigger": "post_glowup",
            "created_at": "2026-04-16T00:00:00+00:00",
        },
        {
            "content": "weekly check-in: what's been landing?",
            "trigger": "weekly_checkin",
            "created_at": "2026-04-15T00:00:00+00:00",
        },
    ]
    repo = _stub_repo(nudges=nudges)
    service, _captured = _build_service(repo)

    # Spy on ``log_llm_call`` so we can inspect the exact pre-strip
    # ``messages`` list the builder emitted (system blocks intact).
    log_calls: list[dict[str, Any]] = []
    real_log = service_module.log_llm_call

    def _spy(logger, **kwargs):
        log_calls.append(kwargs)
        return real_log(logger, **kwargs)

    monkeypatch.setattr(service_module, "log_llm_call", _spy)

    with caplog.at_level(logging.INFO, logger=PAYLOAD_LOGGER_NAME):
        await service.send_message(UUID(_TEST_USER_ID), "What hairstyle would suit me?")

    # --- Pre-strip messages carry the 4th system block ----------------
    assert len(log_calls) == 1
    pre_strip_messages = log_calls[0]["messages"]
    system_blocks = [
        m.get("content", "")
        for m in pre_strip_messages
        if isinstance(m, dict) and m.get("role") == "system"
    ]
    # system[0]=SOUL.md, system[1]=user_data, system[2]=nudges (memories
    # block absent because match_memories=[] yielded no candidates).
    assert len(system_blocks) == 3
    nudge_block = system_blocks[-1]
    nudge_lines = nudge_block.split("\n")
    assert nudge_lines == [
        "nudge (post_analysis): oval face shapes are versatile",
        "nudge (post_glowup): loving how the new fringe lands",
        "nudge (weekly_checkin): weekly check-in: what's been landing?",
    ]

    # --- Payload logger exposes the canonical ``nudge_count`` ---------
    info_records = [
        r for r in caplog.records if getattr(r, "metric", None) == METRIC_KEY_INFO
    ]
    assert len(info_records) == 1
    rec = info_records[0]
    assert rec.nudge_count == 3
    assert rec.system_block_count == 3

    # --- repo-side: the helper was called with the canonical args -----
    repo.get_recent_nudges_for_context.assert_called_once()
    call_kwargs = repo.get_recent_nudges_for_context.call_args.kwargs
    assert call_kwargs["user_id"] == _TEST_USER_ID
    assert call_kwargs["limit"] == settings.ADVISOR_CONTEXT_NUDGE_LIMIT
    # since_iso was computed from settings; assert it is an ISO string in
    # UTC — exact time drifts each test run.
    since_iso = call_kwargs["since_iso"]
    assert isinstance(since_iso, str)
    assert "+00:00" in since_iso or since_iso.endswith("Z")


@pytest.mark.asyncio
async def test_send_message_no_nudges_preserves_three_block_shape(caplog, monkeypatch):
    """Zero recent nudges → no 4th block; nudge_count=0; payload logger intact."""
    from app.advisor import content_filter, service as service_module
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_DEBUG_LOG_PROMPT", False)
    monkeypatch.setattr(settings, "ADVISOR_DEGRADATION_THRESHOLD", 1_000_000)
    monkeypatch.setattr(service_module, "_post_check", lambda text, recent: None)
    monkeypatch.setattr(
        content_filter, "check_rate_limit", AsyncMock(return_value=None)
    )

    repo = _stub_repo(nudges=[])
    service, _captured = _build_service(repo)

    with caplog.at_level(logging.INFO, logger=PAYLOAD_LOGGER_NAME):
        await service.send_message(UUID(_TEST_USER_ID), "Hello")

    info_records = [
        r for r in caplog.records if getattr(r, "metric", None) == METRIC_KEY_INFO
    ]
    rec = info_records[0]
    assert rec.nudge_count == 0
    # SOUL.md + user_data only; memories empty + nudges empty.
    assert rec.system_block_count == 2
