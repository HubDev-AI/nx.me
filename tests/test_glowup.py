"""Tests for the glowup API routes.

Exercises:
  - app/api/glowup.py (AnalyzeResponse, SuggestionResponse models)
  - app/repositories/glowup_analysis_repo.py (GlowupAnalysisRepository)
  - app/api/glowup.analyze_glowup handler (consent 428 gate)
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace
from uuid import uuid4


try:
    from app.api.glowup import (
        AnalyzeResponse,
        SuggestionResponse,
        GenerateRequest,
        GenerateResponse,
        analyze_glowup,
        generate_glowup,
    )
    from app.repositories.glowup_analysis_repo import GlowupAnalysisRepository
    from tests.conftest import MockSupabase

    _AVAILABLE = True
except (ImportError, AttributeError):
    _AVAILABLE = False

pytestmark = pytest.mark.skipif(not _AVAILABLE, reason="glowup module unavailable")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_claims(user_id: str | None = None) -> dict:
    return {"sub": user_id or str(uuid4()), "role": "authenticated"}


def _make_glowup_service(
    analysis_id=None,
    face_shape="oval",
    symmetry_score=0.85,
    raises=None,
) -> MagicMock:
    from app.services.glowup_service import GlowupAnalysisResult

    svc = MagicMock()
    if raises:
        svc.create_analysis = AsyncMock(side_effect=raises)
    else:
        aid = analysis_id or uuid4()
        svc.create_analysis = AsyncMock(
            return_value=GlowupAnalysisResult(
                glowup_analysis_id=aid,
                face_shape=face_shape,
                symmetry_score=symmetry_score,
                recommendations=[
                    {
                        "rank": 1,
                        "category": "hair",
                        "suggestion_text": "Try bangs",
                        "rationale": "Softens forehead",
                    },
                ],
            )
        )
    return svc


# ---------------------------------------------------------------------------
# GlowupAnalysisRepository unit tests
# ---------------------------------------------------------------------------


class TestGlowupAnalysisRepository:
    """Unit tests for GlowupAnalysisRepository."""

    def test_get_by_id_returns_none_when_missing(self):
        from tests.conftest import MockSupabase

        sb = MockSupabase()
        sb.set_table_data("glowup_analyses", None)
        repo = GlowupAnalysisRepository(sb)
        result = repo.get_by_id(str(uuid4()))
        assert result is None

    def test_get_by_upload_id_returns_row(self):
        from tests.conftest import MockSupabase

        upload_id = str(uuid4())
        row = {
            "id": str(uuid4()),
            "upload_id": upload_id,
            "face_shape": "oval",
            "symmetry_score": 0.8,
            "recommendations": [],
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        sb = MockSupabase()
        sb.set_table_data("glowup_analyses", [row])
        repo = GlowupAnalysisRepository(sb)
        result = repo.get_by_upload_id(upload_id)
        assert result is not None
        assert result["face_shape"] == "oval"

    def test_insert_returns_row(self):
        from tests.conftest import MockSupabase

        uid = str(uuid4())
        row = {
            "id": uid,
            "upload_id": str(uuid4()),
            "face_shape": "round",
            "symmetry_score": 0.75,
            "recommendations": [],
        }
        sb = MockSupabase()
        sb.set_table_data("glowup_analyses", [row])
        repo = GlowupAnalysisRepository(sb)
        result = repo.insert(row)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# AnalyzeResponse + SuggestionResponse model tests
# ---------------------------------------------------------------------------


class TestGlowupResponseModels:
    """Pydantic model tests."""

    def test_suggestion_response(self):
        s = SuggestionResponse(rank=2, category="skin", suggestion="Use SPF 50")
        assert s.rank == 2
        assert s.category == "skin"

    def test_analyze_response_minimal(self):
        resp = AnalyzeResponse(
            glowup_analysis_id=str(uuid4()),
            face_shape="square",
            symmetry_score=0.9,
            recommendations=[],
        )
        assert resp.face_shape == "square"
        assert resp.symmetry_score == 0.9

    def test_analyze_response_with_suggestions(self):
        resp = AnalyzeResponse(
            glowup_analysis_id=str(uuid4()),
            face_shape="heart",
            symmetry_score=0.78,
            recommendations=[
                SuggestionResponse(rank=1, category="hair", suggestion="Add volume"),
            ],
        )
        assert len(resp.recommendations) == 1
        assert resp.recommendations[0].rank == 1


# ---------------------------------------------------------------------------
# analyze_glowup handler tests
# ---------------------------------------------------------------------------


class TestAnalyzeGlowupHandler:
    """Handler-level tests for POST /uploads/{id}/glowup/analyze."""

    @pytest.mark.asyncio
    async def test_returns_analysis_on_success(self):
        """Happy path: returns glowup_analysis_id and face data."""
        user_id = str(uuid4())
        upload_id = uuid4()
        claims = _make_claims(user_id)
        glowup_svc = _make_glowup_service(face_shape="oval", symmetry_score=0.85)

        result = await analyze_glowup(
            upload_id=upload_id,
            claims=claims,
            glowup_svc=glowup_svc,
        )

        assert result.face_shape == "oval"
        assert result.symmetry_score == 0.85
        assert len(result.recommendations) == 1

    @pytest.mark.asyncio
    async def test_raises_428_when_no_consent(self):
        """Service raises 428 when face_mod_consent_at IS NULL."""
        from fastapi import HTTPException

        claims = _make_claims()
        glowup_svc = _make_glowup_service(
            raises=HTTPException(
                status_code=428,
                detail={
                    "error": {
                        "code": "FACE_MOD_CONSENT_REQUIRED",
                        "message": "Consent required",
                    }
                },
            )
        )

        with pytest.raises(HTTPException) as exc_info:
            await analyze_glowup(
                upload_id=uuid4(),
                claims=claims,
                glowup_svc=glowup_svc,
            )

        assert exc_info.value.status_code == 428

    @pytest.mark.asyncio
    async def test_raises_404_when_upload_not_found(self):
        """Service raises 404 when upload not found."""
        from fastapi import HTTPException

        claims = _make_claims()
        glowup_svc = _make_glowup_service(
            raises=HTTPException(
                status_code=404,
                detail={"error": {"code": "UPLOAD_NOT_FOUND", "message": "Not found"}},
            )
        )

        with pytest.raises(HTTPException) as exc_info:
            await analyze_glowup(
                upload_id=uuid4(),
                claims=claims,
                glowup_svc=glowup_svc,
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_raises_422_when_face_not_detected(self):
        """Service raises 422 when face_detected is False on the upload."""
        from fastapi import HTTPException

        claims = _make_claims()
        glowup_svc = _make_glowup_service(
            raises=HTTPException(
                status_code=422,
                detail={"error": {"code": "FACE_NOT_DETECTED", "message": "No face"}},
            )
        )

        with pytest.raises(HTTPException) as exc_info:
            await analyze_glowup(
                upload_id=uuid4(),
                claims=claims,
                glowup_svc=glowup_svc,
            )

        assert exc_info.value.status_code == 422


class TestGenerateGlowupHandler:
    """Handler-level tests for POST /uploads/{id}/glowup/generate."""

    @pytest.mark.asyncio
    async def test_duplicate_request_short_circuits_before_entitlement(
        self, monkeypatch
    ):
        user_id = str(uuid4())
        upload_id = uuid4()
        claims = _make_claims(user_id)

        supabase = MockSupabase()
        supabase.set_table_data(
            "users", [{"face_mod_consent_at": "2026-01-01T00:00:00+00:00"}]
        )
        supabase.set_table_data("glowup_analyses", [{"id": "analysis-1"}])
        supabase.set_table_data(
            "uploads",
            [{"id": str(upload_id), "user_id": user_id, "image_url": "raw/key.jpg"}],
        )

        request = MagicMock()
        request.app.state.supabase = supabase
        request.app.state.arq_pool = MagicMock()

        duplicate = GenerateResponse(
            job_id="job-existing",
            status="queued",
            estimated_wait_seconds=0,
            queue_position=0,
        )

        async def fake_run_sync(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        monkeypatch.setattr("app.api.glowup.run_sync", fake_run_sync)
        monkeypatch.setattr(
            "app.api.glowup._check_entitlement",
            AsyncMock(side_effect=AssertionError("entitlement should not run")),
        )
        monkeypatch.setattr(
            "app.api.glowup._check_idempotency", AsyncMock(return_value=duplicate)
        )
        monkeypatch.setattr(
            "app.api.glowup._preflight_checks",
            AsyncMock(side_effect=AssertionError("preflight should not run")),
        )

        result = await generate_glowup(
            upload_id=upload_id,
            body=GenerateRequest(idempotency_key="dup-123"),
            request=request,
            idempotency_key_header=None,
            claims=claims,
            redis_client=AsyncMock(),
            ent_svc=AsyncMock(),
            job_repo=MagicMock(),
            ledger=MagicMock(),
        )

        assert result.job_id == "job-existing"

    @pytest.mark.asyncio
    async def test_enqueue_failure_releases_concurrent_slot(self, monkeypatch):
        user_id = str(uuid4())
        upload_id = uuid4()
        claims = _make_claims(user_id)

        supabase = MockSupabase()
        supabase.set_table_data(
            "users", [{"face_mod_consent_at": "2026-01-01T00:00:00+00:00"}]
        )
        supabase.set_table_data("glowup_analyses", [{"id": "analysis-1"}])
        supabase.set_table_data(
            "uploads",
            [{"id": str(upload_id), "user_id": user_id, "image_url": "raw/key.jpg"}],
        )

        request = MagicMock()
        request.app.state.supabase = supabase
        request.app.state.arq_pool.enqueue_job = AsyncMock(
            side_effect=RuntimeError("queue unavailable")
        )

        redis_client = AsyncMock()
        redis_client.llen.return_value = 0
        job_repo = MagicMock()
        job_repo.create.return_value = {"id": "job-1"}
        job_repo.insert_usage_event.return_value = {"id": "usage-1"}

        async def fake_run_sync(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        monkeypatch.setattr("app.api.glowup.run_sync", fake_run_sync)
        monkeypatch.setattr(
            "app.api.glowup._check_entitlement", AsyncMock(return_value=None)
        )
        monkeypatch.setattr(
            "app.api.glowup._check_idempotency", AsyncMock(return_value=None)
        )
        monkeypatch.setattr(
            "app.api.glowup._preflight_checks",
            AsyncMock(return_value=SimpleNamespace(slug="free", credits_based=False)),
        )

        with pytest.raises(RuntimeError, match="queue unavailable"):
            await generate_glowup(
                upload_id=upload_id,
                body=GenerateRequest(idempotency_key="job-123"),
                request=request,
                idempotency_key_header=None,
                claims=claims,
                redis_client=redis_client,
                ent_svc=AsyncMock(),
                job_repo=job_repo,
                ledger=MagicMock(),
            )

        redis_client.decr.assert_awaited_once_with(f"concurrent:{user_id}")
