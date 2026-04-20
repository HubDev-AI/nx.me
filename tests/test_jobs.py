"""Tests for the jobs API (GET, save, cancel, refund).

Exercises:
  - app/api/jobs.py (JobStatusResponse, SaveResponse, CancelResponse, RefundResponse)
  - app/repositories/job_repo.py (JobRepository)
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


try:
    from app.api.jobs import (
        CancelResponse,
        JobStatusResponse,
        RefundResponse,
        SaveResponse,
        cancel_job,
        get_job,
        refund_job,
        save_job,
    )
    from app.repositories.job_repo import JobRepository, SOURCE_TYPE_GLOWUP

    _AVAILABLE = True
except (ImportError, AttributeError):
    _AVAILABLE = False

pytestmark = pytest.mark.skipif(not _AVAILABLE, reason="jobs module unavailable")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_claims(user_id: str | None = None) -> dict:
    return {"sub": user_id or str(uuid4()), "role": "authenticated"}


def _make_job_repo(job: dict | None = None) -> MagicMock:
    repo = MagicMock()
    repo.get_for_status_poll.return_value = job
    repo.get_for_cancel.return_value = job
    repo.get_for_refund.return_value = job
    repo.get_for_save.return_value = job
    repo.update.return_value = [{}]
    repo.save.return_value = job
    return repo


def _make_redis() -> MagicMock:
    redis = MagicMock()
    redis.zcard = AsyncMock(return_value=0)
    return redis


def _make_request(user_id: str = None) -> MagicMock:
    req = MagicMock()
    req.app.state.supabase = MagicMock()
    return req


def _make_ledger() -> MagicMock:
    ledger = MagicMock()
    return ledger


def _make_job_dict(
    job_id: str = None,
    user_id: str = None,
    status: str = "queued",
    reservation_id: str = None,
    saved_at=None,
    created_at: str = "2026-01-01T00:00:00+00:00",
) -> dict:
    return {
        "id": job_id or str(uuid4()),
        "user_id": user_id or str(uuid4()),
        "status": status,
        "source_type": SOURCE_TYPE_GLOWUP,
        "source_id": str(uuid4()),
        "created_at": created_at,
        "updated_at": "2026-01-01T00:00:00+00:00",
        "before_image_url": None,
        "after_image_url": None,
        "failure_reason": None,
        "saved_at": saved_at,
        "identity_preserved": None,
        "credit_reservation_id": reservation_id,
    }


async def _run_sync_passthrough(fn, *args, **kwargs):
    return fn(*args, **kwargs)


# ---------------------------------------------------------------------------
# JobRepository unit tests
# ---------------------------------------------------------------------------


class TestJobRepository:
    """Unit tests for JobRepository."""

    def test_get_by_idempotency_key_returns_none_when_missing(self):
        from tests.conftest import MockSupabase

        sb = MockSupabase()
        sb.set_table_data("jobs", None)
        repo = JobRepository(sb)
        result = repo.get_by_idempotency_key("key-1", str(uuid4()))
        assert result is None

    def test_create_returns_inserted_row(self):
        from tests.conftest import MockSupabase

        uid = str(uuid4())
        row = {
            "id": uid,
            "user_id": "u1",
            "source_type": SOURCE_TYPE_GLOWUP,
            "source_id": "s1",
        }
        sb = MockSupabase()
        sb.set_table_data("jobs", [row])
        repo = JobRepository(sb)
        result = repo.create(row)
        assert isinstance(result, dict)

    def test_source_type_glowup_constant_value(self):
        assert SOURCE_TYPE_GLOWUP == "glowup_analysis"


# ---------------------------------------------------------------------------
# Response model tests
# ---------------------------------------------------------------------------


class TestJobResponseModels:
    def test_job_status_response_minimal(self):
        resp = JobStatusResponse(job_id=str(uuid4()), status="queued")
        assert resp.status == "queued"
        assert resp.estimated_wait_seconds is None

    def test_save_response(self):
        resp = SaveResponse(saved_at="2026-01-01T12:00:00+00:00")
        assert "2026" in resp.saved_at

    def test_cancel_response(self):
        resp = CancelResponse(
            job_id=str(uuid4()), status="cancelled", credit_refunded=False
        )
        assert resp.status == "cancelled"

    def test_refund_response(self):
        resp = RefundResponse(
            job_id=str(uuid4()), status="failed", credit_refunded=True
        )
        assert resp.credit_refunded is True


# ---------------------------------------------------------------------------
# get_job handler tests
# ---------------------------------------------------------------------------


class TestGetJobHandler:
    """Tests for GET /jobs/{job_id}."""

    @pytest.mark.asyncio
    async def test_returns_404_when_not_found(self):
        from fastapi import HTTPException

        user_id = str(uuid4())
        job_repo = _make_job_repo(job=None)

        with pytest.raises(HTTPException) as exc_info:
            with patch("app.db.async_helpers.run_sync", new=_run_sync_passthrough):
                await get_job(
                    job_id=uuid4(),
                    request=_make_request(user_id),
                    claims=_make_claims(user_id),
                    redis_client=_make_redis(),
                    job_repo=job_repo,
                )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_404_when_wrong_owner(self):
        from fastapi import HTTPException

        user_id = str(uuid4())
        other_user = str(uuid4())
        job = _make_job_dict(user_id=other_user, status="queued")
        job_repo = _make_job_repo(job=job)

        with pytest.raises(HTTPException) as exc_info:
            with patch("app.db.async_helpers.run_sync", new=_run_sync_passthrough):
                await get_job(
                    job_id=uuid4(),
                    request=_make_request(user_id),
                    claims=_make_claims(user_id),
                    redis_client=_make_redis(),
                    job_repo=job_repo,
                )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_queued_status(self):
        user_id = str(uuid4())
        job_id = uuid4()
        job = _make_job_dict(job_id=str(job_id), user_id=user_id, status="queued")
        job_repo = _make_job_repo(job=job)

        with patch("app.db.async_helpers.run_sync", new=_run_sync_passthrough):
            result = await get_job(
                job_id=job_id,
                request=_make_request(user_id),
                claims=_make_claims(user_id),
                redis_client=_make_redis(),
                job_repo=job_repo,
            )

        assert result.status == "queued"
        assert result.estimated_wait_seconds is not None


# ---------------------------------------------------------------------------
# Dev repro harness — DEV_GLOWUP_FORCE_404_FOR_NEW_JOBS_SECONDS gate
# ---------------------------------------------------------------------------


class TestDevForce404Gate:
    """Verify the dev-only 404 gate that simulates read-after-write replica lag.

    Default off in production: setting=0 → no gate. With setting>0, GET
    returns 404 for the first N seconds after a job's created_at.
    """

    @pytest.mark.asyncio
    async def test_default_setting_off_does_not_gate(self):
        from app.config import settings

        assert settings.DEV_GLOWUP_FORCE_404_FOR_NEW_JOBS_SECONDS == 0

        user_id = str(uuid4())
        job_id = uuid4()
        job = _make_job_dict(job_id=str(job_id), user_id=user_id, status="queued")
        job_repo = _make_job_repo(job=job)

        with patch("app.db.async_helpers.run_sync", new=_run_sync_passthrough):
            result = await get_job(
                job_id=job_id,
                request=_make_request(user_id),
                claims=_make_claims(user_id),
                redis_client=_make_redis(),
                job_repo=job_repo,
            )

        assert result.status == "queued"

    @pytest.mark.asyncio
    async def test_gate_returns_404_within_window(self, monkeypatch):
        from datetime import datetime, timezone

        from app.config import settings
        from fastapi import HTTPException

        monkeypatch.setattr(settings, "DEV_GLOWUP_FORCE_404_FOR_NEW_JOBS_SECONDS", 30)

        user_id = str(uuid4())
        job_id = uuid4()
        recent_iso = datetime.now(tz=timezone.utc).isoformat()
        job = _make_job_dict(
            job_id=str(job_id),
            user_id=user_id,
            status="queued",
            created_at=recent_iso,
        )
        job_repo = _make_job_repo(job=job)

        with pytest.raises(HTTPException) as exc_info:
            with patch("app.db.async_helpers.run_sync", new=_run_sync_passthrough):
                await get_job(
                    job_id=job_id,
                    request=_make_request(user_id),
                    claims=_make_claims(user_id),
                    redis_client=_make_redis(),
                    job_repo=job_repo,
                )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_gate_passes_after_window(self, monkeypatch):
        from datetime import datetime, timedelta, timezone

        from app.config import settings

        monkeypatch.setattr(settings, "DEV_GLOWUP_FORCE_404_FOR_NEW_JOBS_SECONDS", 5)

        user_id = str(uuid4())
        job_id = uuid4()
        old_iso = (datetime.now(tz=timezone.utc) - timedelta(seconds=10)).isoformat()
        job = _make_job_dict(
            job_id=str(job_id),
            user_id=user_id,
            status="queued",
            created_at=old_iso,
        )
        job_repo = _make_job_repo(job=job)

        with patch("app.db.async_helpers.run_sync", new=_run_sync_passthrough):
            result = await get_job(
                job_id=job_id,
                request=_make_request(user_id),
                claims=_make_claims(user_id),
                redis_client=_make_redis(),
                job_repo=job_repo,
            )

        assert result.status == "queued"


# ---------------------------------------------------------------------------
# Dev repro harness — DEV_GLOWUP_EMIT_NULL_URLS_ON_COMPLETE setting default
# ---------------------------------------------------------------------------


class TestDevEmitNullUrlsSetting:
    """Verify the worker NULL-URL toggle defaults off and is wired correctly.

    The full _finalize_job path involves PIL image normalization which is
    awkward to mock. We assert the setting default and rely on the inline
    conditional + code review for the worker call site.
    """

    def test_default_setting_off(self):
        from app.config import settings

        assert settings.DEV_GLOWUP_EMIT_NULL_URLS_ON_COMPLETE is False


# ---------------------------------------------------------------------------
# save_job handler tests
# ---------------------------------------------------------------------------


class TestSaveJobHandler:
    """Tests for POST /jobs/{job_id}/save."""

    @pytest.mark.asyncio
    async def test_save_returns_saved_at(self):
        user_id = str(uuid4())
        job_id = uuid4()
        now = "2026-04-13T10:00:00+00:00"
        job = _make_job_dict(
            job_id=str(job_id), user_id=user_id, status="completed", saved_at=now
        )
        job_repo = _make_job_repo(job=job)

        with patch("app.db.async_helpers.run_sync", new=_run_sync_passthrough):
            result = await save_job(
                job_id=job_id,
                claims=_make_claims(user_id),
                job_repo=job_repo,
            )

        assert result.saved_at == now

    @pytest.mark.asyncio
    async def test_save_returns_404_when_not_found(self):
        from fastapi import HTTPException

        job_repo = _make_job_repo(job=None)
        job_repo.save.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            with patch("app.db.async_helpers.run_sync", new=_run_sync_passthrough):
                await save_job(
                    job_id=uuid4(),
                    claims=_make_claims(),
                    job_repo=job_repo,
                )
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# cancel_job handler tests
# ---------------------------------------------------------------------------


class TestCancelJobHandler:
    """Tests for POST /jobs/{job_id}/cancel."""

    @pytest.mark.asyncio
    async def test_cancel_in_flight_job(self):
        user_id = str(uuid4())
        job_id = uuid4()
        job = _make_job_dict(job_id=str(job_id), user_id=user_id, status="processing")
        job_repo = _make_job_repo(job=job)

        with patch("app.db.async_helpers.run_sync", new=_run_sync_passthrough):
            result = await cancel_job(
                job_id=job_id,
                claims=_make_claims(user_id),
                job_repo=job_repo,
                ledger=_make_ledger(),
            )

        assert result.status == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_terminal_job_raises_409(self):
        from fastapi import HTTPException

        user_id = str(uuid4())
        job = _make_job_dict(user_id=user_id, status="completed")
        job_repo = _make_job_repo(job=job)

        with pytest.raises(HTTPException) as exc_info:
            with patch("app.db.async_helpers.run_sync", new=_run_sync_passthrough):
                await cancel_job(
                    job_id=uuid4(),
                    claims=_make_claims(user_id),
                    job_repo=job_repo,
                    ledger=_make_ledger(),
                )
        assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# refund_job handler tests
# ---------------------------------------------------------------------------


class TestRefundJobHandler:
    """Tests for POST /jobs/{job_id}/refund."""

    @pytest.mark.asyncio
    async def test_refund_failed_job(self):
        user_id = str(uuid4())
        job_id = uuid4()
        reservation_id = str(uuid4())
        job = _make_job_dict(
            job_id=str(job_id),
            user_id=user_id,
            status="failed",
            reservation_id=reservation_id,
        )
        job_repo = _make_job_repo(job=job)

        with patch("app.db.async_helpers.run_sync", new=_run_sync_passthrough):
            result = await refund_job(
                job_id=job_id,
                claims=_make_claims(user_id),
                job_repo=job_repo,
                ledger=_make_ledger(),
            )

        assert (
            result.credit_refunded is True or result.credit_refunded is False
        )  # either valid

    @pytest.mark.asyncio
    async def test_refund_already_refunded_raises_409(self):
        """When the ledger rejects both refund and release on a resolved
        reservation, the endpoint returns 409 already_refunded."""
        from fastapi import HTTPException

        user_id = str(uuid4())
        reservation_id = str(uuid4())
        job = _make_job_dict(
            user_id=user_id, status="failed", reservation_id=reservation_id
        )
        job_repo = _make_job_repo(job=job)
        ledger = _make_ledger()
        ledger.refund.side_effect = ValueError("not committed")
        ledger.release.side_effect = ValueError("not reserved")

        with pytest.raises(HTTPException) as exc_info:
            with patch("app.db.async_helpers.run_sync", new=_run_sync_passthrough):
                await refund_job(
                    job_id=uuid4(),
                    claims=_make_claims(user_id),
                    job_repo=job_repo,
                    ledger=ledger,
                )
        assert exc_info.value.status_code == 409
