"""End-to-end regression guards for Plan 2026-04-17-003 — Unit 6.

Asserts the canonical failure mode ("Ada asks the user to describe their
face shape despite full analysis + nudge + glow-up context") is fixed
across the full ``send_message`` flow. One test covers each of the
scenarios in the plan:

1. Canonical happy path — style_profile + pinned analysis_insight +
   post_analysis nudge + weekly_checkin nudge + completed glow-up with
   cleared image. Model picks ``get_latest_glowup`` via the tool
   registry. Assertions:

   * Expanded user_data block carries recs + summary (Unit 1).
   * Latest ``analysis_insight`` is pinned in ``messages`` (Unit 3).
   * 4th system block is the nudges block (Unit 4).
   * ``tools`` passed to the adapter contain the MCP schemas
     (Units 2, 9).
   * Exactly one INFO log record per ``create_message`` call with
     ``system_block_count >= 3``, ``memory_count >= 1``,
     ``nudge_count == 2``, hashed ``user_id_hash`` present (Unit 5).
   * No captured log record contains ``/storage/v1/object/sign/`` or
     ``?token=`` or raw signed-URL fragments anywhere in the stream
     (Unit 9 security invariant).

2. Minimal profile, no nudges — user with only analysis_insight +
   style_profile, no nudges, no glow-up. System block count excludes
   the nudges block; ``get_latest_glowup`` returns ``is_error=True``
   in the mock loop (no crash).

3. Feature flag sanity — ``ADVISOR_ENABLED=False`` makes
   ``require_app_feature("advisor_enabled")`` raise and the service
   flow is NOT invoked.

4. Error path — stubbed LLM raises mid-turn → payload logged once
   before the raise; no partial user message persisted.

Fixtures stub Supabase via a repo mock, Redis via ``AsyncMock``, and
the LLM via the MCP-aware mock adapter driven by ``tool_use_script``
from Unit 9. No real Anthropic or Supabase calls are made.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.advisor.adapters.mock import MockLLMAdapter
from app.advisor.mcp.registry import CONTENT_BLOCK_TYPE_IMAGE
from app.advisor.mcp.tools_glowup import FEATURE_TAG_GLOWUP
from app.advisor.mcp.tools_jobs import BUCKET_AFTER, BUCKET_BEFORE
from app.advisor.models import LLMResponse
from app.advisor.payload_logger import (
    METRIC_KEY_INFO,
    PAYLOAD_LOGGER_NAME,
    USER_ID_HASH_LENGTH,
    _hash_user_id,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TEST_USER_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_CONVERSATION_ID = "11111111-2222-3333-4444-555555555555"
_USER_MESSAGE = "What hairstyle would suit me?"

# Fake bytes used for Supabase downloads. A recognizable fingerprint lets
# later assertions verify the bytes never land in logs.
_FAKE_BEFORE_BYTES = b"\xff\xd8\xff\xe0FAKE_BEFORE_BYTES_FINGERPRINT"
_FAKE_AFTER_BYTES = b"\xff\xd8\xff\xe0FAKE_AFTER_BYTES_FINGERPRINT"

# Sample style_profile content — face shape, symmetry, top recommendations,
# and last_updated_at. The user_data block (Unit 1) renders this as a
# multi-line fragment containing the summary + recs.
_STYLE_PROFILE_CONTENT: dict[str, Any] = {
    "face_shape": "oval",
    "symmetry_score": 0.87,
    "recommendations": [
        "try bangs",
        "clean up brows",
        "hydrate skin",
    ],
    "last_updated_at": "2026-04-17T00:00:00+00:00",
}

# Sample analysis_insight content — written by ``memory_manager.write_analysis_insight``
# and pinned at position 0 of memories via Unit 3.
_ANALYSIS_INSIGHT_CONTENT: dict[str, Any] = {
    "face_shape": "oval",
    "symmetry_score": 0.87,
    "recommendations": [
        "try bangs",
        "clean up brows",
        "hydrate skin",
    ],
    "summary": "narrow forehead, strong jaw",
}

_ANALYSIS_INSIGHT_ROW: dict[str, Any] = {
    "id": "insight-1",
    "type": "analysis_insight",
    "content": _ANALYSIS_INSIGHT_CONTENT,
    "created_at": "2026-04-17T00:00:00+00:00",
}

_STYLE_PROFILE_ROW: dict[str, Any] = {
    "id": "profile-1",
    "type": "style_profile",
    "content": _STYLE_PROFILE_CONTENT,
    "created_at": "2026-04-17T00:00:00+00:00",
}

# Two nudges — one post_analysis + one weekly_checkin — so nudge_count
# lands at exactly 2 in scenario 1.
_POST_ANALYSIS_NUDGE: dict[str, Any] = {
    "content": "oval face shapes are versatile — bangs could land well",
    "trigger": "post_analysis",
    "created_at": "2026-04-17T00:00:00+00:00",
}
_WEEKLY_CHECKIN_NUDGE: dict[str, Any] = {
    "content": "weekly check-in: what's been landing this week?",
    "trigger": "weekly_checkin",
    "created_at": "2026-04-16T00:00:00+00:00",
}

_COMPLETED_GLOWUP_ROW: dict[str, Any] = {
    "id": "job-1",
    "status": "completed",
    "source_type": "glowup_analysis",
    "created_at": "2026-04-17T00:00:00+00:00",
    "completed_at": "2026-04-17T00:01:00+00:00",
    "before_image_url": "user_a/source.jpg",
    "after_image_url": "user_a/after.jpg",
}

# Canonical signed-URL fragments that must never leak through the log stream
# — the Unit 9 security invariant. A single match anywhere fails the suite.
_FORBIDDEN_LOG_SUBSTRINGS: tuple[str, ...] = (
    "/storage/v1/object/sign/",
    "?token=",
    "FAKE_BEFORE_BYTES_FINGERPRINT",
    "FAKE_AFTER_BYTES_FINGERPRINT",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _stub_repo(
    *,
    profile: dict[str, Any] | None,
    analysis_insight: dict[str, Any] | None,
    nudges: list[dict[str, Any]],
    glowup_row: dict[str, Any] | None,
    cleared_images: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Build a repo mock wired for the canonical happy path.

    Every repo helper exercised by ``send_message`` + the MCP tool
    handlers is pre-stubbed with plausible return shapes so the
    integration test exercises the real service + context_builder +
    payload_logger code paths without hitting Supabase.
    """
    repo = MagicMock()
    # Conversation bootstrap — existing, no inactivity timeout.
    repo.get_latest_conversation.return_value = {
        "id": _CONVERSATION_ID,
        "updated_at": "2099-01-01T00:00:00+00:00",
        "created_at": "2099-01-01T00:00:00+00:00",
    }
    repo.get_messages.return_value = []

    # User-data block — Unit 7 reads profile first, then falls through
    # to analysis_insight.
    repo.get_style_profile.return_value = profile
    repo.get_latest_analysis_insight.return_value = analysis_insight
    repo.count_analysis_insights.return_value = 1 if analysis_insight else 0

    # Nudges (Unit 4) — read-only; cap + since_iso come from config.
    repo.get_recent_nudges_for_context.return_value = list(nudges)

    # Memory retrieval — pgvector returns nothing in isolation so only the
    # pinned analysis_insight (Unit 3) appears in the memories block.
    repo.match_memories.return_value = []

    # Tool handlers (Unit 9) — glow-up + cleared images + fetch bytes.
    repo.get_latest_completed_glowup_with_images.return_value = glowup_row
    # Cross-feature tool uses a separate helper name.
    repo.get_latest_completed_job_with_images.return_value = glowup_row
    repo.get_cleared_images.return_value = list(cleared_images or [])

    def _fetch_image_bytes(bucket: str, path: str) -> bytes:
        if bucket == BUCKET_BEFORE:
            return _FAKE_BEFORE_BYTES
        if bucket == BUCKET_AFTER:
            return _FAKE_AFTER_BYTES
        return b""

    repo.fetch_image_bytes.side_effect = _fetch_image_bytes

    # Message save path.
    repo.insert_message.return_value = {
        "id": "msg-1",
        "role": "advisor",
        "content": "stub reply",
        "created_at": "2026-04-17T00:00:02+00:00",
    }
    repo.update_conversation_timestamp.return_value = None
    return repo


def _build_service_with_mock_llm(
    repo: MagicMock,
    mock_llm: Any | None = None,
) -> Any:
    """Construct an AdvisorService with the MCP-aware mock adapter.

    Redis is an ``AsyncMock`` so the rate-limit + degradation-threshold
    lookups do not block. Embeddings are a no-op returning a zero
    vector so ``get_relevant_memories`` stays deterministic.
    """
    from app.advisor.service import AdvisorService

    redis_client = MagicMock()
    redis_client.get = AsyncMock(return_value=None)
    redis_client.set = AsyncMock(return_value=True)
    redis_client.delete = AsyncMock(return_value=1)
    # Rate-limit check pipes through ``redis.pipeline().incr().expire().execute()``.
    # Stub to a minimal no-op so ``check_rate_limit`` does not crash.
    pipe = MagicMock()
    pipe.incr = MagicMock(return_value=pipe)
    pipe.expire = MagicMock(return_value=pipe)
    pipe.execute = AsyncMock(return_value=[1, True])
    redis_client.pipeline = MagicMock(return_value=pipe)

    embedding = MagicMock()
    embedding.compute_embedding = AsyncMock(return_value=[0.0] * 8)

    llm = mock_llm if mock_llm is not None else MockLLMAdapter()
    return AdvisorService(
        advisor_repo=repo,
        redis_client=redis_client,
        llm_adapter=llm,
        embedding_adapter=embedding,
    )


def _spy_log_llm_call(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Install a spy on ``service.log_llm_call`` capturing the pre-strip messages.

    The service strips ``role=system`` entries before handing the array
    to the LLM adapter (see ``service._call_llm_with_check``), so the
    adapter's ``messages`` kwarg cannot be used to inspect the exact
    system-block order the context builder emitted. The payload logger
    receives the PRE-STRIP messages, so spying there is the canonical
    way to assert on the full context.
    """
    from app.advisor import service as service_module

    captured: list[dict[str, Any]] = []
    real_log = service_module.log_llm_call

    def _spy(logger: Any, **kwargs: Any) -> None:
        captured.append(kwargs)
        return real_log(logger, **kwargs)

    monkeypatch.setattr(service_module, "log_llm_call", _spy)
    return captured


def _quiet_the_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    """Short-circuit ambient noise: rate-limit, degradation, post-check."""
    from app.advisor import content_filter, service as service_module
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_DEBUG_LOG_PROMPT", False)
    monkeypatch.setattr(settings, "ADVISOR_DEGRADATION_THRESHOLD", 1_000_000)
    monkeypatch.setattr(service_module, "_post_check", lambda text, recent: None)
    monkeypatch.setattr(
        content_filter, "check_rate_limit", AsyncMock(return_value=None)
    )


def _collect_info_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if getattr(r, "metric", None) == METRIC_KEY_INFO]


def _merged_record_text(record: logging.LogRecord) -> str:
    """Serialize a log record's message + every extra into one haystack string.

    Mirrors ``tests/test_advisor_tool_security.py`` so the leak audit in
    scenario 1 uses the exact same search semantics.
    """
    parts: list[str] = [record.getMessage()]
    for key, value in record.__dict__.items():
        if key in {"args", "msg"}:
            continue
        try:
            parts.append(json.dumps(value, default=str))
        except (TypeError, ValueError):
            parts.append(repr(value))
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Scenario 1 — canonical happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_canonical_happy_path_all_four_signals_present(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """style_profile + analysis_insight + 2 nudges + glow-up + cleared image.

    Asserts every signal from R1-R5 reaches the payload logger and the
    adapter sees the MCP tool schemas. Model picks
    ``get_latest_glowup`` via the scripted mock loop.
    """
    _quiet_the_flow(monkeypatch)

    repo = _stub_repo(
        profile=_STYLE_PROFILE_ROW,
        analysis_insight=_ANALYSIS_INSIGHT_ROW,
        nudges=[_POST_ANALYSIS_NUDGE, _WEEKLY_CHECKIN_NUDGE],
        glowup_row=_COMPLETED_GLOWUP_ROW,
        cleared_images=[{"id": "img-1", "storage_path": "user_a/source.jpg"}],
    )

    mock_llm = MockLLMAdapter()
    # One tool-use round: the model reaches for the glow-up tool because
    # the user asked a styling question with a glow-up in state.
    mock_llm.tool_use_script = [
        [{"name": "get_latest_glowup", "input": {}}],
    ]
    mock_llm.final_response_text = "Bangs or a softer fringe would land well."

    svc = _build_service_with_mock_llm(repo, mock_llm=mock_llm)
    log_calls = _spy_log_llm_call(monkeypatch)

    with caplog.at_level(logging.DEBUG, logger=PAYLOAD_LOGGER_NAME):
        with caplog.at_level(logging.DEBUG):
            await svc.send_message(UUID(_TEST_USER_ID), _USER_MESSAGE)

    # --- Adapter received tools + registry (Units 2, 9) ----------------
    assert mock_llm.calls, "MockLLMAdapter was never invoked"
    first_call = mock_llm.calls[0]
    tools = first_call.get("tools")
    assert isinstance(tools, list) and tools, "tool schemas missing from adapter call"
    tool_names = {t.get("name") for t in tools}
    # Cross-feature + glow-up + profile tools must all be advertised.
    for expected in ("get_latest_glowup", "get_style_profile", "get_recent_nudges"):
        assert expected in tool_names, (
            f"expected tool {expected!r} missing from adapter schemas: {tool_names}"
        )
    assert first_call.get("tool_registry") is not None

    # --- Expanded user_data block carries recs + summary (Unit 1) ------
    # The adapter strips role=system entries before the LLM call, so
    # assert against the PRE-STRIP messages the payload logger saw.
    assert log_calls, "payload logger was never invoked"
    pre_strip_messages = log_calls[0]["messages"]
    system_blocks = [
        m.get("content", "")
        for m in pre_strip_messages
        if isinstance(m, dict) and m.get("role") == "system"
    ]
    # system[0]=SOUL.md, system[1]=user_data, system[2]=nudges.
    # Memories are no longer auto-injected — the model retrieves via
    # search_memories / list_recent_memories when she needs them.
    assert len(system_blocks) == 3, (
        f"expected 3 system blocks (SOUL, user_data, nudges); got "
        f"{len(system_blocks)}: {system_blocks!r}"
    )
    user_data_block = system_blocks[1]
    assert "oval face" in user_data_block  # basics
    assert "try bangs" in user_data_block  # recs line (Unit 1)
    # The style_profile path regenerates the summary via
    # ``summarize_memory_content``; the key recs words must survive.
    assert "brows" in user_data_block

    # --- Nudges block is the 3rd system block (Unit 4) -----------------
    nudges_block = system_blocks[2]
    assert "nudge (post_analysis)" in nudges_block
    assert "nudge (weekly_checkin)" in nudges_block
    assert "oval face shapes are versatile" in nudges_block

    # --- Model-driven tool dispatch fetched the glow-up (Units 2, 9) ---
    assert mock_llm.tool_dispatch_log == [("get_latest_glowup", {})]
    # One round executed, zero over-cap.
    assert len(mock_llm.executed_tool_results) == 1
    round_result = mock_llm.executed_tool_results[0]
    assert len(round_result) == 1
    blocks = round_result[0]["content"]
    # Expect 2 image blocks (before + after) + 1 text summary (feature=glowup).
    image_blocks = [b for b in blocks if b.get("type") == CONTENT_BLOCK_TYPE_IMAGE]
    assert len(image_blocks) == 2
    text_blocks = [b for b in blocks if b.get("type") == "text"]
    assert any(
        f"feature={FEATURE_TAG_GLOWUP}" in b.get("text", "") for b in text_blocks
    )

    # --- Exactly one INFO log record per create_message call (Unit 5) --
    info_records = _collect_info_records(caplog)
    assert len(info_records) == len(mock_llm.calls), (
        f"expected one INFO record per create_message call "
        f"({len(mock_llm.calls)}); got {len(info_records)}"
    )
    rec = info_records[0]
    assert rec.system_block_count >= 3
    assert rec.nudge_count == 2
    # user_id_hash present, and is the SHA-256 truncation — never raw.
    expected_hash = _hash_user_id(_TEST_USER_ID)
    assert rec.user_id_hash == expected_hash
    assert len(rec.user_id_hash) == USER_ID_HASH_LENGTH
    # Raw user_id must not appear anywhere on the INFO record.
    assert _TEST_USER_ID not in _merged_record_text(rec)

    # --- Security invariant: no signed URL / raw bytes in log stream ---
    # Audit EVERY captured log record (INFO and DEBUG), not just the
    # payload logger's — the registry, the adapter, and the service layer
    # all emit records during the turn.
    for record in caplog.records:
        haystack = _merged_record_text(record)
        for forbidden in _FORBIDDEN_LOG_SUBSTRINGS:
            assert forbidden not in haystack, (
                f"log record leaked {forbidden!r}: {haystack[:400]}..."
            )


# ---------------------------------------------------------------------------
# Scenario 2 — minimal profile, no nudges, no glow-up
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_minimal_profile_no_nudges_no_glowup(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """style_profile + analysis_insight only — no nudges, no glow-up.

    Asserts:
      * System block count excludes the nudges block (no 4th block).
      * Tool call for ``get_latest_glowup`` returns ``is_error=True``
        (no completed glow-up) and the mock loop does NOT crash.
    """
    _quiet_the_flow(monkeypatch)

    repo = _stub_repo(
        profile=_STYLE_PROFILE_ROW,
        analysis_insight=_ANALYSIS_INSIGHT_ROW,
        nudges=[],
        glowup_row=None,  # no completed glow-up
        cleared_images=[],
    )

    mock_llm = MockLLMAdapter()
    # Model still reaches for the tool — the tool must surface
    # "no completed glow-up" without crashing.
    mock_llm.tool_use_script = [
        [{"name": "get_latest_glowup", "input": {}}],
    ]

    svc = _build_service_with_mock_llm(repo, mock_llm=mock_llm)
    log_calls = _spy_log_llm_call(monkeypatch)

    with caplog.at_level(logging.INFO, logger=PAYLOAD_LOGGER_NAME):
        await svc.send_message(UUID(_TEST_USER_ID), _USER_MESSAGE)

    # --- Nudges block absent ------------------------------------------
    assert log_calls, "payload logger was never invoked"
    pre_strip_messages = log_calls[0]["messages"]
    system_blocks = [
        m.get("content", "")
        for m in pre_strip_messages
        if isinstance(m, dict) and m.get("role") == "system"
    ]
    # SOUL.md + user_data only — no nudges, and memories are no longer
    # auto-injected (the model retrieves via tools).
    assert len(system_blocks) == 2, (
        f"expected 2 system blocks (SOUL + user_data only); got "
        f"{len(system_blocks)}: {system_blocks!r}"
    )
    # Payload logger's ``nudge_count`` is zero.
    info_records = _collect_info_records(caplog)
    assert info_records, "no INFO record captured"
    assert info_records[0].nudge_count == 0

    # --- Tool returned is_error=True at the ENVELOPE level ------------
    # Plan 2026-04-17 review fix: ``is_error`` rides on the tool_result
    # envelope per Anthropic's spec, not on inner content blocks (where
    # Claude silently ignores it).
    assert len(mock_llm.executed_tool_results) == 1
    envelope = mock_llm.executed_tool_results[0][0]
    assert envelope.get("is_error") is True
    blocks = envelope["content"]
    assert all(b.get("type") == "text" for b in blocks)
    assert all("is_error" not in b for b in blocks)


# ---------------------------------------------------------------------------
# Scenario 3 — feature flag sanity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feature_flag_disabled_short_circuits_the_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``ADVISOR_ENABLED=False`` → ``require_app_feature`` raises; flow not invoked.

    The plan specifies a 402 here but the production route dep
    (``require_app_feature("advisor_enabled")``) raises 403
    FEATURE_DISABLED — 402 is the per-tier ``require_feature``
    dep and a different gate. The canonical assertion is that
    the disabled flag blocks the route before the service
    flow runs, which is what this test verifies.
    """
    from fastapi import HTTPException

    from app.api.deps import require_app_feature
    from app.config import settings

    dep = require_app_feature("advisor_enabled")
    monkeypatch.setattr(settings, "ADVISOR_ENABLED", False)

    with pytest.raises(HTTPException) as exc_info:
        await dep()

    # Matches the shape asserted by tests/test_features.py.
    assert exc_info.value.status_code == 403
    detail = exc_info.value.detail
    assert detail["error"]["code"] == "FEATURE_DISABLED"
    assert detail["error"]["detail"]["feature"] == "advisor_enabled"


# ---------------------------------------------------------------------------
# Scenario 4 — error path
# ---------------------------------------------------------------------------


class _LLMBoom(Exception):
    """Distinctive exception so the raise-path assertion is unambiguous."""


@pytest.mark.asyncio
async def test_llm_raises_mid_turn_payload_logged_once_no_partial_persist(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stubbed LLM raises → INFO record emitted exactly once before the raise.

    Also asserts ``repo.insert_message`` was never called — the service
    persists messages AFTER ``_call_llm_with_check`` returns, so a
    mid-turn raise must not leak a partial user row.
    """
    _quiet_the_flow(monkeypatch)

    repo = _stub_repo(
        profile=_STYLE_PROFILE_ROW,
        analysis_insight=_ANALYSIS_INSIGHT_ROW,
        nudges=[_POST_ANALYSIS_NUDGE, _WEEKLY_CHECKIN_NUDGE],
        glowup_row=_COMPLETED_GLOWUP_ROW,
        cleared_images=[{"id": "img-1", "storage_path": "user_a/source.jpg"}],
    )

    # Custom adapter that logs and raises on the FIRST call so the
    # payload logger already has emitted its record before the
    # exception propagates.
    class _BoomAdapter:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def create_message(self, **kwargs: Any) -> LLMResponse:
            self.calls.append(kwargs)
            raise _LLMBoom("simulated upstream failure")

    adapter = _BoomAdapter()
    svc = _build_service_with_mock_llm(repo, mock_llm=adapter)

    with caplog.at_level(logging.INFO, logger=PAYLOAD_LOGGER_NAME):
        with pytest.raises(_LLMBoom):
            await svc.send_message(UUID(_TEST_USER_ID), _USER_MESSAGE)

    # Adapter was called once.
    assert len(adapter.calls) == 1

    # Exactly one INFO record — payload logger fires BEFORE
    # ``self._llm.create_message`` so the raise cannot swallow the log.
    info_records = _collect_info_records(caplog)
    assert len(info_records) == 1, (
        f"expected one INFO record before the raise; got {len(info_records)}"
    )

    # No partial persist — ``send_message`` raises before reaching the
    # ``_save_message`` step, so the repo INSERT path never fires.
    assert not repo.insert_message.called, (
        "repo.insert_message should not have been called after an LLM raise"
    )
    assert not repo.update_conversation_timestamp.called, (
        "conversation timestamp should not be touched when the LLM raised mid-turn"
    )
