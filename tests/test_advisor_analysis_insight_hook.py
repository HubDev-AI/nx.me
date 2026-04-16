"""Analysis-insight hook — verifies `analyze_glowup` enqueues the ARQ job
that writes an `analysis_insight` memory row for the user.

Spec: advisor-spec.md §4.5, §16.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.glowup import analyze_glowup
from app.services.glowup_service import GlowupAnalysisResult


def _claims(user_id: str | None = None) -> dict:
    return {"sub": user_id or str(uuid4()), "role": "authenticated"}


def _glowup_svc(face_shape: str = "oval", symmetry: float = 0.87) -> MagicMock:
    svc = MagicMock()
    svc.create_analysis = AsyncMock(
        return_value=GlowupAnalysisResult(
            glowup_analysis_id=uuid4(),
            face_shape=face_shape,
            symmetry_score=symmetry,
            recommendations=[
                {
                    "rank": 1,
                    "category": "hair",
                    "suggestion_text": "Try bangs",
                    "rationale": "softens forehead",
                },
                {
                    "rank": 2,
                    "category": "brows",
                    "suggestion_text": "Clean up arch",
                    "rationale": "stronger frame",
                },
            ],
        )
    )
    return svc


def _request_with_pool(enqueue: AsyncMock) -> MagicMock:
    req = MagicMock()
    req.app.state.arq_pool.enqueue_job = enqueue
    return req


@pytest.mark.asyncio
async def test_hook_enqueues_insight_job_when_advisor_enabled(monkeypatch):
    """Happy path: successful analyze enqueues write_analysis_insight_job."""
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_ENABLED", True)

    enqueue = AsyncMock()
    user_id = str(uuid4())
    upload_id = uuid4()

    await analyze_glowup(
        upload_id=upload_id,
        request=_request_with_pool(enqueue),
        claims=_claims(user_id),
        glowup_svc=_glowup_svc(face_shape="heart", symmetry=0.82),
    )

    job_names = [call.args[0] for call in enqueue.await_args_list]
    assert "write_analysis_insight_job" in job_names, (
        f"Expected write_analysis_insight_job to be enqueued, got: {job_names}"
    )

    insight_call = next(
        c for c in enqueue.await_args_list if c.args[0] == "write_analysis_insight_job"
    )
    _name, *args = insight_call.args
    assert args[0] == user_id
    assert args[1] == "heart"
    assert args[2] == pytest.approx(0.82)
    assert args[3] == ["Try bangs", "Clean up arch"]
    assert args[4] == str(upload_id)


@pytest.mark.asyncio
async def test_hook_skips_insight_job_when_advisor_disabled(monkeypatch):
    """Feature flag off: no insight job enqueued (and no nudge either)."""
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_ENABLED", False)

    enqueue = AsyncMock()

    await analyze_glowup(
        upload_id=uuid4(),
        request=_request_with_pool(enqueue),
        claims=_claims(),
        glowup_svc=_glowup_svc(),
    )

    job_names = [call.args[0] for call in enqueue.await_args_list]
    assert "write_analysis_insight_job" not in job_names


@pytest.mark.asyncio
async def test_hook_failure_does_not_block_response(monkeypatch):
    """Enqueue raising must not turn a successful analysis into 5xx."""
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_ENABLED", True)

    enqueue = AsyncMock(side_effect=RuntimeError("redis down"))

    result = await analyze_glowup(
        upload_id=uuid4(),
        request=_request_with_pool(enqueue),
        claims=_claims(),
        glowup_svc=_glowup_svc(face_shape="oval"),
    )
    assert result.face_shape == "oval"


@pytest.mark.asyncio
async def test_insight_job_writes_memory_for_owner(monkeypatch):
    """Unit: write_analysis_insight_job dispatches to memory_manager with caller's user_id."""
    from app.advisor import nudge_scheduler

    user_id = str(uuid4())
    captured: dict = {}

    async def _fake_write(**kwargs):
        captured.update(kwargs)

    fake_mm = SimpleNamespace(write_analysis_insight=_fake_write)

    async def _fake_builder(ctx):
        return fake_mm

    monkeypatch.setattr(nudge_scheduler, "_build_memory_manager", _fake_builder)

    await nudge_scheduler.write_analysis_insight_job(
        {"supabase": object(), "redis": object()},
        user_id,
        "oval",
        0.9,
        ["Try bangs"],
        str(uuid4()),
    )

    assert str(captured["user_id"]) == user_id
    assert captured["face_shape"] == "oval"
    assert captured["symmetry_score"] == 0.9
    assert captured["recommendations"] == ["Try bangs"]
