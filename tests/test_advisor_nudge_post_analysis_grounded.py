"""Post-analysis nudge grounding — Ada must reference the user's actual
face-analysis result, not hallucinate plausible-sounding details.

The prior prompt said "based on their latest result" but never included
the actual face_shape / symmetry_score / recommendations, so the LLM
invented topics (e.g. "your face shape") the user never saw. This
suite pins the contract:

- When the analysis endpoint passes the insight through, the LLM
  prompt contains the real result fields.
- When the insight arg is absent (cron retry, manual dispatch) the
  scheduler falls back to the most recent analysis_insight memory.
- When no insight exists at all, the nudge is skipped rather than
  emitted with hallucinated content.
- The model is Sonnet (Haiku produced generic, ungrounded nudges).
- The generic get_prompt path explicitly does NOT serve post_analysis.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


def _fake_llm_capture():
    """Return (fake_llm, captured) where captured is populated on call."""
    captured: dict = {}

    async def _capturing_create(**kwargs):
        from app.advisor.models import LLMResponse

        captured.update(kwargs)
        return LLMResponse(content="short grounded nudge", input_tokens=1, output_tokens=1)

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


def _patch_repo(monkeypatch, *, latest_insight: dict | None = None):
    """Patch AdvisorRepository so generate_nudge sees the given insight row."""
    from app.advisor import nudge_scheduler

    fake_repo = MagicMock()
    fake_repo.insert_nudge = MagicMock(return_value={"id": str(uuid4())})
    fake_repo.get_latest_analysis_insight = MagicMock(return_value=latest_insight)
    monkeypatch.setattr(
        nudge_scheduler, "AdvisorRepository", MagicMock(return_value=fake_repo)
    )
    return fake_repo


@pytest.mark.asyncio
async def test_post_analysis_nudge_injects_real_result_into_prompt(monkeypatch):
    """Insight arg passed through → LLM sees the real face_shape / symmetry / recs."""
    from app.advisor import nudge_scheduler

    fake_llm, captured = _fake_llm_capture()
    monkeypatch.setattr(nudge_scheduler, "_get_llm_adapter", lambda: fake_llm)
    _patch_entitlement(monkeypatch)
    fake_repo = _patch_repo(monkeypatch)

    insight = {
        "face_shape": "oval",
        "symmetry_score": 0.87,
        "recommendations": ["Trim sideburns", "Thicker brows", "Cooler tones"],
    }

    await nudge_scheduler.generate_nudge(
        {"supabase": object(), "redis": object()},
        str(uuid4()),
        nudge_scheduler.TRIGGER_POST_ANALYSIS,
        insight,
    )

    assert captured, "LLM adapter was not called"
    user_content = captured["messages"][0]["content"]
    assert "oval" in user_content, "face_shape must appear in prompt"
    assert "0.9" in user_content or "0.87" in user_content, (
        "symmetry_score must appear in prompt"
    )
    assert "Trim sideburns" in user_content, "recommendations must appear in prompt"
    # Caller-provided insight is authoritative — the repo fallback MUST NOT fire.
    fake_repo.get_latest_analysis_insight.assert_not_called()


@pytest.mark.asyncio
async def test_post_analysis_nudge_uses_sonnet_model(monkeypatch):
    """Haiku was producing ungrounded nudges; pin Sonnet for this path."""
    from app.advisor import nudge_scheduler
    from app.config import settings

    fake_llm, captured = _fake_llm_capture()
    monkeypatch.setattr(nudge_scheduler, "_get_llm_adapter", lambda: fake_llm)
    _patch_entitlement(monkeypatch)
    _patch_repo(monkeypatch)

    await nudge_scheduler.generate_nudge(
        {"supabase": object(), "redis": object()},
        str(uuid4()),
        nudge_scheduler.TRIGGER_POST_ANALYSIS,
        {
            "face_shape": "round",
            "symmetry_score": 0.9,
            "recommendations": ["Add volume on top"],
        },
    )

    assert captured["model"] == settings.ADVISOR_MODEL_SONNET
    assert captured["model"] != settings.ADVISOR_MODEL_HAIKU


@pytest.mark.asyncio
async def test_post_analysis_nudge_falls_back_to_repo_when_insight_missing(monkeypatch):
    """Cron retries / manual dispatch pass insight=None → load from memory."""
    from app.advisor import nudge_scheduler

    fake_llm, captured = _fake_llm_capture()
    monkeypatch.setattr(nudge_scheduler, "_get_llm_adapter", lambda: fake_llm)
    _patch_entitlement(monkeypatch)
    fake_repo = _patch_repo(
        monkeypatch,
        latest_insight={
            "content": {
                "face_shape": "heart",
                "symmetry_score": 0.72,
                "recommendations": ["Softer fringe"],
            },
            "created_at": "2026-04-16T00:00:00Z",
        },
    )

    await nudge_scheduler.generate_nudge(
        {"supabase": object(), "redis": object()},
        str(uuid4()),
        nudge_scheduler.TRIGGER_POST_ANALYSIS,
        # insight arg omitted on purpose
    )

    fake_repo.get_latest_analysis_insight.assert_called_once()
    user_content = captured["messages"][0]["content"]
    assert "heart" in user_content
    assert "Softer fringe" in user_content


@pytest.mark.asyncio
async def test_post_analysis_nudge_skips_when_no_insight_anywhere(monkeypatch):
    """No insight arg + empty memory → skip entirely (no LLM, no DB write).

    The old code would call the LLM with a generic template and the
    model would hallucinate. Skipping is the only safe default.
    """
    from app.advisor import nudge_scheduler

    fake_llm, captured = _fake_llm_capture()
    monkeypatch.setattr(nudge_scheduler, "_get_llm_adapter", lambda: fake_llm)
    _patch_entitlement(monkeypatch)
    fake_repo = _patch_repo(monkeypatch, latest_insight=None)

    await nudge_scheduler.generate_nudge(
        {"supabase": object(), "redis": object()},
        str(uuid4()),
        nudge_scheduler.TRIGGER_POST_ANALYSIS,
    )

    assert not captured, "LLM must not be called when no insight exists"
    fake_repo.insert_nudge.assert_not_called()
    fake_repo.get_latest_analysis_insight.assert_called_once()


@pytest.mark.parametrize(
    "row",
    [
        {"content": None, "created_at": "2026-04-16T00:00:00Z"},
        {"content": {}, "created_at": "2026-04-16T00:00:00Z"},
    ],
    ids=["content-is-None", "content-is-empty-dict"],
)
@pytest.mark.asyncio
async def test_post_analysis_nudge_skips_when_insight_row_has_empty_content(
    monkeypatch, row
):
    """Partial / legacy insight rows must NOT slip through.

    If the row exists but `content` is `None` or `{}`, the prompt would
    render `face_shape: unknown` and Sonnet would happily ground the
    nudge on `unknown` — the exact hallucination this module exists to
    prevent. Treat an empty content payload as missing.
    """
    from app.advisor import nudge_scheduler

    fake_llm, captured = _fake_llm_capture()
    monkeypatch.setattr(nudge_scheduler, "_get_llm_adapter", lambda: fake_llm)
    _patch_entitlement(monkeypatch)
    fake_repo = _patch_repo(monkeypatch, latest_insight=row)

    await nudge_scheduler.generate_nudge(
        {"supabase": object(), "redis": object()},
        str(uuid4()),
        nudge_scheduler.TRIGGER_POST_ANALYSIS,
    )

    assert not captured, "LLM must not be called for empty insight content"
    fake_repo.insert_nudge.assert_not_called()


@pytest.mark.asyncio
async def test_post_analysis_nudge_does_not_persist_blank_llm_response(monkeypatch):
    """If Sonnet ever returns whitespace-only content, do not save it.

    Pinned because the persistence guard at line ~146 of nudge_scheduler
    runs after the strip — without this test a future refactor that
    moves the strip could silently insert empty nudges into the feed.
    """
    from app.advisor import nudge_scheduler
    from app.advisor.models import LLMResponse

    async def _blank_llm(**_kwargs):
        return LLMResponse(content="   \n  ", input_tokens=1, output_tokens=1)

    monkeypatch.setattr(
        nudge_scheduler,
        "_get_llm_adapter",
        lambda: SimpleNamespace(create_message=_blank_llm),
    )
    _patch_entitlement(monkeypatch)
    fake_repo = _patch_repo(monkeypatch)

    await nudge_scheduler.generate_nudge(
        {"supabase": object(), "redis": object()},
        str(uuid4()),
        nudge_scheduler.TRIGGER_POST_ANALYSIS,
        {
            "face_shape": "oval",
            "symmetry_score": 0.9,
            "recommendations": ["Some rec"],
        },
    )

    fake_repo.insert_nudge.assert_not_called()


@pytest.mark.asyncio
async def test_schedule_post_analysis_nudge_inline_passes_insight(monkeypatch):
    """No arq_pool in ctx → schedule runs generate_nudge inline WITH insight."""
    from app.advisor import nudge_scheduler

    captured: dict = {}

    async def _fake_generate(ctx, user_id, trigger, insight=None):
        captured["trigger"] = trigger
        captured["insight"] = insight

    monkeypatch.setattr(nudge_scheduler, "generate_nudge", _fake_generate)

    await nudge_scheduler.schedule_post_analysis_nudge(
        {},  # no arq_pool → inline path
        str(uuid4()),
        face_shape="square",
        symmetry_score=0.81,
        recommendations=["Trim beard lower", "More contrast in jacket"],
    )

    assert captured["trigger"] == nudge_scheduler.TRIGGER_POST_ANALYSIS
    assert captured["insight"] == {
        "face_shape": "square",
        "symmetry_score": 0.81,
        "recommendations": ["Trim beard lower", "More contrast in jacket"],
    }


@pytest.mark.asyncio
async def test_schedule_post_analysis_nudge_enqueues_with_insight(monkeypatch):
    """arq_pool present → enqueue_job receives the insight dict as a job arg."""
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
        {
            "face_shape": "oval",
            "symmetry_score": 0.9,
            "recommendations": ["Rec A"],
        },
    )


def test_get_prompt_refuses_post_analysis():
    """The generic template path must NOT silently serve post_analysis —
    that trigger is grounded via build_post_analysis_prompt."""
    from app.advisor.nudge_policy import TRIGGER_POST_ANALYSIS
    from app.advisor.nudge_templates import get_prompt

    with pytest.raises(KeyError):
        get_prompt(TRIGGER_POST_ANALYSIS)


def test_build_post_analysis_prompt_includes_all_result_fields():
    """The grounded prompt must surface every fact the LLM is allowed to use."""
    from app.advisor.nudge_templates import build_post_analysis_prompt

    prompt = build_post_analysis_prompt(
        face_shape="oval",
        symmetry_score=0.873,
        recommendations=[
            "Rec-one-kept",
            "Rec-two-kept",
            "Rec-three-kept",
            "Rec-four-dropped",
            "Rec-five-dropped",
        ],
    )

    assert "oval" in prompt
    assert "0.9" in prompt  # rounded to 1 dp per template
    # Top 3 recs only, per _POST_ANALYSIS_RECS_LIMIT
    assert "Rec-one-kept" in prompt
    assert "Rec-two-kept" in prompt
    assert "Rec-three-kept" in prompt
    assert "Rec-four-dropped" not in prompt
    assert "Rec-five-dropped" not in prompt


def test_build_post_analysis_prompt_tolerates_missing_fields():
    """If the analysis pipeline ever hands back partial data, build a prompt
    that still reads cleanly rather than raising."""
    from app.advisor.nudge_templates import build_post_analysis_prompt

    prompt = build_post_analysis_prompt(
        face_shape=None, symmetry_score=None, recommendations=None
    )

    assert "unknown" in prompt  # face_shape fallback
    assert "(none recorded)" in prompt  # recommendations fallback
