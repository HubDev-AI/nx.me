"""Post-glow-up nudge trigger — Plan 2026-04-20-001 Unit 3.

Covers:

- The generation worker's success branch enqueues ``generate_nudge``
  with ``job_id`` after ``_finalize_job`` transitions the job to
  ``completed``.
- Rapid-retry dedup via Redis SETNX.
- New three-field contract {body, next_step.{label, seed}}.
- Parse drop scenarios with kind tags.
- Body-hash dedup (30-day window).
- Skip with structured log when the user has no ``style_profile``.
- Enqueue is fire-and-forget.
"""

from __future__ import annotations

import asyncio
import hashlib
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


def _patch_repo(
    monkeypatch,
    *,
    style_profile: dict | None = None,
    recent_nudges: list | None = None,
    find_duplicate_body: bool = False,
):
    from app.advisor import nudge_scheduler

    repo = MagicMock()
    repo.insert_nudge = MagicMock()
    repo.get_style_profile = MagicMock(return_value=style_profile)
    repo.get_recent_nudge_context = MagicMock(return_value=recent_nudges or [])
    repo.find_duplicate_body = MagicMock(return_value=find_duplicate_body)
    monkeypatch.setattr(
        nudge_scheduler, "AdvisorRepository", MagicMock(return_value=repo)
    )
    return repo


def _patch_handlers(monkeypatch, *, glowup_blocks: list[dict] | None = None):
    """Patch handlers to return envelope-shaped dicts."""
    from app.advisor import nudge_scheduler

    async def _glowup(_ctx):
        if glowup_blocks is not None:
            return {"content": list(glowup_blocks), "is_error": False}
        return {
            "content": [{"type": "text", "text": "no completed glow-up"}],
            "is_error": True,
        }

    monkeypatch.setattr(nudge_scheduler, "_handle_get_latest_glowup", _glowup)


def _patch_upload_id_resolver(monkeypatch, upload_id: str | None):
    from app.advisor import nudge_scheduler

    def _fake_resolve(_supabase, _job_id):
        return upload_id

    monkeypatch.setattr(nudge_scheduler, "_resolve_upload_id_for_job", _fake_resolve)


_GOOD_RESPONSE = (
    '{"body": "Your brow arch looks beautifully defined.", '
    '"next_step": {"label": "Ask Ada", "seed": "How can I keep my brows looking this defined?"}}'
)

_STYLE_PROFILE = {
    "content": {"face_shape": "oval", "symmetry_score": 0.9},
    "created_at": "2026-04-17T00:00:00Z",
}


# ---------------------------------------------------------------------------
# Worker success branch enqueues post_glowup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_enqueues_post_glowup_on_finalize(monkeypatch):
    """``_enqueue_post_glowup_nudge`` enqueues ``generate_nudge`` with new 2-arg shape."""
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
        _TEST_JOB_ID,
    )


@pytest.mark.asyncio
async def test_worker_enqueue_swallows_redis_errors(monkeypatch, caplog):
    """A failing enqueue must not raise — mirrors ``_fail_job`` fire-and-forget."""
    from app.generation import worker

    arq_pool = MagicMock()
    arq_pool.enqueue_job = AsyncMock(side_effect=RuntimeError("redis down"))

    caplog.set_level(logging.WARNING)
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
    """No ``arq_pool`` in ctx → inline ``generate_nudge`` call, WARN logged."""
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
        _TEST_JOB_ID,
    )
    assert any(
        "No arq_pool in ctx" in r.message and r.levelname == "WARNING"
        for r in caplog.records
    )


@pytest.mark.asyncio
async def test_worker_enqueue_inline_fallback_swallows_errors(monkeypatch, caplog):
    """Inline fallback must also be fire-and-forget."""
    from app.generation import worker

    monkeypatch.setattr(
        "app.advisor.nudge_scheduler.generate_nudge",
        AsyncMock(side_effect=RuntimeError("advisor down")),
    )

    caplog.set_level(logging.WARNING)
    await worker._enqueue_post_glowup_nudge(
        ctx={},
        job_id=_TEST_JOB_ID,
        user_id=_TEST_USER_ID,
    )

    assert any("Inline generate_nudge failed" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_worker_enqueue_inline_fallback_bounds_slow_nudge(monkeypatch, caplog):
    """Inline fallback must be bounded by ``asyncio.wait_for``."""
    from app.generation import worker

    async def _stall(*_args, **_kwargs):
        await asyncio.sleep(10)

    monkeypatch.setattr("app.advisor.nudge_scheduler.generate_nudge", _stall)
    monkeypatch.setattr(worker, "_NUDGE_INLINE_TIMEOUT_SECONDS", 0.05)

    caplog.set_level(logging.WARNING)
    await worker._enqueue_post_glowup_nudge(
        ctx={},
        job_id=_TEST_JOB_ID,
        user_id=_TEST_USER_ID,
    )

    assert any("Inline generate_nudge failed" in r.message for r in caplog.records), (
        "timed-out nudge must hit the swallow-and-log branch"
    )


# ---------------------------------------------------------------------------
# Happy path — three-field contract persisted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_persists_three_fields(monkeypatch):
    """Happy path: well-formed JSON → row with body, next_step_label,
    next_step_seed, body_hash persisted."""
    from app.advisor import nudge_scheduler

    monkeypatch.setattr(
        nudge_scheduler, "_get_llm_adapter", lambda: _fake_llm(_GOOD_RESPONSE)
    )
    repo = _patch_repo(monkeypatch, style_profile=_STYLE_PROFILE)
    _patch_handlers(
        monkeypatch,
        glowup_blocks=[_image_block("before"), _image_block("after")],
    )
    _patch_upload_id_resolver(monkeypatch, None)

    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis},
        _TEST_USER_ID,
        _TEST_JOB_ID,
    )

    repo.insert_nudge.assert_called_once()
    call_data = repo.insert_nudge.call_args[0][0]
    assert call_data["body"] == "Your brow arch looks beautifully defined."
    assert call_data["next_step_label"] == "Ask Ada"
    assert (
        call_data["next_step_seed"] == "How can I keep my brows looking this defined?"
    )
    expected_hash = hashlib.sha256(
        "your brow arch looks beautifully defined.".encode()
    ).hexdigest()
    assert call_data["body_hash"] == expected_hash
    assert call_data["user_id"] == _TEST_USER_ID


# ---------------------------------------------------------------------------
# Parse drop scenarios
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parse_drop_body_too_long(monkeypatch, caplog):
    """body = 161 chars → parse drops with kind=length."""
    from app.advisor import nudge_scheduler

    long_body = "x" * 161
    response = (
        f'{{"body": "{long_body}", '
        '"next_step": {"label": "Ask Ada", "seed": "What should I try next?"}}'
    )
    monkeypatch.setattr(
        nudge_scheduler, "_get_llm_adapter", lambda: _fake_llm(response)
    )
    repo = _patch_repo(monkeypatch, style_profile=_STYLE_PROFILE)
    _patch_handlers(
        monkeypatch, glowup_blocks=[_image_block("before"), _image_block("after")]
    )
    _patch_upload_id_resolver(monkeypatch, None)
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    caplog.set_level(logging.WARNING)
    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis}, _TEST_USER_ID, _TEST_JOB_ID
    )

    repo.insert_nudge.assert_not_called()
    drop_records = [
        r
        for r in caplog.records
        if getattr(r, "metric", None) == "advisor.nudge_parse_drop"
    ]
    assert drop_records, "must emit nudge_parse_drop metric"
    assert drop_records[0].kind == "length"


@pytest.mark.asyncio
async def test_parse_drop_seed_missing_question_mark(monkeypatch, caplog):
    """seed missing '?' → drops with kind=seed_not_question."""
    from app.advisor import nudge_scheduler

    response = (
        '{"body": "Your look is stunning.", '
        '"next_step": {"label": "Ask Ada", "seed": "Tell me more about this look"}}'
    )
    monkeypatch.setattr(
        nudge_scheduler, "_get_llm_adapter", lambda: _fake_llm(response)
    )
    repo = _patch_repo(monkeypatch, style_profile=_STYLE_PROFILE)
    _patch_handlers(
        monkeypatch, glowup_blocks=[_image_block("before"), _image_block("after")]
    )
    _patch_upload_id_resolver(monkeypatch, None)
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    caplog.set_level(logging.WARNING)
    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis}, _TEST_USER_ID, _TEST_JOB_ID
    )

    repo.insert_nudge.assert_not_called()
    drop_records = [
        r
        for r in caplog.records
        if getattr(r, "metric", None) == "advisor.nudge_parse_drop"
    ]
    assert drop_records
    assert drop_records[0].kind == "seed_not_question"


@pytest.mark.asyncio
async def test_parse_drop_missing_next_step_key(monkeypatch, caplog):
    """missing next_step key → drops with kind=shape."""
    from app.advisor import nudge_scheduler

    response = '{"body": "Great brows today."}'
    monkeypatch.setattr(
        nudge_scheduler, "_get_llm_adapter", lambda: _fake_llm(response)
    )
    repo = _patch_repo(monkeypatch, style_profile=_STYLE_PROFILE)
    _patch_handlers(
        monkeypatch, glowup_blocks=[_image_block("before"), _image_block("after")]
    )
    _patch_upload_id_resolver(monkeypatch, None)
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    caplog.set_level(logging.WARNING)
    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis}, _TEST_USER_ID, _TEST_JOB_ID
    )

    repo.insert_nudge.assert_not_called()
    drop_records = [
        r
        for r in caplog.records
        if getattr(r, "metric", None) == "advisor.nudge_parse_drop"
    ]
    assert drop_records
    assert drop_records[0].kind == "shape"


@pytest.mark.asyncio
async def test_parse_drop_malformed_json(monkeypatch, caplog):
    """non-JSON string → drops with kind=json."""
    from app.advisor import nudge_scheduler

    monkeypatch.setattr(
        nudge_scheduler,
        "_get_llm_adapter",
        lambda: _fake_llm("this is not json at all"),
    )
    repo = _patch_repo(monkeypatch, style_profile=_STYLE_PROFILE)
    _patch_handlers(
        monkeypatch, glowup_blocks=[_image_block("before"), _image_block("after")]
    )
    _patch_upload_id_resolver(monkeypatch, None)
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    caplog.set_level(logging.WARNING)
    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis}, _TEST_USER_ID, _TEST_JOB_ID
    )

    repo.insert_nudge.assert_not_called()
    drop_records = [
        r
        for r in caplog.records
        if getattr(r, "metric", None) == "advisor.nudge_parse_drop"
    ]
    assert drop_records
    assert drop_records[0].kind == "json"


# ---------------------------------------------------------------------------
# Edge: first-ever nudge (empty recent_nudges)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_ever_nudge_no_recent_nudges(monkeypatch):
    """recent_nudges empty → prompt still builds, nudge persisted."""
    from app.advisor import nudge_scheduler

    monkeypatch.setattr(
        nudge_scheduler, "_get_llm_adapter", lambda: _fake_llm(_GOOD_RESPONSE)
    )
    repo = _patch_repo(monkeypatch, style_profile=_STYLE_PROFILE, recent_nudges=[])
    _patch_handlers(
        monkeypatch, glowup_blocks=[_image_block("before"), _image_block("after")]
    )
    _patch_upload_id_resolver(monkeypatch, None)
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis}, _TEST_USER_ID, _TEST_JOB_ID
    )

    repo.insert_nudge.assert_called_once()


# ---------------------------------------------------------------------------
# Error: vision model raises
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vision_model_raises_returns_silently(monkeypatch, caplog):
    """LLM raises → function returns silently, no insert."""
    from app.advisor import nudge_scheduler

    async def _raise(**_kwargs):
        raise RuntimeError("LLM timeout")

    monkeypatch.setattr(
        nudge_scheduler,
        "_get_llm_adapter",
        lambda: SimpleNamespace(create_message=_raise),
    )
    repo = _patch_repo(monkeypatch, style_profile=_STYLE_PROFILE)
    _patch_handlers(
        monkeypatch, glowup_blocks=[_image_block("before"), _image_block("after")]
    )
    _patch_upload_id_resolver(monkeypatch, None)
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    caplog.set_level(logging.ERROR)
    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis}, _TEST_USER_ID, _TEST_JOB_ID
    )

    repo.insert_nudge.assert_not_called()


# ---------------------------------------------------------------------------
# Body-hash dedup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_body_hash_dedup_drops_within_30_days(monkeypatch, caplog):
    """body_hash collides with row 29 days old → dropped with METRIC_NUDGE_DUPLICATE_BODY."""
    from app.advisor import nudge_scheduler

    monkeypatch.setattr(
        nudge_scheduler, "_get_llm_adapter", lambda: _fake_llm(_GOOD_RESPONSE)
    )
    # find_duplicate_body returns True → duplicate exists
    repo = _patch_repo(
        monkeypatch, style_profile=_STYLE_PROFILE, find_duplicate_body=True
    )
    _patch_handlers(
        monkeypatch, glowup_blocks=[_image_block("before"), _image_block("after")]
    )
    _patch_upload_id_resolver(monkeypatch, None)
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    caplog.set_level(logging.INFO)
    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis}, _TEST_USER_ID, _TEST_JOB_ID
    )

    repo.insert_nudge.assert_not_called()
    dup_records = [
        r
        for r in caplog.records
        if getattr(r, "metric", None) == "advisor.nudge_duplicate_body"
    ]
    assert dup_records, "must emit nudge_duplicate_body metric"


@pytest.mark.asyncio
async def test_body_hash_dedup_proceeds_after_30_days(monkeypatch):
    """body_hash collides with row 31 days old → insert proceeds.

    find_duplicate_body checks ``created_at >= since`` (30-day window),
    so a 31-day-old row returns False.
    """
    from app.advisor import nudge_scheduler

    monkeypatch.setattr(
        nudge_scheduler, "_get_llm_adapter", lambda: _fake_llm(_GOOD_RESPONSE)
    )
    # find_duplicate_body returns False → outside window
    repo = _patch_repo(
        monkeypatch, style_profile=_STYLE_PROFILE, find_duplicate_body=False
    )
    _patch_handlers(
        monkeypatch, glowup_blocks=[_image_block("before"), _image_block("after")]
    )
    _patch_upload_id_resolver(monkeypatch, None)
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis}, _TEST_USER_ID, _TEST_JOB_ID
    )

    repo.insert_nudge.assert_called_once()


# ---------------------------------------------------------------------------
# Integration: 5 distinct responses → 5 rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_five_distinct_responses_persist_five_rows(monkeypatch):
    """5 distinct mock responses → 5 rows persisted with distinct body_hashes."""
    from app.advisor import nudge_scheduler

    bodies = [
        "Your warm undertone creates a gorgeous glow.",
        "The brow lift adds so much structure to your look.",
        "Softer jaw contouring reads beautifully here.",
        "The warmth in your highlight is so flattering.",
        "Clean liner makes your eyes pop in this shot.",
    ]
    seeds = [
        "What can I do to enhance my warm undertone?",
        "How can I maintain this brow lift effect?",
        "What techniques work best for a softer jaw look?",
        "Which highlight shades would suit my skin tone?",
        "How do I keep my liner looking this crisp?",
    ]
    responses = [
        (f'{{"body": "{b}", "next_step": {{"label": "Ask Ada", "seed": "{s}"}}}}')
        for b, s in zip(bodies, seeds)
    ]

    call_idx = 0

    def _llm_factory():
        async def _create(**_kwargs):
            nonlocal call_idx
            from app.advisor.models import LLMResponse

            r = LLMResponse(
                content=responses[call_idx], input_tokens=1, output_tokens=1
            )
            call_idx += 1
            return r

        return SimpleNamespace(create_message=_create)

    monkeypatch.setattr(nudge_scheduler, "_get_llm_adapter", _llm_factory)
    repo = _patch_repo(monkeypatch, style_profile=_STYLE_PROFILE)
    _patch_handlers(
        monkeypatch, glowup_blocks=[_image_block("before"), _image_block("after")]
    )
    _patch_upload_id_resolver(monkeypatch, None)

    for _ in range(5):
        redis = AsyncMock()
        redis.set = AsyncMock(return_value=True)
        await nudge_scheduler.generate_nudge(
            {"supabase": MagicMock(), "redis": redis}, _TEST_USER_ID, None
        )

    assert repo.insert_nudge.call_count == 5
    hashes = [c[0][0]["body_hash"] for c in repo.insert_nudge.call_args_list]
    assert len(set(hashes)) == 5, "all 5 body_hashes must be distinct"


# ---------------------------------------------------------------------------
# Integration: 5 identical responses → 1 row, 4 drops
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_five_identical_responses_persist_one_row(monkeypatch, caplog):
    """5 identical mock responses → 1 row persisted, 4 dropped by body-hash dedup."""
    # We use a real find_duplicate_body-like pattern:
    # repo.find_duplicate_body returns False on first call, True on subsequent.
    call_count = [0]

    from app.advisor import nudge_scheduler as _ns

    repo = MagicMock()
    repo.insert_nudge = MagicMock()
    repo.get_style_profile = MagicMock(return_value=_STYLE_PROFILE)
    repo.get_recent_nudge_context = MagicMock(return_value=[])

    def _find_dup(user_id, body_hash, since):
        call_count[0] += 1
        # First call: not a duplicate yet; subsequent calls: duplicate exists.
        return call_count[0] > 1

    repo.find_duplicate_body = _find_dup
    monkeypatch.setattr(_ns, "AdvisorRepository", MagicMock(return_value=repo))

    monkeypatch.setattr(_ns, "_get_llm_adapter", lambda: _fake_llm(_GOOD_RESPONSE))
    _patch_handlers(
        monkeypatch, glowup_blocks=[_image_block("before"), _image_block("after")]
    )
    _patch_upload_id_resolver(monkeypatch, None)

    caplog.set_level(logging.INFO)
    for _ in range(5):
        redis = AsyncMock()
        redis.set = AsyncMock(return_value=True)
        await _ns.generate_nudge(
            {"supabase": MagicMock(), "redis": redis}, _TEST_USER_ID, None
        )

    assert repo.insert_nudge.call_count == 1, "only first nudge must be persisted"
    dup_records = [
        r
        for r in caplog.records
        if getattr(r, "metric", None) == "advisor.nudge_duplicate_body"
    ]
    assert len(dup_records) == 4, "4 duplicates must be dropped"


# ---------------------------------------------------------------------------
# Integration: prompt contains last 5 bodies (novelty block)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prompt_contains_recent_bodies_novelty_block(monkeypatch):
    """Captured prompt contains the last 5 bodies in the novelty block."""
    from app.advisor import nudge_scheduler

    recent = [
        {
            "body": "Your jaw contour is striking.",
            "next_step_label": "Ask Ada",
            "next_step_seed": "How do I keep my jaw looking this defined?",
            "created_at": "2026-04-15T00:00:00Z",
        },
        {
            "body": "Brow lift adds so much lift here.",
            "next_step_label": "Try it",
            "next_step_seed": "What products work best for brow lift?",
            "created_at": "2026-04-14T00:00:00Z",
        },
    ]

    captured_prompts: list[str] = []

    async def _capturing_create(**kwargs):
        from app.advisor.models import LLMResponse

        msgs = kwargs.get("messages", [])
        for m in msgs:
            content = m.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if block.get("type") == "text":
                        captured_prompts.append(block["text"])
        return LLMResponse(content=_GOOD_RESPONSE, input_tokens=1, output_tokens=1)

    monkeypatch.setattr(
        nudge_scheduler,
        "_get_llm_adapter",
        lambda: SimpleNamespace(create_message=_capturing_create),
    )
    _patch_repo(monkeypatch, style_profile=_STYLE_PROFILE, recent_nudges=recent)
    _patch_handlers(
        monkeypatch, glowup_blocks=[_image_block("before"), _image_block("after")]
    )
    _patch_upload_id_resolver(monkeypatch, None)
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis}, _TEST_USER_ID, _TEST_JOB_ID
    )

    assert captured_prompts, "prompt must have been captured"
    prompt_text = captured_prompts[0]
    assert "Your jaw contour is striking." in prompt_text
    assert "Brow lift adds so much lift here." in prompt_text


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
        lambda: _fake_llm(_GOOD_RESPONSE),
    )

    repo = _patch_repo(monkeypatch, style_profile=_STYLE_PROFILE)
    _patch_handlers(
        monkeypatch,
        glowup_blocks=[_image_block("before"), _image_block("after")],
    )
    _patch_upload_id_resolver(monkeypatch, _TEST_UPLOAD_ID)

    redis = AsyncMock()
    redis.set = AsyncMock(side_effect=[True, None])

    caplog.set_level(logging.INFO)

    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis},
        _TEST_USER_ID,
        _TEST_JOB_ID,
    )
    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis},
        _TEST_USER_ID,
        _TEST_JOB_ID,
    )

    assert repo.insert_nudge.call_count == 1
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
        lambda: _fake_llm(_GOOD_RESPONSE),
    )

    repo = _patch_repo(monkeypatch, style_profile=_STYLE_PROFILE)
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
        _TEST_JOB_ID,
    )
    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis},
        _TEST_USER_ID,
        _TEST_JOB_ID,
    )

    redis.set.assert_not_called()
    assert repo.insert_nudge.call_count == 2


@pytest.mark.asyncio
async def test_rapid_retry_dedup_different_upload_does_not_skip(monkeypatch):
    """Different upload_ids → both runs proceed."""
    from app.advisor import nudge_scheduler

    monkeypatch.setattr(
        nudge_scheduler,
        "_get_llm_adapter",
        lambda: _fake_llm(_GOOD_RESPONSE),
    )

    repo = _patch_repo(monkeypatch, style_profile=_STYLE_PROFILE)
    _patch_handlers(
        monkeypatch,
        glowup_blocks=[_image_block("before"), _image_block("after")],
    )

    upload_ids = iter([_TEST_UPLOAD_ID, str(uuid4())])

    def _fake_resolve(_supabase, _job_id):
        return next(upload_ids)

    monkeypatch.setattr(nudge_scheduler, "_resolve_upload_id_for_job", _fake_resolve)

    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis},
        _TEST_USER_ID,
        _TEST_JOB_ID,
    )
    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis},
        _TEST_USER_ID,
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
            content=_GOOD_RESPONSE,
            input_tokens=1,
            output_tokens=1,
        )

    monkeypatch.setattr(
        nudge_scheduler,
        "_get_llm_adapter",
        lambda: SimpleNamespace(create_message=_create),
    )

    repo = _patch_repo(monkeypatch, style_profile=None)
    _patch_handlers(monkeypatch)

    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    caplog.set_level(logging.INFO)
    await nudge_scheduler.generate_nudge(
        {"supabase": MagicMock(), "redis": redis},
        _TEST_USER_ID,
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
    """Handler returns is_error text → skip rather than feed an empty prompt."""
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

    repo = _patch_repo(monkeypatch, style_profile=_STYLE_PROFILE)
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
        _TEST_JOB_ID,
    )

    assert not llm_calls, "LLM must not be called without any image blocks"
    repo.insert_nudge.assert_not_called()
