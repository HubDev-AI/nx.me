"""Post-glow-up nudge trigger — Plan 2026-04-17-003 Unit 8.

Covers:

- The generation worker's success branch enqueues ``generate_nudge``
  with ``TRIGGER_POST_GLOWUP`` + ``job_id`` after ``_finalize_job``
  transitions the job to ``completed``.
- Rapid-retry dedup via Redis SETNX: a second ``post_glowup`` for the
  same user+upload_id within ``ADVISOR_POST_GLOWUP_RAPID_RETRY_MINUTES``
  is skipped with ``advisor.nudge_rapid_retry_dedup`` metric.
- Skip with structured log when the user has no ``style_profile``.
- Enqueue is fire-and-forget: Redis / ARQ errors never block the glow
  up completion path.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


_TEST_USER_ID = str(uuid4())
_TEST_JOB_ID = str(uuid4())
_TEST_SOURCE_ID = str(uuid4())
_TEST_UPLOAD_ID = str(uuid4())


def _image_block(tag: str) -> dict[str, Any]:
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": tag},
    }


def _fake_llm(response_text: str):
    async def _create(**_kwargs):
        from app.advisor.models import LLMResponse

        return LLMResponse(content=response_text, input_tokens=1, output_tokens=1)

    return SimpleNamespace(create_message=_create)


def _patch_entitlement(monkeypatch):
    ent = MagicMock()
    ent.check = AsyncMock(return_value=SimpleNamespace(allowed=True, error_code=None))
    monkeypatch.setattr(
        "app.entitlement.service.EntitlementService", MagicMock(return_value=ent)
    )


def _patch_repo(
    monkeypatch,
    *,
    style_profile: dict | None = None,
):
    from app.advisor import nudge_scheduler

    repo = MagicMock()
    repo.insert_nudge = MagicMock()
    repo.get_style_profile = MagicMock(return_value=style_profile)
    repo.get_recent_nudge_context = MagicMock(return_value=[])
    monkeypatch.setattr(
        nudge_scheduler, "AdvisorRepository", MagicMock(return_value=repo)
    )
    return repo


def _patch_handlers(monkeypatch, *, glowup_blocks: list[dict] | None = None):
    """Patch handlers to return envelope-shaped dicts (Plan 2026-04-17 review fix).

    ``{"content": [...], "is_error": bool}`` — ``is_error`` rides on the
    envelope per Anthropic's spec, never on an inner content block.
    """
    from app.advisor import nudge_scheduler

    async def _glowup(_ctx):
        if glowup_blocks is not None:
            return {"content": list(glowup_blocks), "is_error": False}
        return {
            "content": [{"type": "text", "text": "no completed glow-up"}],
            "is_error": True,
        }

    async def _photo(_ctx):
        return {
            "content": [{"type": "text", "text": "no source photo"}],
            "is_error": True,
        }

    monkeypatch.setattr(nudge_scheduler, "_handle_get_latest_glowup", _glowup)
    monkeypatch.setattr(nudge_scheduler, "_handle_get_latest_photo", _photo)


def _patch_upload_id_resolver(monkeypatch, upload_id: str | None):
    """Patch ``_resolve_upload_id_for_job`` so rapid-retry dedup is deterministic."""
    from app.advisor import nudge_scheduler

    def _fake_resolve(_supabase, _job_id):
        return upload_id

    monkeypatch.setattr(nudge_scheduler, "_resolve_upload_id_for_job", _fake_resolve)


# ---------------------------------------------------------------------------
# Worker success branch enqueues post_glowup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_enqueues_post_glowup_on_finalize(monkeypatch):
    """``_enqueue_post_glowup_nudge`` enqueues ``generate_nudge`` fire-and-forget.

    Covers the worker.py integration point — Unit 8 places the enqueue
    after ``_finalize_job`` on the success branch.
    """
    from app.advisor.nudge_policy import TRIGGER_POST_GLOWUP
    from app.generation import worker

    arq_pool = MagicMock()
    arq_pool.enqueue_job = AsyncMock()

    await worker._enqueue_post_glowup_nudge(
        ctx={"arq_pool": arq_pool},
        job_id=_TEST_JOB_ID,
        user_id=_TEST_USER_ID,
    )

    arq_pool.enqueue_job.assert_awaited_once_with(
        "generate_nudge",
        _TEST_USER_ID,
        TRIGGER_POST_GLOWUP,
        None,
        _TEST_JOB_ID,
    )


@pytest.mark.asyncio
async def test_worker_enqueue_swallows_redis_errors(monkeypatch, caplog):
    """A failing enqueue must not raise — mirrors ``_fail_job`` fire-and-forget."""
    from app.generation import worker

    arq_pool = MagicMock()
    arq_pool.enqueue_job = AsyncMock(side_effect=RuntimeError("redis down"))

    caplog.set_level(logging.WARNING)
    # Must not raise
    await worker._enqueue_post_glowup_nudge(
        ctx={"arq_pool": arq_pool},
        job_id=_TEST_JOB_ID,
        user_id=_TEST_USER_ID,
    )

    assert any(
        "Failed to enqueue post_glowup nudge" in r.message for r in caplog.records
    )


@pytest.mark.asyncio
async def test_worker_enqueue_falls_back_to_inline_without_arq_pool(
    monkeypatch, caplog
):
    """No ``arq_pool`` in ctx → inline ``generate_nudge`` call, WARN logged.

    Defense in depth: ``worker_settings.startup`` populates ctx["arq_pool"]
    in production, but if that ever regresses the user must still receive
    the nudge rather than silently lose it. This test pins the fallback
    contract introduced alongside the startup fix.
    """
    from app.advisor.nudge_policy import TRIGGER_POST_GLOWUP
    from app.generation import worker

    generate_nudge_mock = AsyncMock()
    monkeypatch.setattr(
        "app.advisor.nudge_scheduler.generate_nudge", generate_nudge_mock
    )

    caplog.set_level(logging.WARNING)
    await worker._enqueue_post_glowup_nudge(
        ctx={},
        job_id=_TEST_JOB_ID,
        user_id=_TEST_USER_ID,
    )

    generate_nudge_mock.assert_awaited_once_with(
        {},
        _TEST_USER_ID,
        TRIGGER_POST_GLOWUP,
        None,
        _TEST_JOB_ID,
    )
    assert any(
        "No arq_pool in ctx" in r.message and r.levelname == "WARNING"
        for r in caplog.records
    )


@pytest.mark.asyncio
async def test_worker_enqueue_inline_fallback_swallows_errors(monkeypatch, caplog):
    """Inline fallback must also be fire-and-forget — a failing
    ``generate_nudge`` must not bubble up and fail the glow-up."""
    from app.generation import worker

    monkeypatch.setattr(
        "app.advisor.nudge_scheduler.generate_nudge",
        AsyncMock(side_effect=RuntimeError("advisor down")),
    )

    caplog.set_level(logging.WARNING)
    # Must not raise
    await worker._enqueue_post_glowup_nudge(
        ctx={},
        job_id=_TEST_JOB_ID,
        user_id=_TEST_USER_ID,
    )

    assert any("Inline generate_nudge failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Rapid-retry dedup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rapid_retry_dedup_skips_second_run_on_same_upload(monkeypatch, caplog):
    """Two post_glowup nudges within the rapid-retry window on the same
    upload: the second is skipped; the first proceeds."""
    from app.advisor import nudge_scheduler

    monkeypatch.setattr(
        nudge_scheduler,
        "_get_llm_adapter",
        lambda: _fake_llm('{"body": "warm.", "observation_tag": "clean"}'),
    )
    _patch_entitlement(monkeypatch)
    repo = _patch_repo(
        monkeypatch,
        style_profile={
            "content": {"face_shape": "oval", "symmetry_score": 0.9},
            "created_at": "2026-04-17T00:00:00Z",
        },
    )
    _patch_handlers(
        monkeypatch,
        glowup_blocks=[_image_block("before"), _image_block("after")],
    )
    _patch_upload_id_resolver(monkeypatch, _TEST_UPLOAD_ID)

    # Simulate a real Redis SETNX: first call accepted, second rejected.
    redis = AsyncMock()
    # .set(key, value, ex=..., nx=True) → True on first, None on second
    redis.set = AsyncMock(side_effect=[True, None])

    caplog.set_level(logging.INFO)

    # First run → proceeds.
    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis},
        _TEST_USER_ID,
        nudge_scheduler.TRIGGER_POST_GLOWUP,
        None,
        _TEST_JOB_ID,
    )
    # Second run → skipped (SETNX rejected).
    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis},
        _TEST_USER_ID,
        nudge_scheduler.TRIGGER_POST_GLOWUP,
        None,
        _TEST_JOB_ID,
    )

    # Exactly one persistence — the first run.
    assert repo.insert_nudge.call_count == 1
    # Dedup metric was emitted for the second run.
    metric_records = [
        r
        for r in caplog.records
        if getattr(r, "metric", None) == "advisor.nudge_rapid_retry_dedup"
    ]
    assert metric_records, "rapid_retry_dedup metric must be emitted"


@pytest.mark.asyncio
async def test_rapid_retry_dedup_disabled_when_window_is_zero(monkeypatch):
    """``ADVISOR_POST_GLOWUP_RAPID_RETRY_MINUTES=0`` → no SETNX call, both proceed."""
    from app.advisor import nudge_scheduler
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_POST_GLOWUP_RAPID_RETRY_MINUTES", 0)
    monkeypatch.setattr(
        nudge_scheduler,
        "_get_llm_adapter",
        lambda: _fake_llm('{"body": "warm.", "observation_tag": "clean"}'),
    )
    _patch_entitlement(monkeypatch)
    repo = _patch_repo(
        monkeypatch,
        style_profile={
            "content": {"face_shape": "oval", "symmetry_score": 0.9},
            "created_at": "2026-04-17T00:00:00Z",
        },
    )
    _patch_handlers(
        monkeypatch,
        glowup_blocks=[_image_block("before"), _image_block("after")],
    )
    _patch_upload_id_resolver(monkeypatch, _TEST_UPLOAD_ID)

    redis = AsyncMock()
    redis.set = AsyncMock()

    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis},
        _TEST_USER_ID,
        nudge_scheduler.TRIGGER_POST_GLOWUP,
        None,
        _TEST_JOB_ID,
    )
    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis},
        _TEST_USER_ID,
        nudge_scheduler.TRIGGER_POST_GLOWUP,
        None,
        _TEST_JOB_ID,
    )

    redis.set.assert_not_called()  # guard short-circuits before Redis
    assert repo.insert_nudge.call_count == 2


@pytest.mark.asyncio
async def test_rapid_retry_dedup_different_upload_does_not_skip(monkeypatch):
    """Different upload_ids → both runs proceed (two distinct glow-ups).

    Simulates two back-to-back glow-ups on the same user but with two
    different source photos.
    """
    from app.advisor import nudge_scheduler

    monkeypatch.setattr(
        nudge_scheduler,
        "_get_llm_adapter",
        lambda: _fake_llm('{"body": "warm.", "observation_tag": "clean"}'),
    )
    _patch_entitlement(monkeypatch)
    repo = _patch_repo(
        monkeypatch,
        style_profile={
            "content": {"face_shape": "oval", "symmetry_score": 0.9},
            "created_at": "2026-04-17T00:00:00Z",
        },
    )
    _patch_handlers(
        monkeypatch,
        glowup_blocks=[_image_block("before"), _image_block("after")],
    )

    upload_ids = iter([_TEST_UPLOAD_ID, str(uuid4())])

    def _fake_resolve(_supabase, _job_id):
        return next(upload_ids)

    monkeypatch.setattr(nudge_scheduler, "_resolve_upload_id_for_job", _fake_resolve)

    redis = AsyncMock()
    # Both SETNX calls accepted because keys differ.
    redis.set = AsyncMock(return_value=True)

    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis},
        _TEST_USER_ID,
        nudge_scheduler.TRIGGER_POST_GLOWUP,
        None,
        _TEST_JOB_ID,
    )
    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis},
        _TEST_USER_ID,
        nudge_scheduler.TRIGGER_POST_GLOWUP,
        None,
        str(uuid4()),
    )

    assert repo.insert_nudge.call_count == 2, (
        "distinct upload_ids must not dedup each other"
    )


# ---------------------------------------------------------------------------
# Skip when no style_profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_glowup_skips_when_no_style_profile(monkeypatch, caplog):
    """No profile → skip with structured log, no image fetch, no LLM call."""
    from app.advisor import nudge_scheduler

    llm_calls: list[dict] = []

    async def _create(**kwargs):
        from app.advisor.models import LLMResponse

        llm_calls.append(kwargs)
        return LLMResponse(
            content='{"body":"x","observation_tag":"y"}',
            input_tokens=1,
            output_tokens=1,
        )

    monkeypatch.setattr(
        nudge_scheduler,
        "_get_llm_adapter",
        lambda: SimpleNamespace(create_message=_create),
    )
    _patch_entitlement(monkeypatch)
    repo = _patch_repo(monkeypatch, style_profile=None)
    _patch_handlers(monkeypatch)

    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    caplog.set_level(logging.INFO)
    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis},
        _TEST_USER_ID,
        nudge_scheduler.TRIGGER_POST_GLOWUP,
        None,
        _TEST_JOB_ID,
    )

    assert not llm_calls, "LLM must not be called without a style_profile"
    repo.insert_nudge.assert_not_called()
    no_profile_records = [
        r
        for r in caplog.records
        if getattr(r, "metric", None) == "advisor.nudge_no_profile"
    ]
    assert no_profile_records, "must emit metric=advisor.nudge_no_profile"


# ---------------------------------------------------------------------------
# Zero-image fallback — handler returned no images at all
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_glowup_skips_when_handler_returns_no_images(monkeypatch):
    """Both handlers return is_error text → skip rather than feed an empty prompt."""
    from app.advisor import nudge_scheduler

    llm_calls: list[dict] = []

    async def _create(**kwargs):
        from app.advisor.models import LLMResponse

        llm_calls.append(kwargs)
        return LLMResponse(content="unused", input_tokens=1, output_tokens=1)

    monkeypatch.setattr(
        nudge_scheduler,
        "_get_llm_adapter",
        lambda: SimpleNamespace(create_message=_create),
    )
    _patch_entitlement(monkeypatch)
    repo = _patch_repo(
        monkeypatch,
        style_profile={
            "content": {"face_shape": "oval", "symmetry_score": 0.9},
            "created_at": "2026-04-17T00:00:00Z",
        },
    )
    # No image blocks in either handler result.
    _patch_handlers(
        monkeypatch,
        glowup_blocks=[{"type": "text", "text": "no glow-up", "is_error": True}],
    )
    _patch_upload_id_resolver(monkeypatch, None)

    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis},
        _TEST_USER_ID,
        nudge_scheduler.TRIGGER_POST_GLOWUP,
        None,
        _TEST_JOB_ID,
    )

    assert not llm_calls, "LLM must not be called without any image blocks"
    repo.insert_nudge.assert_not_called()
