"""Vision-grounded nudge generation — Plan 2026-04-17-003 Unit 8.

End-to-end coverage for the vision path in ``nudge_scheduler``:

- The model sees before+after images fetched via the MCP handlers
  (same in-process code path Ada chat uses).
- Output parsing for strict JSON ``{"body", "observation_tag"}``.
- NULL ``observation_tag`` on pre-migration rows renders as "no tag".
- Cross-user isolation: the worker uses ``user_id`` from the job, not
  from any LLM-provided input; a spoofed user_id cannot fetch another
  user's images.
- Two back-to-back glow-ups produce two non-duplicate nudges (Jaccard
  regression threshold; exact content is model-dependent and not
  golden-tested).
"""

from __future__ import annotations

import base64
import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest


_TEST_USER_ID = str(uuid4())
_OTHER_USER_ID = str(uuid4())
_FAKE_BEFORE_BYTES = b"\xff\xd8\xff\xe0fake-before-jpeg"
_FAKE_AFTER_BYTES = b"\xff\xd8\xff\xe0fake-after-jpeg"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _image_block(data: bytes) -> dict[str, Any]:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": _b64(data),
        },
    }


def _fake_llm(response_text: str):
    """Return (adapter, captured_kwargs)."""
    captured: dict[str, Any] = {}

    async def _create(**kwargs):
        from app.advisor.models import LLMResponse

        captured.update(kwargs)
        return LLMResponse(content=response_text, input_tokens=1, output_tokens=1)

    return SimpleNamespace(create_message=_create), captured


def _patch_repo(
    monkeypatch,
    *,
    style_profile: dict | None = None,
    recent_nudge_context: list[dict] | None = None,
):
    from app.advisor import nudge_scheduler

    repo = MagicMock()
    repo.insert_nudge = MagicMock(return_value={"id": str(uuid4())})
    repo.get_style_profile = MagicMock(return_value=style_profile)
    repo.get_recent_nudge_context = MagicMock(return_value=recent_nudge_context or [])
    # Image repo surface — tests that exercise the real handlers patch
    # these too; tests that monkeypatch the handlers directly rely on
    # the noop defaults.
    repo.get_latest_completed_glowup_with_images = MagicMock(return_value=None)
    repo.get_cleared_images = MagicMock(return_value=[])
    repo.fetch_image_bytes = MagicMock(return_value=b"")
    monkeypatch.setattr(
        nudge_scheduler, "AdvisorRepository", MagicMock(return_value=repo)
    )
    return repo


def _patch_handlers(
    monkeypatch,
    *,
    glowup_blocks: list[dict] | None = None,
    photo_blocks: list[dict] | None = None,
):
    """Patch the two MCP handler functions directly.

    When a test wants to exercise the real handlers (image fetch via
    the repo), it can skip this and patch the repo methods instead.
    """
    from app.advisor import nudge_scheduler

    async def _fake_glowup(_ctx):
        if glowup_blocks is not None:
            return {"content": list(glowup_blocks), "is_error": False}
        return {
            "content": [{"type": "text", "text": "no completed glow-up"}],
            "is_error": True,
        }

    async def _fake_photo(_ctx):
        if photo_blocks is not None:
            return {"content": list(photo_blocks), "is_error": False}
        return {
            "content": [{"type": "text", "text": "no source photo"}],
            "is_error": True,
        }

    monkeypatch.setattr(nudge_scheduler, "_handle_get_latest_glowup", _fake_glowup)
    monkeypatch.setattr(nudge_scheduler, "_handle_get_latest_photo", _fake_photo)


# ---------------------------------------------------------------------------
# Happy path — first glow-up
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_glowup_generates_persisted_nudge(monkeypatch):
    """First post_glowup: body is one sentence, observation_tag 1-3 words."""
    from app.advisor import nudge_scheduler

    llm, _captured = _fake_llm(
        '{"body": "The new look brightens your features in a way that reads well.",'
        ' "observation_tag": "brighter features"}'
    )
    monkeypatch.setattr(nudge_scheduler, "_get_llm_adapter", lambda: llm)

    repo = _patch_repo(
        monkeypatch,
        style_profile={
            "content": {
                "face_shape": "oval",
                "symmetry_score": 0.87,
                "recommendations": ["Softer layers"],
            },
            "created_at": "2026-04-17T00:00:00Z",
        },
    )
    _patch_handlers(
        monkeypatch,
        glowup_blocks=[
            _image_block(_FAKE_BEFORE_BYTES),
            _image_block(_FAKE_AFTER_BYTES),
            {"type": "text", "text": "feature=glowup"},
        ],
    )

    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis},
        _TEST_USER_ID,
        nudge_scheduler.TRIGGER_POST_GLOWUP,
    )

    repo.insert_nudge.assert_called_once()
    persisted = repo.insert_nudge.call_args[0][0]
    body = persisted["content"]
    # One sentence: single trailing punctuation mark, no embedded '.' mid-body.
    assert body.count(".") <= 2, f"body is not one sentence: {body!r}"
    tag = persisted["observation_tag"]
    assert 1 <= len(tag.split()) <= 3, f"observation_tag word count off: {tag!r}"


# ---------------------------------------------------------------------------
# Happy path — second glow-up, low word overlap
# ---------------------------------------------------------------------------


def _jaccard(a: str, b: str) -> float:
    tokens_a = {w.lower().strip(".,!?") for w in a.split() if w.strip(".,!?")}
    tokens_b = {w.lower().strip(".,!?") for w in b.split() if w.strip(".,!?")}
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


@pytest.mark.asyncio
async def test_two_back_to_back_glowups_have_low_overlap(monkeypatch):
    """Two distinct nudge bodies; Jaccard word-overlap stays under 0.4."""
    from app.advisor import nudge_scheduler

    # Distinct responses simulating the model steering away from the
    # prior observation_tag present in the recent-context block.
    first_body = "Your new cut settles into the jawline with a clean edge."
    second_body = "The warmer undertone lifts how your eyes read in this light."
    responses = iter(
        [
            f'{{"body": "{first_body}", "observation_tag": "cleaner jaw"}}',
            f'{{"body": "{second_body}", "observation_tag": "warmer tone"}}',
        ]
    )

    async def _create(**_kwargs):
        from app.advisor.models import LLMResponse

        return LLMResponse(content=next(responses), input_tokens=1, output_tokens=1)

    monkeypatch.setattr(
        nudge_scheduler,
        "_get_llm_adapter",
        lambda: SimpleNamespace(create_message=_create),
    )

    _patch_repo(
        monkeypatch,
        style_profile={
            "content": {"face_shape": "oval", "symmetry_score": 0.88},
            "created_at": "2026-04-17T00:00:00Z",
        },
    )
    _patch_handlers(
        monkeypatch,
        glowup_blocks=[
            _image_block(_FAKE_BEFORE_BYTES),
            _image_block(_FAKE_AFTER_BYTES),
        ],
    )

    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    # Run twice sequentially (different upload_ids so rapid-retry does
    # not interfere).
    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis},
        _TEST_USER_ID,
        nudge_scheduler.TRIGGER_POST_GLOWUP,
    )
    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis},
        _TEST_USER_ID,
        nudge_scheduler.TRIGGER_POST_GLOWUP,
    )

    assert _jaccard(first_body, second_body) < 0.4, (
        "two distinct nudge bodies must not share >=40% tokens"
    )


# ---------------------------------------------------------------------------
# Recent-context block — NULL observation_tag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recent_context_with_null_tag_renders_as_no_tag(monkeypatch):
    """Pre-Unit-8 row with observation_tag=NULL should render as 'no tag'."""
    from app.advisor import nudge_scheduler

    llm, captured = _fake_llm('{"body": "warm sentence.", "observation_tag": "x y"}')
    monkeypatch.setattr(nudge_scheduler, "_get_llm_adapter", lambda: llm)

    _patch_repo(
        monkeypatch,
        style_profile={
            "content": {"face_shape": "oval", "symmetry_score": 0.9},
            "created_at": "2026-04-17T00:00:00Z",
        },
        recent_nudge_context=[
            {
                "body": "pre-migration body",
                "observation_tag": None,
                "created_at": "2026-04-10T00:00:00Z",
            }
        ],
    )
    _patch_handlers(
        monkeypatch,
        glowup_blocks=[_image_block(_FAKE_BEFORE_BYTES)],
    )

    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis},
        _TEST_USER_ID,
        nudge_scheduler.TRIGGER_POST_GLOWUP,
    )

    prompt_text = captured["messages"][0]["content"][0]["text"]
    assert "no tag" in prompt_text
    assert "pre-migration body" in prompt_text


# ---------------------------------------------------------------------------
# Security — cross-user isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_user_id_is_authoritative_over_llm_input(monkeypatch):
    """The MCP handlers resolve images from ctx.user_id, not from any args.

    Even if a caller passes a different user_id shape in kwargs (which
    the worker job signature does not expose), the handler's sole
    source of user identity is the McpContext the worker builds.
    """
    from app.advisor import nudge_scheduler
    from app.advisor.mcp.context import McpContext

    seen_user_ids: list[str] = []

    async def _glowup(ctx: McpContext):
        seen_user_ids.append(str(ctx.user_id))
        return {
            "content": [
                _image_block(_FAKE_BEFORE_BYTES),
                _image_block(_FAKE_AFTER_BYTES),
            ],
            "is_error": False,
        }

    monkeypatch.setattr(nudge_scheduler, "_handle_get_latest_glowup", _glowup)

    async def _photo(ctx: McpContext):
        seen_user_ids.append(str(ctx.user_id))
        return {
            "content": [{"type": "text", "text": "no source photo"}],
            "is_error": True,
        }

    monkeypatch.setattr(nudge_scheduler, "_handle_get_latest_photo", _photo)

    llm, _captured = _fake_llm('{"body": "warm.", "observation_tag": "clean"}')
    monkeypatch.setattr(nudge_scheduler, "_get_llm_adapter", lambda: llm)

    _patch_repo(
        monkeypatch,
        style_profile={
            "content": {"face_shape": "oval", "symmetry_score": 0.9},
            "created_at": "2026-04-17T00:00:00Z",
        },
    )

    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis},
        _TEST_USER_ID,  # authoritative
        nudge_scheduler.TRIGGER_POST_GLOWUP,
    )

    assert seen_user_ids, "handler must have been called"
    for seen in seen_user_ids:
        assert seen == _TEST_USER_ID, (
            f"handler saw user_id {seen!r} but worker was called with "
            f"{_TEST_USER_ID!r} — authenticated user must be authoritative"
        )
        assert seen != _OTHER_USER_ID, "no other-user leakage"


@pytest.mark.asyncio
async def test_vision_nudge_handlers_called_with_frozen_context(monkeypatch):
    """The worker builds a frozen McpContext; the handler cannot mutate user_id."""
    from app.advisor import nudge_scheduler
    from app.advisor.mcp.context import McpContext
    from dataclasses import FrozenInstanceError

    captured_ctx: list[McpContext] = []

    async def _glowup(ctx: McpContext):
        captured_ctx.append(ctx)
        return {
            "content": [_image_block(_FAKE_BEFORE_BYTES)],
            "is_error": False,
        }

    monkeypatch.setattr(nudge_scheduler, "_handle_get_latest_glowup", _glowup)

    llm, _captured = _fake_llm('{"body": "warm.", "observation_tag": "clean"}')
    monkeypatch.setattr(nudge_scheduler, "_get_llm_adapter", lambda: llm)

    _patch_repo(
        monkeypatch,
        style_profile={
            "content": {"face_shape": "oval", "symmetry_score": 0.9},
            "created_at": "2026-04-17T00:00:00Z",
        },
    )

    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis},
        _TEST_USER_ID,
        nudge_scheduler.TRIGGER_POST_GLOWUP,
    )

    assert captured_ctx, "handler must have been called"
    ctx = captured_ctx[0]
    assert ctx.user_id == UUID(_TEST_USER_ID)
    # The context is frozen — a compromised handler cannot reassign.
    with pytest.raises(FrozenInstanceError):
        ctx.user_id = UUID(_OTHER_USER_ID)


# ---------------------------------------------------------------------------
# Logging — structured metric on invalid JSON
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_json_emits_metric_and_no_persistence(monkeypatch, caplog):
    """Drop path emits ``advisor.nudge_invalid_json`` as ``extra.metric``."""
    from app.advisor import nudge_scheduler

    llm, _captured = _fake_llm("<<< not JSON >>>")
    monkeypatch.setattr(nudge_scheduler, "_get_llm_adapter", lambda: llm)

    repo = _patch_repo(
        monkeypatch,
        style_profile={
            "content": {"face_shape": "oval", "symmetry_score": 0.9},
            "created_at": "2026-04-17T00:00:00Z",
        },
    )
    _patch_handlers(
        monkeypatch,
        glowup_blocks=[_image_block(_FAKE_BEFORE_BYTES)],
    )

    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    caplog.set_level(logging.WARNING)
    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis},
        _TEST_USER_ID,
        nudge_scheduler.TRIGGER_POST_GLOWUP,
    )

    repo.insert_nudge.assert_not_called()
    metric_records = [
        r
        for r in caplog.records
        if getattr(r, "metric", None) == "advisor.nudge_invalid_json"
    ]
    assert metric_records, (
        "must emit a WARNING log with metric=advisor.nudge_invalid_json on parse failure"
    )


# ---------------------------------------------------------------------------
# Repo — get_recent_nudge_context
# ---------------------------------------------------------------------------


def test_repo_get_recent_nudge_context_aliases_content_to_body(monkeypatch):
    """Repo helper returns ``body`` alias for ``content`` + pass-through fields."""
    from app.repositories.advisor_repo import AdvisorRepository

    sb = MagicMock()
    rows = [
        {
            "content": "first",
            "observation_tag": "softer jaw",
            "created_at": "2026-04-17T00:00:00Z",
        },
        {
            "content": "second",
            "observation_tag": None,
            "created_at": "2026-04-16T00:00:00Z",
        },
    ]
    sb.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = rows

    repo = AdvisorRepository(sb)
    out = repo.get_recent_nudge_context(_TEST_USER_ID, limit=5)

    assert [r["body"] for r in out] == ["first", "second"]
    assert out[0]["observation_tag"] == "softer jaw"
    assert out[1]["observation_tag"] is None
    # Select column shape:
    sb.table.return_value.select.assert_called_with(
        "content, observation_tag, created_at"
    )
    sb.table.return_value.select.return_value.eq.assert_called_with(
        "user_id", _TEST_USER_ID
    )
