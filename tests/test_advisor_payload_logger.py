"""Tests for ``app.advisor.payload_logger.log_llm_call``.

Plan 2026-04-17-003 Unit 5. Covers:

- INFO record emitted per LLM call with correct counts (memories, nudges,
  vision blocks, system blocks, trim stats).
- User ID is SHA-256 hashed; raw IDs never appear.
- Signed URLs never leak to INFO — only host + expiry-presence.
- DEBUG gated behind ``ADVISOR_DEBUG_LOG_PROMPT``; when off, only INFO.
- Serialization failures fall back to ``repr()`` and never crash.
- Integration: ``_call_llm_with_check`` emits exactly one record per
  ``create_message`` call (two on retry).
"""

from __future__ import annotations

import json
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.advisor.models import LLMResponse
from app.advisor.payload_logger import (
    JSON_SERIALIZATION_FAILURE_MARKER,
    METRIC_KEY_DEBUG,
    METRIC_KEY_INFO,
    PAYLOAD_LOGGER_NAME,
    USER_ID_HASH_LENGTH,
    _hash_user_id,
    log_llm_call,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_TEST_USER_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_TEST_CONVERSATION_ID = "11111111-2222-3333-4444-555555555555"
_TEST_MODEL = "claude-sonnet-4-6"
_SUPABASE_SIGNED_URL = (
    "https://example.supabase.co/storage/v1/object/sign/images/path.jpg"
    "?token=abc.def.ghi&expires=1234567890"
)


def _sample_context_messages(
    memory_lines: int = 2,
    nudge_lines: int = 3,
    include_nudges: bool = True,
) -> list[dict[str, Any]]:
    """Return a messages list mirroring ``build_context`` shape.

    Layout: SOUL.md (system), user_data (system), memories (system),
    nudges (system, optional), conversation turns, final user message.
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "SOUL.md persona instructions"},
        {"role": "system", "content": "oval face, symmetry 0.87, 4 analyses"},
    ]
    memories_content = "\n".join(f"memory line {i}" for i in range(memory_lines))
    messages.append({"role": "system", "content": memories_content})

    if include_nudges:
        nudges_content = "\n".join(f"nudge line {i}" for i in range(nudge_lines))
        messages.append({"role": "system", "content": nudges_content})

    messages.extend(
        [
            {"role": "user", "content": "earlier user turn"},
            {"role": "advisor", "content": "earlier advisor reply"},
            {"role": "user", "content": "What hairstyle would suit me?"},
        ]
    )
    return messages


def _vision_content_with_signed_urls() -> list[dict[str, Any]]:
    return [
        {
            "type": "image",
            "source": {"type": "url", "url": _SUPABASE_SIGNED_URL},
        },
        {
            "type": "image",
            "source": {
                "type": "url",
                "url": _SUPABASE_SIGNED_URL.replace("path.jpg", "after.jpg"),
            },
        },
    ]


def _find_record(caplog: pytest.LogCaptureFixture, metric: str) -> logging.LogRecord:
    """Return the single LogRecord whose ``metric`` attr matches ``metric``."""
    records = [r for r in caplog.records if getattr(r, "metric", None) == metric]
    assert len(records) == 1, (
        f"expected exactly one record for metric={metric!r}, "
        f"got {len(records)}: {records!r}"
    )
    return records[0]


# ---------------------------------------------------------------------------
# Happy-path counts
# ---------------------------------------------------------------------------


def test_log_llm_call_emits_expected_counts(caplog, monkeypatch):
    """4 system blocks + 2 memories + 3 nudges + 2 vision blocks → correct counts.

    Asserts no raw user_id and no full signed URL appear in the INFO record.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_DEBUG_LOG_PROMPT", False)

    messages = _sample_context_messages(memory_lines=2, nudge_lines=3)
    vision = _vision_content_with_signed_urls()

    with caplog.at_level(logging.INFO, logger=PAYLOAD_LOGGER_NAME):
        log_llm_call(
            None,
            model=_TEST_MODEL,
            user_id=_TEST_USER_ID,
            conversation_id=_TEST_CONVERSATION_ID,
            system="SOUL.md persona instructions",
            messages=messages,
            vision_content=vision,
            trimmed=False,
            dropped=0,
        )

    rec = _find_record(caplog, METRIC_KEY_INFO)
    # Counts
    assert rec.system_block_count == 4  # system str + 3 system-role msgs
    assert rec.memory_count == 2
    assert rec.nudge_count == 3
    assert rec.vision_block_count == 2
    assert rec.model == _TEST_MODEL
    assert rec.user_id_hash == _hash_user_id(_TEST_USER_ID)
    assert len(rec.user_id_hash) == USER_ID_HASH_LENGTH

    # Redaction — raw user_id never appears
    dumped = json.dumps(rec.__dict__, default=str)
    assert _TEST_USER_ID not in dumped

    # Redaction — full signed URL never appears at INFO
    assert _SUPABASE_SIGNED_URL not in dumped
    assert "abc.def.ghi" not in dumped  # raw token from URL

    # Safe URL metadata is present
    sources = rec.vision_sources
    assert isinstance(sources, list)
    assert all(src["host"] == "example.supabase.co" for src in sources)
    assert all(src["has_expiry_token"] == "true" for src in sources)


def test_log_llm_call_user_message_length_is_last_user_turn(caplog):
    """``user_message_length`` measures the FINAL user turn, not the entire chat."""
    messages = _sample_context_messages()
    final_user_len = len("What hairstyle would suit me?")

    with caplog.at_level(logging.INFO, logger=PAYLOAD_LOGGER_NAME):
        log_llm_call(
            None,
            model=_TEST_MODEL,
            user_id=_TEST_USER_ID,
            conversation_id=_TEST_CONVERSATION_ID,
            system="SOUL.md persona instructions",
            messages=messages,
            vision_content=None,
            trimmed=False,
            dropped=0,
        )

    rec = _find_record(caplog, METRIC_KEY_INFO)
    assert rec.user_message_length == final_user_len


def test_log_llm_call_total_input_tokens_est_nonzero(caplog):
    """``total_input_tokens_est`` is derived across system + messages, not zero."""
    messages = _sample_context_messages()

    with caplog.at_level(logging.INFO, logger=PAYLOAD_LOGGER_NAME):
        log_llm_call(
            None,
            model=_TEST_MODEL,
            user_id=_TEST_USER_ID,
            conversation_id=_TEST_CONVERSATION_ID,
            system="SOUL.md persona instructions",
            messages=messages,
            vision_content=None,
            trimmed=False,
            dropped=0,
        )

    rec = _find_record(caplog, METRIC_KEY_INFO)
    assert isinstance(rec.total_input_tokens_est, int)
    assert rec.total_input_tokens_est > 0


# ---------------------------------------------------------------------------
# DEBUG gating
# ---------------------------------------------------------------------------


def test_debug_off_emits_only_info(caplog, monkeypatch):
    """``ADVISOR_DEBUG_LOG_PROMPT=False`` → only INFO, no DEBUG record."""
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_DEBUG_LOG_PROMPT", False)

    messages = _sample_context_messages()

    with caplog.at_level(logging.DEBUG, logger=PAYLOAD_LOGGER_NAME):
        log_llm_call(
            None,
            model=_TEST_MODEL,
            user_id=_TEST_USER_ID,
            conversation_id=_TEST_CONVERSATION_ID,
            system="SOUL.md persona instructions",
            messages=messages,
            vision_content=None,
            trimmed=False,
            dropped=0,
        )

    info_records = [
        r for r in caplog.records if getattr(r, "metric", None) == METRIC_KEY_INFO
    ]
    debug_records = [
        r for r in caplog.records if getattr(r, "metric", None) == METRIC_KEY_DEBUG
    ]
    assert len(info_records) == 1
    assert len(debug_records) == 0


def test_debug_on_emits_info_plus_full_payload(caplog, monkeypatch):
    """``ADVISOR_DEBUG_LOG_PROMPT=True`` → INFO + DEBUG with full system + messages."""
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_DEBUG_LOG_PROMPT", True)

    messages = _sample_context_messages()
    vision = _vision_content_with_signed_urls()
    system_str = "SOUL.md persona instructions"

    with caplog.at_level(logging.DEBUG, logger=PAYLOAD_LOGGER_NAME):
        log_llm_call(
            None,
            model=_TEST_MODEL,
            user_id=_TEST_USER_ID,
            conversation_id=_TEST_CONVERSATION_ID,
            system=system_str,
            messages=messages,
            vision_content=vision,
            trimmed=False,
            dropped=0,
        )

    info = _find_record(caplog, METRIC_KEY_INFO)
    debug = _find_record(caplog, METRIC_KEY_DEBUG)
    assert info.user_id_hash == _hash_user_id(_TEST_USER_ID)
    assert debug.user_id_hash == _hash_user_id(_TEST_USER_ID)
    # DEBUG carries full system + messages
    assert debug.system == system_str
    assert debug.messages == messages
    assert debug.vision_content == vision


# ---------------------------------------------------------------------------
# Edge cases — vision, trimmed, dropped
# ---------------------------------------------------------------------------


def test_vision_none_zero_count_no_url_fields(caplog):
    """``vision_content=None`` → ``vision_block_count=0``; no vision_sources field."""
    messages = _sample_context_messages()

    with caplog.at_level(logging.INFO, logger=PAYLOAD_LOGGER_NAME):
        log_llm_call(
            None,
            model=_TEST_MODEL,
            user_id=_TEST_USER_ID,
            conversation_id=_TEST_CONVERSATION_ID,
            system="SOUL.md persona instructions",
            messages=messages,
            vision_content=None,
            trimmed=False,
            dropped=0,
        )

    rec = _find_record(caplog, METRIC_KEY_INFO)
    assert rec.vision_block_count == 0
    # vision_sources should not be attached when there are no blocks
    assert not hasattr(rec, "vision_sources") or rec.vision_sources in (None, [], "")


def test_trimmed_and_dropped_surface_at_info(caplog):
    """``trimmed=True, dropped=2`` → both surface at INFO."""
    messages = _sample_context_messages()

    with caplog.at_level(logging.INFO, logger=PAYLOAD_LOGGER_NAME):
        log_llm_call(
            None,
            model=_TEST_MODEL,
            user_id=_TEST_USER_ID,
            conversation_id=_TEST_CONVERSATION_ID,
            system="SOUL.md persona instructions",
            messages=messages,
            vision_content=None,
            trimmed=True,
            dropped=2,
        )

    rec = _find_record(caplog, METRIC_KEY_INFO)
    assert rec.trimmed is True
    assert rec.dropped == 2


# ---------------------------------------------------------------------------
# Redaction / security
# ---------------------------------------------------------------------------


def test_signed_url_never_appears_in_info_record(caplog):
    """Signed URLs with tokens never leak to INFO, even in human message."""
    messages = _sample_context_messages()
    vision = _vision_content_with_signed_urls()

    with caplog.at_level(logging.INFO, logger=PAYLOAD_LOGGER_NAME):
        log_llm_call(
            None,
            model=_TEST_MODEL,
            user_id=_TEST_USER_ID,
            conversation_id=_TEST_CONVERSATION_ID,
            system="SOUL.md",
            messages=messages,
            vision_content=vision,
            trimmed=False,
            dropped=0,
        )

    rec = _find_record(caplog, METRIC_KEY_INFO)
    # Both human message and all extras are checked
    full_text = rec.getMessage() + "||" + json.dumps(rec.__dict__, default=str)
    assert "/storage/v1/object/sign/" not in full_text
    assert "abc.def.ghi" not in full_text
    assert _TEST_USER_ID not in full_text


def test_user_id_hashing_is_deterministic_and_short():
    """Hashing is deterministic and truncated to ``USER_ID_HASH_LENGTH`` chars."""
    hashed_a = _hash_user_id(_TEST_USER_ID)
    hashed_b = _hash_user_id(UUID(_TEST_USER_ID))
    assert hashed_a == hashed_b
    assert len(hashed_a) == USER_ID_HASH_LENGTH
    assert hashed_a != _TEST_USER_ID[:USER_ID_HASH_LENGTH]


# ---------------------------------------------------------------------------
# Serialization failure path
# ---------------------------------------------------------------------------


class _Unserializable:
    """Object that neither serializes as JSON nor as a clean repr."""

    def __repr__(self) -> str:
        return "_Unserializable()"


def test_serialization_failure_falls_back_to_repr(caplog):
    """Non-JSON-serializable message content → logger falls back to repr, never crashes."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "SOUL.md"},
        {"role": "user", "content": _Unserializable()},  # type: ignore[dict-item]
    ]

    with caplog.at_level(logging.INFO, logger=PAYLOAD_LOGGER_NAME):
        # Must not raise
        log_llm_call(
            None,
            model=_TEST_MODEL,
            user_id=_TEST_USER_ID,
            conversation_id=_TEST_CONVERSATION_ID,
            system="SOUL.md",
            messages=messages,
            vision_content=None,
            trimmed=False,
            dropped=0,
        )

    rec = _find_record(caplog, METRIC_KEY_INFO)
    # role_breakdown is serializable (it's just {str: int}), so it survives
    # as-is. The record was still emitted — no crash.
    assert rec.role_breakdown == {"system": 1, "user": 1}


def test_serialization_failure_on_debug_path_still_emits(caplog, monkeypatch):
    """DEBUG path: unserializable messages → emit record with fallback marker."""
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_DEBUG_LOG_PROMPT", True)

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": _Unserializable()},  # type: ignore[dict-item]
    ]

    with caplog.at_level(logging.DEBUG, logger=PAYLOAD_LOGGER_NAME):
        log_llm_call(
            None,
            model=_TEST_MODEL,
            user_id=_TEST_USER_ID,
            conversation_id=_TEST_CONVERSATION_ID,
            system="SOUL.md",
            messages=messages,
            vision_content=None,
            trimmed=False,
            dropped=0,
        )

    debug = _find_record(caplog, METRIC_KEY_DEBUG)
    # The ``messages`` field should carry the fallback marker rather than the raw object.
    serialized = json.dumps(debug.messages, default=str)
    assert JSON_SERIALIZATION_FAILURE_MARKER in serialized


# ---------------------------------------------------------------------------
# Integration: _call_llm_with_check emits one record per create_message call
# ---------------------------------------------------------------------------


def _make_service_with_mock_llm(llm_responses: list[str]):
    """Return an AdvisorService with a mocked LLM returning canned text.

    Minimal plumbing — we drive ``_call_llm_with_check`` directly, so
    conversation + repo side effects don't fire.
    """
    from app.advisor.service import AdvisorService

    repo = MagicMock()
    redis_client = MagicMock()
    redis_client.get = AsyncMock(return_value=None)  # below degradation threshold

    llm = MagicMock()
    responses_iter = iter(llm_responses)

    async def _create_message(**kwargs: Any) -> LLMResponse:
        return LLMResponse(content=next(responses_iter))

    llm.create_message = _create_message

    embedding = MagicMock()

    return AdvisorService(
        advisor_repo=repo,
        redis_client=redis_client,
        llm_adapter=llm,
        embedding_adapter=embedding,
    )


@pytest.mark.asyncio
async def test_call_llm_with_check_emits_one_record_per_call(caplog, monkeypatch):
    """Single successful LLM call → exactly one INFO record."""
    from app.advisor import service as service_module
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_DEBUG_LOG_PROMPT", False)
    # Force Sonnet path — no degradation lookup noise
    monkeypatch.setattr(settings, "ADVISOR_DEGRADATION_THRESHOLD", 1_000_000)
    # Keep post_check short-circuited: no prior advisor messages, single-sentence reply.
    monkeypatch.setattr(
        service_module,
        "_post_check",
        lambda text, recent: None,
    )

    svc = _make_service_with_mock_llm(["A clean short answer."])

    with caplog.at_level(logging.INFO, logger=PAYLOAD_LOGGER_NAME):
        text = await svc._call_llm_with_check(
            user_id=UUID(_TEST_USER_ID),
            conversation_id=_TEST_CONVERSATION_ID,
            messages=_sample_context_messages(),
            vision_content=None,
            recent_responses=[],
            dropped=0,
        )

    assert text == "A clean short answer."
    info_records = [
        r for r in caplog.records if getattr(r, "metric", None) == METRIC_KEY_INFO
    ]
    assert len(info_records) == 1


@pytest.mark.asyncio
async def test_call_llm_with_check_emits_two_records_on_retry(caplog, monkeypatch):
    """Retry path: two ``create_message`` calls → two INFO records."""
    from app.advisor import service as service_module
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_DEBUG_LOG_PROMPT", False)
    monkeypatch.setattr(settings, "ADVISOR_DEGRADATION_THRESHOLD", 1_000_000)

    # First call triggers retry via post-check hint, second returns clean.
    hint_once = iter([None])

    def _post_check(_text: str, _recent: list[str]) -> str | None:
        try:
            next(hint_once)
            return "Shorter. Say less."
        except StopIteration:
            return None

    monkeypatch.setattr(service_module, "_post_check", _post_check)

    svc = _make_service_with_mock_llm(["First long reply.", "Short reply."])

    with caplog.at_level(logging.INFO, logger=PAYLOAD_LOGGER_NAME):
        text = await svc._call_llm_with_check(
            user_id=UUID(_TEST_USER_ID),
            conversation_id=_TEST_CONVERSATION_ID,
            messages=_sample_context_messages(),
            vision_content=None,
            recent_responses=[],
            dropped=0,
        )

    assert text == "Short reply."
    info_records = [
        r for r in caplog.records if getattr(r, "metric", None) == METRIC_KEY_INFO
    ]
    assert len(info_records) == 2
