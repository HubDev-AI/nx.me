"""Post-analysis nudge grounding — Unit 8 vision-grounded path.

Plan 2026-04-17-003 Unit 8. The face-shape-parroting prompt (and the
briefly-considered deterministic focus-topic rotation) have been
replaced by a vision-grounded builder: the model looks at the actual
source photo (and the glow-up after when one exists), reads the stable
``style_profile``, and the last N nudge bodies + ``observation_tag``s,
then decides what to say. This suite pins the new contract:

- The prompt is vision-grounded and carries the stable profile block
  + recent-nudges "don't repeat" block.
- Output is strict JSON ``{"body", "observation_tag"}``; parse
  failure drops the nudge with no persistence.
- Users without a ``style_profile`` are skipped with a structured log.
- The generic ``get_prompt`` path still refuses ``post_analysis`` /
  ``post_glowup``.
- Model is Haiku (vision-capable) — pinned against regression to
  Sonnet (reverted 2026-04-17) and to any swap that would lose vision.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


_TEST_USER_ID = str(uuid4())


def _fake_llm_capture(
    response_text: str = '{"body": "short grounded nudge", "observation_tag": "cleaner brows"}',
):
    """Return (fake_llm, captured) where captured is populated on call."""
    captured: dict = {}

    async def _capturing_create(**kwargs):
        from app.advisor.models import LLMResponse

        captured.update(kwargs)
        return LLMResponse(content=response_text, input_tokens=1, output_tokens=1)

    return SimpleNamespace(create_message=_capturing_create), captured


def _patch_entitlement(monkeypatch, *, allowed: bool = True):
    fake_ent = MagicMock()
    fake_ent.check = AsyncMock(
        return_value=SimpleNamespace(allowed=allowed, error_code=None)
    )
    monkeypatch.setattr(
        "app.entitlement.service.EntitlementService",
        MagicMock(return_value=fake_ent),
    )


def _patch_repo(
    monkeypatch,
    *,
    style_profile: dict | None = None,
    recent_nudge_context: list[dict] | None = None,
):
    """Patch AdvisorRepository so generate_nudge sees stubbed profile + context.

    ``style_profile`` is the row returned by ``get_style_profile`` (carries
    ``content`` + ``created_at``). Pass ``None`` to exercise the "no
    profile → skip" path.
    """
    from app.advisor import nudge_scheduler

    fake_repo = MagicMock()
    fake_repo.insert_nudge = MagicMock(return_value={"id": str(uuid4())})
    fake_repo.get_style_profile = MagicMock(return_value=style_profile)
    fake_repo.get_recent_nudge_context = MagicMock(
        return_value=recent_nudge_context or []
    )
    monkeypatch.setattr(
        nudge_scheduler, "AdvisorRepository", MagicMock(return_value=fake_repo)
    )
    return fake_repo


def _patch_image_fetch(monkeypatch, image_blocks: list[dict] | None = None):
    """Patch the two MCP vision handlers so the scheduler sees deterministic output.

    Defaults to returning an envelope with ``is_error=True`` for
    ``_handle_get_latest_glowup`` (no glow-up yet) and a single image
    block for ``_handle_get_latest_photo`` — the degenerate
    post_analysis shape. Handler shape is
    ``{"content": [...], "is_error": bool}`` (Plan 2026-04-17 review fix).
    """
    from app.advisor import nudge_scheduler

    if image_blocks is None:
        image_blocks = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": "AAAA",
                },
            }
        ]

    async def _fake_glowup(_ctx):
        # No glow-up → envelope is_error=True, text block with no inner flag.
        return {
            "content": [{"type": "text", "text": "no completed glow-up"}],
            "is_error": True,
        }

    async def _fake_photo(_ctx):
        return {"content": list(image_blocks), "is_error": False}

    monkeypatch.setattr(nudge_scheduler, "_handle_get_latest_glowup", _fake_glowup)
    monkeypatch.setattr(nudge_scheduler, "_handle_get_latest_photo", _fake_photo)


# ---------------------------------------------------------------------------
# Prompt shape + JSON output
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_analysis_nudge_prompt_is_vision_grounded(monkeypatch):
    """Prompt carries profile block + recent-nudges block + JSON contract."""
    from app.advisor import nudge_scheduler

    fake_llm, captured = _fake_llm_capture()
    monkeypatch.setattr(nudge_scheduler, "_get_llm_adapter", lambda: fake_llm)
    _patch_entitlement(monkeypatch)
    _patch_repo(
        monkeypatch,
        style_profile={
            "content": {
                "face_shape": "oval",
                "symmetry_score": 0.87,
                "recommendations": ["Trim sideburns", "Thicker brows"],
            },
            "created_at": "2026-04-17T00:00:00Z",
        },
        recent_nudge_context=[
            {
                "body": "prior nudge body",
                "observation_tag": "softer jaw",
                "created_at": "2026-04-16T00:00:00Z",
            }
        ],
    )
    _patch_image_fetch(monkeypatch)

    await nudge_scheduler.generate_nudge(
        {"supabase": object(), "redis": object()},
        _TEST_USER_ID,
        nudge_scheduler.TRIGGER_POST_ANALYSIS,
    )

    assert captured, "LLM adapter was not called"
    user_content = captured["messages"][0]["content"]
    # Vision-grounded path: content is a list [text, image, ...]
    assert isinstance(user_content, list), (
        "vision prompt must be a list of content blocks"
    )
    text_block = next(b for b in user_content if b.get("type") == "text")
    image_blocks = [b for b in user_content if b.get("type") == "image"]
    assert image_blocks, "must attach at least one image block"

    prompt = text_block["text"]
    assert "oval face" in prompt, "profile block should render face shape"
    assert "Trim sideburns" in prompt, "profile block should render recommendations"
    assert "softer jaw" in prompt, "recent-nudges block should render observation_tag"
    assert "prior nudge body" in prompt, "recent-nudges block should render body"
    assert "body" in prompt and "observation_tag" in prompt, (
        "prompt must state the JSON output contract explicitly"
    )


@pytest.mark.asyncio
async def test_vision_nudge_persists_body_and_observation_tag(monkeypatch):
    """Parsed JSON's body goes into ``content``; observation_tag goes in its column."""
    from app.advisor import nudge_scheduler

    fake_llm, _captured = _fake_llm_capture(
        response_text='{"body": "something warm about the new look",'
        ' "observation_tag": "brighter eyes"}'
    )
    monkeypatch.setattr(nudge_scheduler, "_get_llm_adapter", lambda: fake_llm)
    _patch_entitlement(monkeypatch)
    fake_repo = _patch_repo(
        monkeypatch,
        style_profile={
            "content": {"face_shape": "heart", "symmetry_score": 0.8},
            "created_at": "2026-04-17T00:00:00Z",
        },
    )
    _patch_image_fetch(monkeypatch)

    await nudge_scheduler.generate_nudge(
        {"supabase": object(), "redis": object()},
        _TEST_USER_ID,
        nudge_scheduler.TRIGGER_POST_ANALYSIS,
    )

    fake_repo.insert_nudge.assert_called_once()
    persisted = fake_repo.insert_nudge.call_args[0][0]
    assert persisted["content"] == "something warm about the new look"
    assert persisted["observation_tag"] == "brighter eyes"
    assert persisted["trigger"] == nudge_scheduler.TRIGGER_POST_ANALYSIS


@pytest.mark.asyncio
async def test_vision_nudge_accepts_fenced_json(monkeypatch):
    """Model wraps JSON in ```json … ``` → fence stripped, nudge persisted.

    Observed 2026-04-17: Haiku wraps strict-JSON responses in a markdown
    fence even when the prompt forbids markdown, which silently dropped
    every post_glowup / post_analysis nudge. ``_strip_json_code_fence``
    unwraps the fence before ``json.loads``.
    """
    from app.advisor import nudge_scheduler

    fake_llm, _captured = _fake_llm_capture(
        response_text=(
            "```json\n"
            '{"body": "warm sentence about the new look",'
            ' "observation_tag": "warmer tone"}\n'
            "```"
        )
    )
    monkeypatch.setattr(nudge_scheduler, "_get_llm_adapter", lambda: fake_llm)
    _patch_entitlement(monkeypatch)
    fake_repo = _patch_repo(
        monkeypatch,
        style_profile={
            "content": {"face_shape": "oblong", "symmetry_score": 0.97},
            "created_at": "2026-04-17T00:00:00Z",
        },
    )
    _patch_image_fetch(monkeypatch)

    await nudge_scheduler.generate_nudge(
        {"supabase": object(), "redis": object()},
        _TEST_USER_ID,
        nudge_scheduler.TRIGGER_POST_ANALYSIS,
    )

    fake_repo.insert_nudge.assert_called_once()
    persisted = fake_repo.insert_nudge.call_args[0][0]
    assert persisted["content"] == "warm sentence about the new look"
    assert persisted["observation_tag"] == "warmer tone"


@pytest.mark.asyncio
async def test_vision_nudge_drops_malformed_json(monkeypatch, caplog):
    """Model returns non-JSON → nudge dropped, no partial row persisted."""
    from app.advisor import nudge_scheduler

    fake_llm, _captured = _fake_llm_capture(
        response_text="This is plain text not JSON at all."
    )
    monkeypatch.setattr(nudge_scheduler, "_get_llm_adapter", lambda: fake_llm)
    _patch_entitlement(monkeypatch)
    fake_repo = _patch_repo(
        monkeypatch,
        style_profile={
            "content": {"face_shape": "oval", "symmetry_score": 0.9},
            "created_at": "2026-04-17T00:00:00Z",
        },
    )
    _patch_image_fetch(monkeypatch)

    caplog.set_level(logging.WARNING)
    await nudge_scheduler.generate_nudge(
        {"supabase": object(), "redis": object()},
        _TEST_USER_ID,
        nudge_scheduler.TRIGGER_POST_ANALYSIS,
    )

    fake_repo.insert_nudge.assert_not_called()
    assert any("malformed JSON" in record.message for record in caplog.records), (
        "must log a warning identifying the malformed JSON drop"
    )


@pytest.mark.asyncio
async def test_vision_nudge_skips_when_no_style_profile(monkeypatch):
    """No style_profile → skip entirely (no LLM, no DB write).

    Was the pre-redesign behavior and still the safest default: the
    prompt's "stable facts" block has nothing to render on.
    """
    from app.advisor import nudge_scheduler

    fake_llm, captured = _fake_llm_capture()
    monkeypatch.setattr(nudge_scheduler, "_get_llm_adapter", lambda: fake_llm)
    _patch_entitlement(monkeypatch)
    fake_repo = _patch_repo(monkeypatch, style_profile=None)
    _patch_image_fetch(monkeypatch)

    await nudge_scheduler.generate_nudge(
        {"supabase": object(), "redis": object()},
        _TEST_USER_ID,
        nudge_scheduler.TRIGGER_POST_ANALYSIS,
    )

    assert not captured, "LLM must not be called without a style_profile"
    fake_repo.insert_nudge.assert_not_called()


@pytest.mark.asyncio
async def test_vision_nudge_uses_haiku_model(monkeypatch):
    """Pin Haiku (vision-capable). Sonnet revert + Haiku 4.5 both supported."""
    from app.advisor import nudge_scheduler
    from app.config import settings

    fake_llm, captured = _fake_llm_capture()
    monkeypatch.setattr(nudge_scheduler, "_get_llm_adapter", lambda: fake_llm)
    _patch_entitlement(monkeypatch)
    _patch_repo(
        monkeypatch,
        style_profile={
            "content": {"face_shape": "round", "symmetry_score": 0.9},
            "created_at": "2026-04-17T00:00:00Z",
        },
    )
    _patch_image_fetch(monkeypatch)

    await nudge_scheduler.generate_nudge(
        {"supabase": object(), "redis": object()},
        _TEST_USER_ID,
        nudge_scheduler.TRIGGER_POST_ANALYSIS,
    )

    assert captured["model"] == settings.ADVISOR_MODEL_HAIKU


@pytest.mark.asyncio
async def test_vision_nudge_one_image_degenerate_case_still_grounds(monkeypatch):
    """post_analysis with only a source photo must still invoke the model.

    The prompt explicitly handles the "only one image attached" case —
    we assert here that (a) exactly one image block reaches the model,
    and (b) the generation proceeds without raising or silent-skipping.
    """
    from app.advisor import nudge_scheduler

    fake_llm, captured = _fake_llm_capture()
    monkeypatch.setattr(nudge_scheduler, "_get_llm_adapter", lambda: fake_llm)
    _patch_entitlement(monkeypatch)
    _patch_repo(
        monkeypatch,
        style_profile={
            "content": {"face_shape": "oval", "symmetry_score": 0.87},
            "created_at": "2026-04-17T00:00:00Z",
        },
    )
    _patch_image_fetch(monkeypatch)  # default → 1 source photo block

    await nudge_scheduler.generate_nudge(
        {"supabase": object(), "redis": object()},
        _TEST_USER_ID,
        nudge_scheduler.TRIGGER_POST_ANALYSIS,
    )

    assert captured, "LLM must be invoked even with a single image"
    content = captured["messages"][0]["content"]
    image_count = sum(1 for b in content if b.get("type") == "image")
    assert image_count == 1, "degenerate post_analysis should attach exactly 1 image"


# ---------------------------------------------------------------------------
# Schedule wrapper behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schedule_post_analysis_nudge_inline_fires_trigger(monkeypatch):
    """No arq_pool in ctx → schedule runs generate_nudge inline."""
    from app.advisor import nudge_scheduler

    captured: dict = {}

    async def _fake_generate(ctx, user_id, trigger, *args, **kwargs):
        captured["trigger"] = trigger
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setattr(nudge_scheduler, "generate_nudge", _fake_generate)

    await nudge_scheduler.schedule_post_analysis_nudge(
        {},  # no arq_pool → inline path
        _TEST_USER_ID,
        face_shape="square",
        symmetry_score=0.81,
        recommendations=["Trim beard lower"],
    )

    assert captured["trigger"] == nudge_scheduler.TRIGGER_POST_ANALYSIS


@pytest.mark.asyncio
async def test_schedule_post_analysis_nudge_enqueues_without_insight_payload(
    monkeypatch,
):
    """arq_pool present → enqueue_job fires without the legacy insight dict.

    Unit 8 dropped the ``insight`` payload on the enqueue side — the
    vision path reads stable facts from ``style_profile`` instead. The
    wrapper's signature stays stable for API compat.
    """
    from app.advisor import nudge_scheduler

    arq_pool = MagicMock()
    arq_pool.enqueue_job = AsyncMock()

    await nudge_scheduler.schedule_post_analysis_nudge(
        {"arq_pool": arq_pool},
        "user-123",
        face_shape="oval",
        symmetry_score=0.9,
        recommendations=["Rec A"],
    )

    arq_pool.enqueue_job.assert_awaited_once_with(
        "generate_nudge",
        "user-123",
        nudge_scheduler.TRIGGER_POST_ANALYSIS,
    )


# ---------------------------------------------------------------------------
# Template invariants
# ---------------------------------------------------------------------------


def test_get_prompt_refuses_vision_triggers():
    """Generic template path must NOT serve post_analysis / post_glowup.

    Both are vision-grounded via ``build_vision_nudge_prompt``.
    """
    from app.advisor.nudge_policy import TRIGGER_POST_ANALYSIS, TRIGGER_POST_GLOWUP
    from app.advisor.nudge_templates import get_prompt

    with pytest.raises(KeyError):
        get_prompt(TRIGGER_POST_ANALYSIS)
    with pytest.raises(KeyError):
        get_prompt(TRIGGER_POST_GLOWUP)


def test_build_post_analysis_prompt_removed():
    """The old grounded-facts builder is retired.

    Unit 8 deletes ``build_post_analysis_prompt`` — its prompt shape
    (face_shape + symmetry + top-3 recommendations as bullets with
    instructions to reference at least one) was superseded by
    ``build_vision_nudge_prompt``. Keep this guard so a resurrected
    stub would fail loudly.
    """
    from app.advisor import nudge_templates

    assert not hasattr(nudge_templates, "build_post_analysis_prompt"), (
        "Unit 8 removed build_post_analysis_prompt — vision path "
        "authored the replacement."
    )


def test_build_vision_nudge_prompt_renders_profile_and_recent():
    """Vision prompt surfaces the profile shape + recent context verbatim."""
    from app.advisor.nudge_templates import build_vision_nudge_prompt

    prompt = build_vision_nudge_prompt(
        profile={
            "face_shape": "oval",
            "symmetry_score": 0.873,
            "recommendations": [
                "Softer fringe",
                "Warmer tones",
                "Layered cut",
                "Rec-four-dropped",
            ],
        },
        recent_nudges=[
            {"body": "Yesterday's nudge", "observation_tag": "brighter eyes"},
            {"body": "Two days ago", "observation_tag": None},  # pre-migration row
        ],
    )

    assert "oval face" in prompt
    assert "symmetry 0.87" in prompt
    assert "Softer fringe" in prompt
    assert "Rec-four-dropped" not in prompt, "profile block caps at top 3 recs"
    assert "Yesterday's nudge" in prompt
    assert "brighter eyes" in prompt
    assert "no tag" in prompt, "NULL observation_tag should render as 'no tag'"
    # Output contract:
    assert '"body"' in prompt and '"observation_tag"' in prompt


def test_build_vision_nudge_prompt_handles_missing_profile():
    """Degenerate: missing profile still yields a readable prompt."""
    from app.advisor.nudge_templates import build_vision_nudge_prompt

    prompt = build_vision_nudge_prompt(profile=None, recent_nudges=None)

    assert "no stable profile" in prompt
    assert "(none)" in prompt, "empty recent-nudges block should render (none)"


def test_trigger_post_glowup_constant_exists():
    """Unit 8 adds TRIGGER_POST_GLOWUP — the worker fires it on completion."""
    from app.advisor.nudge_policy import TRIGGER_POST_GLOWUP

    assert TRIGGER_POST_GLOWUP == "post_glowup"


def test_focus_topics_tuple_absent():
    """The earlier deterministic rotation was wrong — prove it never returned.

    A ``FOCUS_TOPICS = (hair, beard, brows, skin, fit, accessories)``
    tuple on ``nudge_policy`` would reintroduce a server-authored
    taxonomy — incorrect on a women-primary audience. This guard fails
    loudly if a refactor ever resurrects it.
    """
    from app.advisor import nudge_policy

    assert not hasattr(nudge_policy, "FOCUS_TOPICS"), (
        "FOCUS_TOPICS was an earlier mistake; Unit 8 removed it."
    )
