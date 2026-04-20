"""Tests for worker auto-refund on non-user-caused job failures.

Verifies that _fail_job:
  - calls ledger.release() for non-user-caused in-flight failures
    (PROVIDER_ERROR, GENERATION_TIMEOUT on reserved reservations)
  - calls ledger.refund() for non-user-caused finalizing failures
    (committed reservations that need reversal)
  - does NOT release/refund for user-caused failures (NSFW, IDENTITY) —
    the provider already ran a paid inference, so the credit stays
    consumed. Reserved credits are committed in that path.
  - does NOT settle credits for completed jobs (credit already fully
    consumed)
  - handles credit settle failure gracefully (still marks job failed)

Idempotency is enforced by the ledger RPCs themselves (credit_release,
credit_refund, credit_commit all use UPDATE ... WHERE status = X
RETURNING *), so the worker no longer writes a secondary usage_events
row.

Pattern: unit tests calling _fail_job directly with MagicMock
dependencies, consistent with test_refund.py and test_face_errors.py.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4


try:
    from app.generation.worker import _fail_job
    from app.generation.models import (
        FAILURE_PROVIDER,
        FAILURE_TIMEOUT,
        FAILURE_NSFW,
        FAILURE_IDENTITY,
        NON_USER_FAILURE_REASONS,
        JobStatus,
    )

    _WORKER_AVAILABLE = True
except (ImportError, AttributeError):
    _WORKER_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _WORKER_AVAILABLE, reason="worker module unavailable"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_job_repo() -> MagicMock:
    repo = MagicMock()
    repo.update.return_value = [{}]
    return repo


def _make_supabase(
    release_raises: Exception | None = None, refund_raises: Exception | None = None
) -> MagicMock:
    """Return a mock Supabase client with a patched CreditLedger."""
    return MagicMock()  # CreditLedger is patched at import level in tests


def _make_ledger(
    release_raises: Exception | None = None, refund_raises: Exception | None = None
) -> MagicMock:
    ledger = MagicMock()
    if release_raises is not None:
        ledger.release.side_effect = release_raises
    if refund_raises is not None:
        ledger.refund.side_effect = refund_raises
    return ledger


def _make_job_data(
    status: str = JobStatus.PROCESSING,
    reservation_id: str | None = None,
) -> dict:
    return {
        "id": str(uuid4()),
        "user_id": str(uuid4()),
        "status": status,
        "credit_reservation_id": reservation_id or str(uuid4()),
    }


async def _call_fail_job(
    job_data: dict,
    failure_reason: str,
    ledger: MagicMock,
    identity_score: float | None = None,
) -> tuple[MagicMock, MagicMock]:
    """Call _fail_job with mocked dependencies. Returns (job_repo, ledger).

    CreditLedger is imported inside _fail_job, so we patch it at its
    definition location (app.entitlement.ledger.CreditLedger) and also
    at the local import path used by the worker module.
    """
    job_repo = _make_job_repo()
    supabase = MagicMock()

    # _fail_job does `from app.entitlement.ledger import CreditLedger`
    # so we patch the class at the module where it is defined.
    with patch("app.entitlement.ledger.CreditLedger", return_value=ledger):
        await _fail_job(
            job_repo=job_repo,
            job_id=job_data["id"],
            job_data=job_data,
            failure_reason=failure_reason,
            identity_score=identity_score,
            supabase=supabase,
        )

    return job_repo, ledger


# ---------------------------------------------------------------------------
# NON_USER_FAILURE_REASONS classification
# ---------------------------------------------------------------------------


class TestFailureClassification:
    """Verify NON_USER_FAILURE_REASONS contains the right reasons."""

    def test_provider_error_is_non_user(self):
        assert FAILURE_PROVIDER in NON_USER_FAILURE_REASONS

    def test_timeout_is_non_user(self):
        assert FAILURE_TIMEOUT in NON_USER_FAILURE_REASONS

    def test_nsfw_not_in_non_user(self):
        assert FAILURE_NSFW not in NON_USER_FAILURE_REASONS

    def test_identity_not_in_non_user(self):
        assert FAILURE_IDENTITY not in NON_USER_FAILURE_REASONS


# ---------------------------------------------------------------------------
# Auto-release for in-flight (non-finalizing) failures
# ---------------------------------------------------------------------------


class TestWorkerAutoReleaseOnProviderFailure:
    """Non-user-caused failures: worker auto-releases the credit reservation."""

    @pytest.mark.asyncio
    async def test_provider_failure_calls_release(self):
        """PROVIDER_ERROR: calls ledger.release()."""
        job_data = _make_job_data(status=JobStatus.PROCESSING)
        ledger = _make_ledger()

        job_repo, ledger = await _call_fail_job(job_data, FAILURE_PROVIDER, ledger)

        ledger.release.assert_called_once()
        ledger.refund.assert_not_called()

    @pytest.mark.asyncio
    async def test_timeout_failure_calls_release(self):
        """GENERATION_TIMEOUT: calls ledger.release()."""
        job_data = _make_job_data(status=JobStatus.PROCESSING)
        ledger = _make_ledger()

        _, ledger = await _call_fail_job(job_data, FAILURE_TIMEOUT, ledger)

        ledger.release.assert_called_once()

    @pytest.mark.asyncio
    async def test_job_marked_failed_with_correct_reason(self):
        """Job status is set to failed with the given failure_reason."""
        job_data = _make_job_data(status=JobStatus.PROCESSING)
        ledger = _make_ledger()

        job_repo, _ = await _call_fail_job(job_data, FAILURE_PROVIDER, ledger)

        update_call = job_repo.update.call_args
        assert update_call is not None
        update_data = update_call[0][1]
        assert update_data["status"] == JobStatus.FAILED
        assert update_data["failure_reason"] == FAILURE_PROVIDER


# ---------------------------------------------------------------------------
# Auto-refund for finalizing (credit already committed) failures
# ---------------------------------------------------------------------------


class TestWorkerAutoRefundOnFinalizingFailure:
    """Jobs stuck in FINALIZING have committed credits — refund() must be used."""

    @pytest.mark.asyncio
    async def test_finalizing_job_calls_refund_not_release(self):
        """FINALIZING job: calls ledger.refund() instead of release()."""
        job_data = _make_job_data(status=JobStatus.FINALIZING)
        ledger = _make_ledger()

        _, ledger = await _call_fail_job(job_data, FAILURE_TIMEOUT, ledger)

        ledger.refund.assert_called_once()
        ledger.release.assert_not_called()


# ---------------------------------------------------------------------------
# User-caused failures — credits still released (same path), but the
# client refund endpoint distinguishes via failure_reason / user_caused
# ---------------------------------------------------------------------------


class TestWorkerNoAutoRefundOnUserCausedFailures:
    """User-caused failures keep the credit consumed.

    The provider already ran a paid inference by the time we classify
    the output as NSFW or identity-drifted, so auto-refunding the user
    would leave NXME holding the bill. _fail_job commits the reserved
    credit (reserved → committed) so the balance reflects what we
    actually paid for.
    """

    @pytest.mark.asyncio
    async def test_nsfw_failure_commits_instead_of_releasing(self):
        """NSFW_CONTENT_DETECTED: credit is committed, not released."""
        job_data = _make_job_data(status=JobStatus.PROCESSING)
        ledger = _make_ledger()

        _, ledger = await _call_fail_job(job_data, FAILURE_NSFW, ledger)

        ledger.release.assert_not_called()
        ledger.refund.assert_not_called()
        ledger.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_identity_failure_commits_instead_of_releasing(self):
        """IDENTITY_PRESERVATION_FAILED: credit is committed, not released."""
        job_data = _make_job_data(
            status=JobStatus.PROCESSING, reservation_id=str(uuid4())
        )
        ledger = _make_ledger()

        _, ledger = await _call_fail_job(
            job_data, FAILURE_IDENTITY, ledger, identity_score=0.42
        )

        ledger.release.assert_not_called()
        ledger.refund.assert_not_called()
        ledger.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_user_caused_failure_in_finalizing_skips_commit(self):
        """Finalizing job with user-caused failure: credit already committed.

        The finalizer is the thing that performs ``ledger.commit`` for
        the happy path. If the job flips to FAILED while in FINALIZING
        with a user-caused reason, the credit is already in ``committed``
        and must be left alone — a second commit would raise ValueError.
        """
        job_data = _make_job_data(status=JobStatus.FINALIZING)
        ledger = _make_ledger()

        _, ledger = await _call_fail_job(job_data, FAILURE_IDENTITY, ledger)

        ledger.release.assert_not_called()
        ledger.refund.assert_not_called()
        ledger.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_identity_failure_updates_identity_fields(self):
        """identity_preserved=False is written to the job row on identity failure.

        The old jobs schema had an identity_similarity_score column; the tier-3
        schema (0034) removes it — only the boolean identity_preserved is stored.
        """
        job_data = _make_job_data(status=JobStatus.PROCESSING)
        ledger = _make_ledger()

        job_repo, _ = await _call_fail_job(
            job_data, FAILURE_IDENTITY, ledger, identity_score=0.35
        )

        update_data = job_repo.update.call_args[0][1]
        assert update_data["identity_preserved"] is False
        assert "identity_similarity_score" not in update_data


# ---------------------------------------------------------------------------
# No credit action for completed jobs
# ---------------------------------------------------------------------------


class TestWorkerNoActionForCompletedJobs:
    """Completed jobs have fully consumed credits — _fail_job must not touch them."""

    @pytest.mark.asyncio
    async def test_completed_job_skips_credit_settle(self):
        """A job already in COMPLETED status skips release/refund."""
        job_data = _make_job_data(status=JobStatus.COMPLETED)
        ledger = _make_ledger()

        _, ledger = await _call_fail_job(job_data, FAILURE_PROVIDER, ledger)

        ledger.release.assert_not_called()
        ledger.refund.assert_not_called()


# ---------------------------------------------------------------------------
# No credit action when no reservation
# ---------------------------------------------------------------------------


class TestWorkerNoActionWithoutReservation:
    """Jobs without a credit_reservation_id (free-tier) skip credit settle."""

    @pytest.mark.asyncio
    async def test_no_reservation_skips_ledger(self):
        """No reservation ID → no ledger calls."""
        job_data = _make_job_data(status=JobStatus.PROCESSING, reservation_id=None)
        # Override: no reservation
        job_data["credit_reservation_id"] = None
        ledger = _make_ledger()

        _, ledger = await _call_fail_job(job_data, FAILURE_PROVIDER, ledger)

        ledger.release.assert_not_called()
        ledger.refund.assert_not_called()


# ---------------------------------------------------------------------------
# Resilience — credit settle failure does not block job status update
# ---------------------------------------------------------------------------


class TestWorkerCreditSettleFailureResilience:
    """Credit settle errors are logged and swallowed — job is still marked failed."""

    @pytest.mark.asyncio
    async def test_release_failure_still_marks_job_failed(self):
        """If ledger.release() raises, the job is still marked as FAILED."""
        job_data = _make_job_data(status=JobStatus.PROCESSING)
        ledger = _make_ledger(release_raises=ValueError("already resolved"))

        job_repo, _ = await _call_fail_job(job_data, FAILURE_PROVIDER, ledger)

        update_data = job_repo.update.call_args[0][1]
        assert update_data["status"] == JobStatus.FAILED

    @pytest.mark.asyncio
    async def test_refund_failure_still_marks_job_failed(self):
        """If ledger.refund() raises for a finalizing job, job is still marked failed."""
        job_data = _make_job_data(status=JobStatus.FINALIZING)
        ledger = _make_ledger(refund_raises=ValueError("not committed"))

        job_repo, _ = await _call_fail_job(job_data, FAILURE_TIMEOUT, ledger)

        update_data = job_repo.update.call_args[0][1]
        assert update_data["status"] == JobStatus.FAILED
