"""Tests for the credit refund endpoint (POST /v1/analyses/{job_id}/refund).

Exercises production code in app/api/refund.py.

Pattern: tests call the handler function directly with mock dependencies,
consistent with the rest of the test suite (no HTTP integration tests).
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4


try:
    from app.api.refund import refund_analysis_job, RefundJobResponse
    from app.api.errors import ApiError
    _REFUND_AVAILABLE = True
except (ImportError, AttributeError):
    _REFUND_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _REFUND_AVAILABLE, reason="refund module unavailable"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_claims(user_id: str | None = None) -> dict:
    """Return a minimal UserClaims-like dict."""
    return {"sub": user_id or str(uuid4()), "role": "authenticated"}


def _make_job(
    job_id: str,
    user_id: str,
    status: str = "failed",
    credit_reservation_id: str | None = None,
) -> dict:
    """Return a minimal job dict as returned by get_for_refund."""
    return {
        "id": job_id,
        "user_id": user_id,
        "status": status,
        "credit_reservation_id": credit_reservation_id,
    }


def _make_job_repo(job: dict | None, usage_status: str | None = None) -> MagicMock:
    """Return a mock JobRepository."""
    repo = MagicMock()
    repo.get_for_refund.return_value = job
    repo.get_usage_event_status.return_value = usage_status
    repo.update_usage_event.return_value = []
    return repo


def _make_ledger(balance: int = 5) -> MagicMock:
    """Return a mock CreditLedger."""
    ledger = MagicMock()
    ledger.balance.return_value = balance
    return ledger


async def _call(
    job_id_str: str,
    claims: dict,
    job_repo: MagicMock,
    ledger: MagicMock,
):
    """Invoke the refund_analysis_job handler with run_sync patched."""
    from uuid import UUID

    # run_sync wraps sync calls so they run in a thread executor.
    # For tests we patch it to call the function directly.
    async def fake_run_sync(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with patch("app.api.refund.run_sync", side_effect=fake_run_sync):
        return await refund_analysis_job(
            job_id=UUID(job_id_str),
            claims=claims,
            job_repo=job_repo,
            ledger=ledger,
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRefundEndpoint:
    """Unit tests for refund_analysis_job handler."""

    @pytest.mark.asyncio
    async def test_refund_failed_job_returns_200(self):
        """A failed job with a credit reservation is refunded and returns balance."""
        job_id = str(uuid4())
        user_id = str(uuid4())
        reservation_id = str(uuid4())

        job = _make_job(job_id, user_id, status="failed", credit_reservation_id=reservation_id)
        job_repo = _make_job_repo(job, usage_status="committed")
        ledger = _make_ledger(balance=5)

        claims = _make_claims(user_id)
        result = await _call(job_id, claims, job_repo, ledger)

        assert isinstance(result, RefundJobResponse)
        assert result.refunded is True
        assert result.new_balance == 5
        ledger.refund.assert_called_once()
        job_repo.update_usage_event.assert_called_once_with(job_id, {"status": "refunded"})

    @pytest.mark.asyncio
    async def test_refund_cancelled_job_returns_200(self):
        """A cancelled job can also be refunded via this endpoint."""
        job_id = str(uuid4())
        user_id = str(uuid4())

        job = _make_job(job_id, user_id, status="cancelled")
        job_repo = _make_job_repo(job, usage_status="reserved")
        ledger = _make_ledger(balance=3)

        claims = _make_claims(user_id)
        result = await _call(job_id, claims, job_repo, ledger)

        assert result.refunded is True
        assert result.new_balance == 3

    @pytest.mark.asyncio
    async def test_refund_already_refunded_returns_409(self):
        """A job whose usage_event is already refunded returns 409 already_refunded."""
        job_id = str(uuid4())
        user_id = str(uuid4())

        job = _make_job(job_id, user_id, status="failed")
        job_repo = _make_job_repo(job, usage_status="refunded")
        ledger = _make_ledger()

        claims = _make_claims(user_id)
        with pytest.raises(ApiError) as exc_info:
            await _call(job_id, claims, job_repo, ledger)

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "already_refunded"

    @pytest.mark.asyncio
    async def test_refund_already_released_returns_409(self):
        """A job whose usage_event is released also returns 409 already_refunded."""
        job_id = str(uuid4())
        user_id = str(uuid4())

        job = _make_job(job_id, user_id, status="failed")
        job_repo = _make_job_repo(job, usage_status="released")
        ledger = _make_ledger()

        claims = _make_claims(user_id)
        with pytest.raises(ApiError) as exc_info:
            await _call(job_id, claims, job_repo, ledger)

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "already_refunded"

    @pytest.mark.asyncio
    async def test_refund_not_owner_returns_403(self):
        """A caller who is not the job owner receives 403 forbidden."""
        job_id = str(uuid4())
        owner_id = str(uuid4())
        other_id = str(uuid4())

        job = _make_job(job_id, owner_id, status="failed")
        job_repo = _make_job_repo(job, usage_status=None)
        ledger = _make_ledger()

        claims = _make_claims(other_id)  # different user
        with pytest.raises(ApiError) as exc_info:
            await _call(job_id, claims, job_repo, ledger)

        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "forbidden"

    @pytest.mark.asyncio
    async def test_refund_completed_job_returns_409(self):
        """A completed job returns 409 refund_not_applicable (use /v1/jobs endpoint)."""
        job_id = str(uuid4())
        user_id = str(uuid4())

        job = _make_job(job_id, user_id, status="completed")
        job_repo = _make_job_repo(job, usage_status="committed")
        ledger = _make_ledger()

        claims = _make_claims(user_id)
        with pytest.raises(ApiError) as exc_info:
            await _call(job_id, claims, job_repo, ledger)

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "refund_not_applicable"

    @pytest.mark.asyncio
    async def test_refund_queued_job_returns_409(self):
        """A queued job returns 409 refund_not_applicable."""
        job_id = str(uuid4())
        user_id = str(uuid4())

        job = _make_job(job_id, user_id, status="queued")
        job_repo = _make_job_repo(job, usage_status="reserved")
        ledger = _make_ledger()

        claims = _make_claims(user_id)
        with pytest.raises(ApiError) as exc_info:
            await _call(job_id, claims, job_repo, ledger)

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "refund_not_applicable"

    @pytest.mark.asyncio
    async def test_refund_job_not_found_returns_404(self):
        """A non-existent job returns 404 job_not_found."""
        job_id = str(uuid4())
        user_id = str(uuid4())

        job_repo = _make_job_repo(None)  # job does not exist
        ledger = _make_ledger()

        claims = _make_claims(user_id)
        with pytest.raises(ApiError) as exc_info:
            await _call(job_id, claims, job_repo, ledger)

        assert exc_info.value.status_code == 404
        assert exc_info.value.code == "job_not_found"

    @pytest.mark.asyncio
    async def test_refund_no_reservation_id_skips_ledger(self):
        """A failed job without a credit_reservation_id skips the ledger call."""
        job_id = str(uuid4())
        user_id = str(uuid4())

        job = _make_job(job_id, user_id, status="failed", credit_reservation_id=None)
        job_repo = _make_job_repo(job, usage_status="reserved")
        ledger = _make_ledger(balance=2)

        claims = _make_claims(user_id)
        result = await _call(job_id, claims, job_repo, ledger)

        assert result.refunded is True
        assert result.new_balance == 2
        ledger.refund.assert_not_called()
        ledger.release.assert_not_called()

    @pytest.mark.asyncio
    async def test_refund_falls_back_to_release_on_value_error(self):
        """When ledger.refund raises ValueError, release is tried as fallback."""
        job_id = str(uuid4())
        user_id = str(uuid4())
        reservation_id = str(uuid4())

        job = _make_job(job_id, user_id, status="failed", credit_reservation_id=reservation_id)
        job_repo = _make_job_repo(job, usage_status="reserved")
        ledger = _make_ledger(balance=1)
        ledger.refund.side_effect = ValueError("not committed")

        claims = _make_claims(user_id)
        result = await _call(job_id, claims, job_repo, ledger)

        assert result.refunded is True
        ledger.release.assert_called_once()


class TestRefundResponseModel:
    """Pydantic model tests for RefundJobResponse."""

    def test_response_fields(self):
        resp = RefundJobResponse(refunded=True, new_balance=10)
        assert resp.refunded is True
        assert resp.new_balance == 10

    def test_response_zero_balance(self):
        resp = RefundJobResponse(refunded=True, new_balance=0)
        assert resp.new_balance == 0
