"""Tests for POST /uploads/{upload_id}/makeup/generate handler.

Covers:
  - Happy path: 202 MakeupGenerateResponse
  - Idempotency-Key: header wins over body; same hash → 202 replay; diff hash → 409
  - Ownership: 404 UPLOAD_NOT_FOUND
  - Preset validation: 400 PRESET_INVALID / PRESET_DEPRECATED / PRESET_BLOCKED_FOR_BIN
  - Missing idempotency key: 400 MISSING_IDEMPOTENCY_KEY
  - Fair-use cap: 429 RATE_LIMITED
  - Enqueue failure triggers fair_use_decr (and does NOT happen in race path)
  - Concurrent-INSERT race paths: hash match → 202 replay; hash mismatch → 409; winner
    not visible → 409 IDEMPOTENT_RACE
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.generation.makeup_analyzer import MakeupAnalysis
from app.generation.models import JobStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _analysis_row(user_id: str, mst_bin: int = 3, days_ago: int = 0) -> dict:
    created_at = datetime.now(tz=timezone.utc)
    return {
        "id": str(uuid4()),
        "user_id": user_id,
        "mst_bin": mst_bin,
        "undertone": "warm",
        "region_anchors": {"cheek": [100, 200, 50, 50]},
        "consent_version": "1.0",
        "created_at": created_at.isoformat(),
    }


def _fresh_analysis() -> MakeupAnalysis:
    return MakeupAnalysis(
        mst_bin=3,
        undertone="warm",
        region_anchors={"cheek": [100, 200, 50, 50]},
        recommended_preset_ranking=["bold_lip"],
    )


def _make_preset(
    deprecated: bool = False,
    mst_blocklist: list[int] | None = None,
    intensities: list[str] | None = None,
) -> MagicMock:
    p = MagicMock()
    p.deprecated = deprecated
    p.mst_bin_blocklist = mst_blocklist or []
    p.supported_intensities = intensities or ["light", "medium", "bold"]
    return p


def _make_request(arq_pool=None) -> MagicMock:
    req = MagicMock()
    req.app.state.supabase = MagicMock()
    pool = arq_pool or MagicMock()
    if not hasattr(pool, "enqueue_job") or not isinstance(pool.enqueue_job, AsyncMock):
        pool.enqueue_job = AsyncMock()
    req.app.state.arq_pool = pool
    return req


def _make_job_repo(
    existing_job: dict | None = None,
    inserted_job: str | dict | None = "auto",
) -> MagicMock:
    job_repo = MagicMock()
    job_repo.get_makeup_job_by_idempotency_key.return_value = existing_job
    if inserted_job == "auto":
        job_repo.pre_record_makeup_job.return_value = {
            "id": str(uuid4()),
            "status": JobStatus.QUEUED,
        }
    else:
        job_repo.pre_record_makeup_job.return_value = inserted_job
    job_repo.update = MagicMock(return_value=None)
    return job_repo


def _make_upload_repo(found: bool = True) -> MagicMock:
    repo = MagicMock()
    repo.get_by_id_for_owner_check.return_value = (
        {"image_url": "https://ex.com/img.jpg"} if found else None
    )
    return repo


def _make_analysis_repo(row: dict | None = None) -> MagicMock:
    repo = MagicMock()
    repo.get_latest_for_user.return_value = row
    repo.insert.return_value = row or _analysis_row("placeholder")
    return repo


@pytest.fixture(autouse=True)
def _patch_run_sync():
    async def _run_sync(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with patch("app.api.makeup.run_sync", side_effect=_run_sync):
        yield


def _body(
    preset: str = "bold_lip",
    intensity: str = "medium",
    idem_key: str | None = "test-key",
):
    from app.schemas.makeup import MakeupGenerateRequest

    return MakeupGenerateRequest(
        preset_slug=preset,
        intensity=intensity,
        idempotency_key=idem_key,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestGenerateMakeupHappyPath:
    @pytest.mark.asyncio
    async def test_returns_202_with_job_id_and_poll_url(self):
        from app.api.makeup import generate_makeup

        user_id = str(uuid4())
        upload_id = uuid4()
        row = _analysis_row(user_id)
        job_repo = _make_job_repo()

        with (
            patch("app.api.makeup.analyzer_stale", return_value=False),
            patch("app.api.makeup.get_preset", return_value=_make_preset()),
            patch(
                "app.api.makeup.fair_use_incr", new=AsyncMock(return_value=(True, 1))
            ),
            patch(
                "app.api.makeup.MakeupAnalysisRepository",
                return_value=_make_analysis_repo(row),
            ),
        ):
            result = await generate_makeup(
                upload_id=upload_id,
                body=_body(),
                request=_make_request(),
                idempotency_key_header=None,
                claims={"sub": user_id},
                redis_client=AsyncMock(),
                job_repo=job_repo,
                upload_repo=_make_upload_repo(),
            )

        assert result.status == JobStatus.QUEUED
        assert result.poll_url.startswith("/v1/jobs/")
        assert result.job_id is not None

    @pytest.mark.asyncio
    async def test_header_key_wins_over_body_key(self):
        from app.api.makeup import generate_makeup

        user_id = str(uuid4())
        upload_id = uuid4()
        row = _analysis_row(user_id)
        job_repo = _make_job_repo()

        with (
            patch("app.api.makeup.analyzer_stale", return_value=False),
            patch("app.api.makeup.get_preset", return_value=_make_preset()),
            patch(
                "app.api.makeup.fair_use_incr", new=AsyncMock(return_value=(True, 1))
            ),
            patch(
                "app.api.makeup.MakeupAnalysisRepository",
                return_value=_make_analysis_repo(row),
            ),
        ):
            await generate_makeup(
                upload_id=upload_id,
                body=_body(idem_key="body-key"),
                request=_make_request(),
                idempotency_key_header="header-key",
                claims={"sub": user_id},
                redis_client=AsyncMock(),
                job_repo=job_repo,
                upload_repo=_make_upload_repo(),
            )

        called_key = job_repo.get_makeup_job_by_idempotency_key.call_args[0][0]
        assert "header-key" in called_key
        assert "body-key" not in called_key


# ---------------------------------------------------------------------------
# 400 validation errors
# ---------------------------------------------------------------------------


class TestGenerateMakeup400Errors:
    @pytest.mark.asyncio
    async def test_400_missing_idempotency_key(self):
        from fastapi import HTTPException

        from app.api.makeup import generate_makeup

        with pytest.raises(HTTPException) as exc_info:
            await generate_makeup(
                upload_id=uuid4(),
                body=_body(idem_key=None),
                request=_make_request(),
                idempotency_key_header=None,
                claims={"sub": str(uuid4())},
                redis_client=AsyncMock(),
                job_repo=_make_job_repo(),
                upload_repo=_make_upload_repo(),
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["error"]["code"] == "MISSING_IDEMPOTENCY_KEY"

    @pytest.mark.asyncio
    async def test_400_preset_invalid(self):
        from fastapi import HTTPException

        from app.api.makeup import generate_makeup

        user_id = str(uuid4())
        row = _analysis_row(user_id)

        with (
            patch("app.api.makeup.analyzer_stale", return_value=False),
            patch("app.api.makeup.get_preset", return_value=None),
            patch(
                "app.api.makeup.MakeupAnalysisRepository",
                return_value=_make_analysis_repo(row),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await generate_makeup(
                upload_id=uuid4(),
                body=_body(preset="ghost_preset"),
                request=_make_request(),
                idempotency_key_header=None,
                claims={"sub": user_id},
                redis_client=AsyncMock(),
                job_repo=_make_job_repo(),
                upload_repo=_make_upload_repo(),
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["error"]["code"] == "PRESET_INVALID"

    @pytest.mark.asyncio
    async def test_400_preset_deprecated(self):
        from fastapi import HTTPException

        from app.api.makeup import generate_makeup

        user_id = str(uuid4())
        row = _analysis_row(user_id)

        with (
            patch("app.api.makeup.analyzer_stale", return_value=False),
            patch(
                "app.api.makeup.get_preset", return_value=_make_preset(deprecated=True)
            ),
            patch(
                "app.api.makeup.MakeupAnalysisRepository",
                return_value=_make_analysis_repo(row),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await generate_makeup(
                upload_id=uuid4(),
                body=_body(),
                request=_make_request(),
                idempotency_key_header=None,
                claims={"sub": user_id},
                redis_client=AsyncMock(),
                job_repo=_make_job_repo(),
                upload_repo=_make_upload_repo(),
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["error"]["code"] == "PRESET_DEPRECATED"

    @pytest.mark.asyncio
    async def test_400_preset_blocked_for_mst_bin(self):
        from fastapi import HTTPException

        from app.api.makeup import generate_makeup

        user_id = str(uuid4())
        row = _analysis_row(user_id, mst_bin=3)

        with (
            patch("app.api.makeup.analyzer_stale", return_value=False),
            patch(
                "app.api.makeup.get_preset",
                return_value=_make_preset(mst_blocklist=[3]),
            ),
            patch(
                "app.api.makeup.MakeupAnalysisRepository",
                return_value=_make_analysis_repo(row),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await generate_makeup(
                upload_id=uuid4(),
                body=_body(),
                request=_make_request(),
                idempotency_key_header=None,
                claims={"sub": user_id},
                redis_client=AsyncMock(),
                job_repo=_make_job_repo(),
                upload_repo=_make_upload_repo(),
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["error"]["code"] == "PRESET_BLOCKED_FOR_BIN"

    @pytest.mark.asyncio
    async def test_400_intensity_not_supported(self):
        from fastapi import HTTPException

        from app.api.makeup import generate_makeup

        user_id = str(uuid4())
        row = _analysis_row(user_id)

        with (
            patch("app.api.makeup.analyzer_stale", return_value=False),
            patch(
                "app.api.makeup.get_preset",
                return_value=_make_preset(intensities=["light", "medium"]),
            ),
            patch(
                "app.api.makeup.MakeupAnalysisRepository",
                return_value=_make_analysis_repo(row),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await generate_makeup(
                upload_id=uuid4(),
                body=_body(intensity="ultra"),
                request=_make_request(),
                idempotency_key_header=None,
                claims={"sub": user_id},
                redis_client=AsyncMock(),
                job_repo=_make_job_repo(),
                upload_repo=_make_upload_repo(),
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["error"]["code"] == "PRESET_INVALID"


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------


class TestGenerateMakeupOwnership:
    @pytest.mark.asyncio
    async def test_404_upload_not_found(self):
        from fastapi import HTTPException

        from app.api.makeup import generate_makeup

        with pytest.raises(HTTPException) as exc_info:
            await generate_makeup(
                upload_id=uuid4(),
                body=_body(),
                request=_make_request(),
                idempotency_key_header=None,
                claims={"sub": str(uuid4())},
                redis_client=AsyncMock(),
                job_repo=_make_job_repo(),
                upload_repo=_make_upload_repo(found=False),
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail["error"]["code"] == "UPLOAD_NOT_FOUND"


# ---------------------------------------------------------------------------
# Idempotency replay and conflict
# ---------------------------------------------------------------------------


class TestGenerateMakeupIdempotency:
    @pytest.mark.asyncio
    async def test_202_replay_same_body_hash(self):
        """Pre-check SELECT finds existing job with matching hash → 202 replay."""
        from app.api.makeup import _body_hash, generate_makeup

        user_id = str(uuid4())
        upload_id = uuid4()
        row = _analysis_row(user_id)
        expected_hash = _body_hash("bold_lip", "medium", str(upload_id))
        existing = {
            "id": str(uuid4()),
            "status": "processing",
            "idempotency_key_body_hash": expected_hash,
        }
        job_repo = _make_job_repo(existing_job=existing)

        with (
            patch("app.api.makeup.analyzer_stale", return_value=False),
            patch("app.api.makeup.get_preset", return_value=_make_preset()),
            patch(
                "app.api.makeup.MakeupAnalysisRepository",
                return_value=_make_analysis_repo(row),
            ),
        ):
            result = await generate_makeup(
                upload_id=upload_id,
                body=_body(),
                request=_make_request(),
                idempotency_key_header=None,
                claims={"sub": user_id},
                redis_client=AsyncMock(),
                job_repo=job_repo,
                upload_repo=_make_upload_repo(),
            )

        assert result.job_id == existing["id"]
        assert result.status == "processing"
        assert job_repo.pre_record_makeup_job.call_count == 0

    @pytest.mark.asyncio
    async def test_409_conflict_different_body_hash(self):
        """Pre-check SELECT finds existing job with different hash → 409."""
        from fastapi import HTTPException

        from app.api.makeup import generate_makeup

        user_id = str(uuid4())
        upload_id = uuid4()
        row = _analysis_row(user_id)
        existing = {
            "id": str(uuid4()),
            "status": "queued",
            "idempotency_key_body_hash": "different_hash_entirely",
        }
        job_repo = _make_job_repo(existing_job=existing)

        with (
            patch("app.api.makeup.analyzer_stale", return_value=False),
            patch("app.api.makeup.get_preset", return_value=_make_preset()),
            patch(
                "app.api.makeup.MakeupAnalysisRepository",
                return_value=_make_analysis_repo(row),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await generate_makeup(
                upload_id=upload_id,
                body=_body(),
                request=_make_request(),
                idempotency_key_header=None,
                claims={"sub": user_id},
                redis_client=AsyncMock(),
                job_repo=job_repo,
                upload_repo=_make_upload_repo(),
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"


# ---------------------------------------------------------------------------
# Fair-use cap
# ---------------------------------------------------------------------------


class TestGenerateMakeupFairUseCap:
    @pytest.mark.asyncio
    async def test_429_when_cap_exceeded(self):
        from fastapi import HTTPException

        from app.api.makeup import generate_makeup

        user_id = str(uuid4())
        row = _analysis_row(user_id)
        redis_client = AsyncMock()
        redis_client.ttl = AsyncMock(return_value=3600)

        with (
            patch("app.api.makeup.analyzer_stale", return_value=False),
            patch("app.api.makeup.get_preset", return_value=_make_preset()),
            patch(
                "app.api.makeup.fair_use_incr", new=AsyncMock(return_value=(False, 0))
            ),
            patch(
                "app.api.makeup.MakeupAnalysisRepository",
                return_value=_make_analysis_repo(row),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await generate_makeup(
                upload_id=uuid4(),
                body=_body(),
                request=_make_request(),
                idempotency_key_header=None,
                claims={"sub": user_id},
                redis_client=redis_client,
                job_repo=_make_job_repo(),
                upload_repo=_make_upload_repo(),
            )

        assert exc_info.value.status_code == 429
        assert exc_info.value.detail["error"]["code"] == "RATE_LIMITED"

    @pytest.mark.asyncio
    async def test_enqueue_failure_calls_fair_use_decr(self):
        """ARQ enqueue failure must roll back the fair-use charge."""
        from app.api.makeup import generate_makeup

        user_id = str(uuid4())
        row = _analysis_row(user_id)
        arq_pool = MagicMock()
        arq_pool.enqueue_job = AsyncMock(side_effect=RuntimeError("pool unavailable"))

        decr_mock = AsyncMock(return_value=True)

        with (
            patch("app.api.makeup.analyzer_stale", return_value=False),
            patch("app.api.makeup.get_preset", return_value=_make_preset()),
            patch(
                "app.api.makeup.fair_use_incr", new=AsyncMock(return_value=(True, 1))
            ),
            patch(
                "app.api.rate_limiters.makeup_fair_use.fair_use_decr",
                decr_mock,
            ),
            patch(
                "app.api.makeup.MakeupAnalysisRepository",
                return_value=_make_analysis_repo(row),
            ),
            pytest.raises(RuntimeError),
        ):
            await generate_makeup(
                upload_id=uuid4(),
                body=_body(),
                request=_make_request(arq_pool=arq_pool),
                idempotency_key_header=None,
                claims={"sub": user_id},
                redis_client=AsyncMock(),
                job_repo=_make_job_repo(),
                upload_repo=_make_upload_repo(),
            )

        decr_mock.assert_awaited_once()


# ---------------------------------------------------------------------------
# Concurrent INSERT race paths
# ---------------------------------------------------------------------------


class TestGenerateMakeupConcurrentRace:
    @pytest.mark.asyncio
    async def test_race_same_hash_returns_202_no_decrement(self):
        """INSERT returns None (race loser), winner has same hash → 202.
        fair_use_decr must NOT be called — incr saw already_charged."""
        from app.api.makeup import _body_hash, generate_makeup

        user_id = str(uuid4())
        upload_id = uuid4()
        row = _analysis_row(user_id)
        expected_hash = _body_hash("bold_lip", "medium", str(upload_id))
        winner = {
            "id": str(uuid4()),
            "status": "queued",
            "idempotency_key_body_hash": expected_hash,
        }

        job_repo = MagicMock()
        # First call (pre-check) returns None; second call (race SELECT) returns winner.
        job_repo.get_makeup_job_by_idempotency_key.side_effect = [None, winner]
        job_repo.pre_record_makeup_job.return_value = None  # race loser

        decr_mock = AsyncMock(return_value=True)

        with (
            patch("app.api.makeup.analyzer_stale", return_value=False),
            patch("app.api.makeup.get_preset", return_value=_make_preset()),
            patch(
                "app.api.makeup.fair_use_incr", new=AsyncMock(return_value=(True, 1))
            ),
            patch(
                "app.api.rate_limiters.makeup_fair_use.fair_use_decr",
                decr_mock,
            ),
            patch(
                "app.api.makeup.MakeupAnalysisRepository",
                return_value=_make_analysis_repo(row),
            ),
        ):
            result = await generate_makeup(
                upload_id=upload_id,
                body=_body(),
                request=_make_request(),
                idempotency_key_header=None,
                claims={"sub": user_id},
                redis_client=AsyncMock(),
                job_repo=job_repo,
                upload_repo=_make_upload_repo(),
            )

        assert result.job_id == winner["id"]
        assert result.status == "queued"
        decr_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_race_winner_not_visible_returns_409_idempotent_race(self):
        """INSERT None, post-race SELECT also None → 409 IDEMPOTENT_RACE."""
        from fastapi import HTTPException

        from app.api.makeup import generate_makeup

        user_id = str(uuid4())
        row = _analysis_row(user_id)

        job_repo = MagicMock()
        job_repo.get_makeup_job_by_idempotency_key.side_effect = [None, None]
        job_repo.pre_record_makeup_job.return_value = None

        with (
            patch("app.api.makeup.analyzer_stale", return_value=False),
            patch("app.api.makeup.get_preset", return_value=_make_preset()),
            patch(
                "app.api.makeup.fair_use_incr", new=AsyncMock(return_value=(True, 1))
            ),
            patch(
                "app.api.makeup.MakeupAnalysisRepository",
                return_value=_make_analysis_repo(row),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await generate_makeup(
                upload_id=uuid4(),
                body=_body(),
                request=_make_request(),
                idempotency_key_header=None,
                claims={"sub": user_id},
                redis_client=AsyncMock(),
                job_repo=job_repo,
                upload_repo=_make_upload_repo(),
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["error"]["code"] == "IDEMPOTENT_RACE"
        assert exc_info.value.headers["Retry-After"] == "1"

    @pytest.mark.asyncio
    async def test_race_different_hash_returns_409_conflict(self):
        """INSERT None, winner has different hash → 409 IDEMPOTENCY_KEY_CONFLICT."""
        from fastapi import HTTPException

        from app.api.makeup import generate_makeup

        user_id = str(uuid4())
        row = _analysis_row(user_id)
        winner = {
            "id": str(uuid4()),
            "status": "queued",
            "idempotency_key_body_hash": "completely_different_hash",
        }

        job_repo = MagicMock()
        job_repo.get_makeup_job_by_idempotency_key.side_effect = [None, winner]
        job_repo.pre_record_makeup_job.return_value = None

        with (
            patch("app.api.makeup.analyzer_stale", return_value=False),
            patch("app.api.makeup.get_preset", return_value=_make_preset()),
            patch(
                "app.api.makeup.fair_use_incr", new=AsyncMock(return_value=(True, 1))
            ),
            patch(
                "app.api.makeup.MakeupAnalysisRepository",
                return_value=_make_analysis_repo(row),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await generate_makeup(
                upload_id=uuid4(),
                body=_body(),
                request=_make_request(),
                idempotency_key_header=None,
                claims={"sub": user_id},
                redis_client=AsyncMock(),
                job_repo=job_repo,
                upload_repo=_make_upload_repo(),
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"
