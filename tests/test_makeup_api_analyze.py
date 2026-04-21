"""Tests for POST /uploads/{upload_id}/makeup/analyze handler.

Covers:
  - Happy path: 201 MakeupAnalyzeResponse with correct fields
  - Insert dict uses migration-correct columns (preset_ranking, no upload_id/updated_at)
  - 404 UPLOAD_NOT_FOUND when upload missing or wrong owner
  - 429 RATE_LIMITED from analyze rate limiter with Retry-After header
  - 422 FACE_NOT_DETECTED when analyzer raises AnalysisError
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.entitlement.consent import MAKEUP_CONSENT_VERSION
from app.generation.makeup_analyzer import AnalysisError, MakeupAnalysis


def _make_analysis(mst_bin: int = 3, undertone: str = "warm") -> MakeupAnalysis:
    return MakeupAnalysis(
        mst_bin=mst_bin,
        undertone=undertone,
        region_anchors={"cheek": [100, 200, 50, 50]},
        recommended_preset_ranking=["bold_lip", "natural_glow"],
    )


def _make_request(supabase=None) -> MagicMock:
    req = MagicMock()
    req.app.state.supabase = supabase or MagicMock()
    return req


def _default_analysis_repo(analysis_id: str | None = None) -> MagicMock:
    repo = MagicMock()
    repo.insert.return_value = {
        "id": analysis_id or str(uuid4()),
        "mst_bin": 3,
        "undertone": "warm",
    }
    return repo


@pytest.fixture(autouse=True)
def _patch_run_sync():
    async def _run_sync(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with patch("app.api.makeup.run_sync", side_effect=_run_sync):
        yield


class TestAnalyzeMakeupHappyPath:
    @pytest.mark.asyncio
    async def test_returns_201_with_correct_fields(self):
        from app.api.makeup import analyze_makeup

        user_id = str(uuid4())
        upload_id = uuid4()
        analysis_id = str(uuid4())
        analysis = _make_analysis()
        repo = _default_analysis_repo(analysis_id)

        upload_repo = MagicMock()
        upload_repo.get_by_id_for_owner_check.return_value = {
            "image_url": "https://ex.com/img.jpg"
        }

        with (
            patch(
                "app.api.makeup.check_makeup_analyze_rate_limit",
                new=AsyncMock(return_value=(True, 0)),
            ),
            patch("app.api.makeup.analyze", return_value=analysis),
            patch("app.api.makeup.MakeupAnalysisRepository", return_value=repo),
        ):
            result = await analyze_makeup(
                upload_id=upload_id,
                request=_make_request(),
                claims={"sub": user_id},
                redis_client=AsyncMock(),
                upload_repo=upload_repo,
            )

        assert result.makeup_analysis_id == analysis_id
        assert result.mst_bin == 3
        assert result.undertone == "warm"
        assert result.recommended_presets == ["bold_lip", "natural_glow"]

    @pytest.mark.asyncio
    async def test_insert_dict_uses_migration_columns(self):
        """Insert dict must match migration: preset_ranking, no upload_id/updated_at."""
        from app.api.makeup import analyze_makeup

        user_id = str(uuid4())
        repo = _default_analysis_repo()
        upload_repo = MagicMock()
        upload_repo.get_by_id_for_owner_check.return_value = {
            "image_url": "https://ex.com/img.jpg"
        }

        with (
            patch(
                "app.api.makeup.check_makeup_analyze_rate_limit",
                new=AsyncMock(return_value=(True, 0)),
            ),
            patch("app.api.makeup.analyze", return_value=_make_analysis()),
            patch("app.api.makeup.MakeupAnalysisRepository", return_value=repo),
        ):
            await analyze_makeup(
                upload_id=uuid4(),
                request=_make_request(),
                claims={"sub": user_id},
                redis_client=AsyncMock(),
                upload_repo=upload_repo,
            )

        call_data = repo.insert.call_args[0][0]
        assert "preset_ranking" in call_data
        assert "recommended_preset_ranking" not in call_data
        assert "upload_id" not in call_data
        assert "updated_at" not in call_data
        assert call_data["consent_version"] == MAKEUP_CONSENT_VERSION


class TestAnalyzeMakeupOwnership:
    @pytest.mark.asyncio
    async def test_404_upload_not_found(self):
        from fastapi import HTTPException

        from app.api.makeup import analyze_makeup

        upload_repo = MagicMock()
        upload_repo.get_by_id_for_owner_check.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await analyze_makeup(
                upload_id=uuid4(),
                request=_make_request(),
                claims={"sub": str(uuid4())},
                redis_client=AsyncMock(),
                upload_repo=upload_repo,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail["error"]["code"] == "UPLOAD_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_rate_limit_not_checked_before_ownership(self):
        """Upload ownership must be verified before touching rate-limit counters."""
        from app.api.makeup import analyze_makeup

        upload_repo = MagicMock()
        upload_repo.get_by_id_for_owner_check.return_value = None
        rate_limit_mock = AsyncMock(return_value=(True, 0))

        with (
            patch("app.api.makeup.check_makeup_analyze_rate_limit", rate_limit_mock),
            pytest.raises(Exception),
        ):
            await analyze_makeup(
                upload_id=uuid4(),
                request=_make_request(),
                claims={"sub": str(uuid4())},
                redis_client=AsyncMock(),
                upload_repo=upload_repo,
            )

        rate_limit_mock.assert_not_awaited()


class TestAnalyzeMakeupRateLimit:
    @pytest.mark.asyncio
    async def test_429_when_rate_limited(self):
        from fastapi import HTTPException

        from app.api.makeup import analyze_makeup

        upload_repo = MagicMock()
        upload_repo.get_by_id_for_owner_check.return_value = {
            "image_url": "https://ex.com/img.jpg"
        }

        with (
            patch(
                "app.api.makeup.check_makeup_analyze_rate_limit",
                new=AsyncMock(return_value=(False, 42)),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await analyze_makeup(
                upload_id=uuid4(),
                request=_make_request(),
                claims={"sub": str(uuid4())},
                redis_client=AsyncMock(),
                upload_repo=upload_repo,
            )

        assert exc_info.value.status_code == 429
        assert exc_info.value.detail["error"]["code"] == "RATE_LIMITED"
        assert exc_info.value.detail["error"]["retry_after"] == 42
        assert exc_info.value.headers["Retry-After"] == "42"


class TestAnalyzeMakeupFaceNotDetected:
    @pytest.mark.asyncio
    async def test_422_face_not_detected(self):
        from fastapi import HTTPException

        from app.api.makeup import analyze_makeup

        upload_repo = MagicMock()
        upload_repo.get_by_id_for_owner_check.return_value = {
            "image_url": "https://ex.com/img.jpg"
        }

        with (
            patch(
                "app.api.makeup.check_makeup_analyze_rate_limit",
                new=AsyncMock(return_value=(True, 0)),
            ),
            patch("app.api.makeup.analyze", side_effect=AnalysisError("no_face")),
            pytest.raises(HTTPException) as exc_info,
        ):
            await analyze_makeup(
                upload_id=uuid4(),
                request=_make_request(),
                claims={"sub": str(uuid4())},
                redis_client=AsyncMock(),
                upload_repo=upload_repo,
            )

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["error"]["code"] == "FACE_NOT_DETECTED"
        assert exc_info.value.detail["error"]["detail"]["reason"] == "no_face"

    @pytest.mark.asyncio
    async def test_422_includes_reason_from_error(self):
        from fastapi import HTTPException

        from app.api.makeup import analyze_makeup

        upload_repo = MagicMock()
        upload_repo.get_by_id_for_owner_check.return_value = {
            "image_url": "https://ex.com/img.jpg"
        }

        with (
            patch(
                "app.api.makeup.check_makeup_analyze_rate_limit",
                new=AsyncMock(return_value=(True, 0)),
            ),
            patch("app.api.makeup.analyze", side_effect=AnalysisError("low_quality")),
            pytest.raises(HTTPException) as exc_info,
        ):
            await analyze_makeup(
                upload_id=uuid4(),
                request=_make_request(),
                claims={"sub": str(uuid4())},
                redis_client=AsyncMock(),
                upload_repo=upload_repo,
            )

        assert exc_info.value.detail["error"]["detail"]["reason"] == "low_quality"
