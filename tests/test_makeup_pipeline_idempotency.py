"""Integration tests for the two-stage idempotency contract in makeup_pipeline.

Execution note: written BEFORE the pipeline implementation so each test
describes the correctness contract rather than the code path.
"""

from __future__ import annotations

from unittest.mock import ANY, AsyncMock, MagicMock

import pytest

from app.generation.adapters.falai import MakeupAdapterError, MakeupAdapterResult
from app.generation.makeup_pipeline import MakeupPipeline


def _fresh_job(
    job_id: str = "job-1",
    user_id: str = "user-1",
    *,
    fal_request_id: str | None = None,
    fal_idempotency_key: str | None = None,
    fal_url: str | None = None,
    consent_version: str | None = "makeup_v1",
) -> dict:
    return {
        "id": job_id,
        "user_id": user_id,
        "status": "processing",
        "source_id": "upload-abc",
        "source_type": "makeup_session",
        "preset_slug": "bold_red",
        "intensity": "medium",
        "idempotency_key": "makeup:test-idem",
        "idempotency_key_body_hash": "abc123",
        "fal_request_id": fal_request_id,
        "fal_idempotency_key": fal_idempotency_key,
        "fal_url": fal_url,
        "consent_version_at_enqueue": consent_version,
        "credit_reservation_id": "res-1",
        "user_tier_at_enqueue": "PREMIUM",
    }


def _make_pipeline(
    *,
    job_seq: list[dict | None] | None = None,
    fal_result: MakeupAdapterResult | None = None,
    fal_error: MakeupAdapterError | None = None,
    copy_side_effects: list | None = None,
    entitlements: bool = True,
    image_url: str = "https://fal.media/selfie.jpg",
) -> tuple[MakeupPipeline, MagicMock, MagicMock, MagicMock]:
    """Build a MakeupPipeline with all dependencies mocked.

    Returns (pipeline, job_repo, fal_adapter, output_copier).
    """
    job_repo = MagicMock()
    if job_seq is not None:
        job_repo.get_for_makeup_worker.side_effect = job_seq

    # Mock image repo for signed URL resolution
    image_repo = MagicMock()
    image_repo.create_signed_url.return_value = image_url
    upload_repo = MagicMock()
    upload_repo.get_by_id.return_value = {"image_url": "raw-selfies/user-1/photo.jpg"}

    fal_adapter = MagicMock()
    if fal_error is not None:
        fal_adapter.apply_makeup_preset = AsyncMock(side_effect=fal_error)
    else:
        fal_result = fal_result or MakeupAdapterResult(
            fal_request_id="fal-req-abc", fal_output_url="https://fal.media/output.jpg"
        )
        fal_adapter.apply_makeup_preset = AsyncMock(return_value=fal_result)

    output_copier = MagicMock()
    if copy_side_effects is not None:
        output_copier.copy = AsyncMock(side_effect=copy_side_effects)
    else:
        output_copier.copy = AsyncMock(return_value=None)

    pipeline = MakeupPipeline(
        job_repo=job_repo,
        fal_adapter=fal_adapter,
        output_copier=output_copier,
        redis_client=MagicMock(),
        entitlements_check=AsyncMock(return_value=entitlements),
        image_repo=image_repo,
        upload_repo=upload_repo,
    )
    return pipeline, job_repo, fal_adapter, output_copier


# ---------------------------------------------------------------------------
# Stage B retry does not re-call fal
# ---------------------------------------------------------------------------


class TestStageBRetryDoesNotRecallFal:
    @pytest.mark.asyncio
    async def test_fal_called_once_after_stage_b_retry(self):
        """Stage A commits, Stage B copy fails; second run skips Stage A."""
        job_id = "job-1"
        fresh = _fresh_job(job_id=job_id)
        committed = _fresh_job(
            job_id=job_id,
            fal_request_id="fal-req-abc",
            fal_idempotency_key="idem-key",
            fal_url="https://fal.media/output.jpg",
        )

        pipeline, job_repo, fal_adapter, output_copier = _make_pipeline(
            # First run: Stage A runs on fresh job; second run: job has fal_request_id
            job_seq=[fresh, committed],
            copy_side_effects=[RuntimeError("copy failed"), None],
        )

        # Run 1: Stage A succeeds, Stage B raises
        with pytest.raises(RuntimeError, match="copy failed"):
            await pipeline.run(job_id)

        assert fal_adapter.apply_makeup_preset.call_count == 1

        # Run 2: Stage A skipped (fal_request_id set), Stage B succeeds
        await pipeline.run(job_id)

        assert fal_adapter.apply_makeup_preset.call_count == 1
        job_repo.update_makeup_job_completed.assert_called_once()


# ---------------------------------------------------------------------------
# Stage A already committed → skip fal entirely
# ---------------------------------------------------------------------------


class TestStageASkippedWhenFalRequestIdSet:
    @pytest.mark.asyncio
    async def test_fal_never_called_when_stage_a_already_committed(self):
        """Job already has fal_request_id — Stage A must be skipped."""
        job = _fresh_job(
            fal_request_id="fal-req-existing",
            fal_idempotency_key="idem-key",
            fal_url="https://fal.media/output.jpg",
        )

        pipeline, job_repo, fal_adapter, output_copier = _make_pipeline(
            job_seq=[job],
        )

        await pipeline.run("job-1")

        fal_adapter.apply_makeup_preset.assert_not_called()
        job_repo.update_makeup_job_completed.assert_called_once()


# ---------------------------------------------------------------------------
# Refused: Pro lapses between submit and worker entry
# ---------------------------------------------------------------------------


class TestRefusedWhenProLapsed:
    @pytest.mark.asyncio
    async def test_refused_when_has_active_pro_false(self):
        """has_active_pro returns False → refused, fair-use decremented, fal never called."""
        pipeline, job_repo, fal_adapter, _ = _make_pipeline(
            job_seq=[_fresh_job()],
            entitlements=False,
        )

        await pipeline.run("job-1")

        fal_adapter.apply_makeup_preset.assert_not_called()
        job_repo.update_makeup_job_failed.assert_called_once_with(
            "job-1", "refused", ANY
        )


# ---------------------------------------------------------------------------
# Non-retryable fal error → job fails, counter decremented
# ---------------------------------------------------------------------------


class TestNonRetryableFalError:
    @pytest.mark.asyncio
    async def test_bad_request_fails_job_as_non_retryable(self):
        """fal 422 bad_request → job ends (failed, non_retryable), fal called once."""
        pipeline, job_repo, fal_adapter, _ = _make_pipeline(
            job_seq=[_fresh_job()],
            fal_error=MakeupAdapterError(
                kind="non_retryable", reason="fal_bad_request"
            ),
        )

        await pipeline.run("job-1")

        assert fal_adapter.apply_makeup_preset.call_count == 1
        job_repo.update_makeup_job_failed.assert_called_once_with(
            "job-1", "non_retryable", ANY
        )


# ---------------------------------------------------------------------------
# Retryable fal error → pipeline re-raises (ARQ handles retry)
# ---------------------------------------------------------------------------


class TestRetryableFalError:
    @pytest.mark.asyncio
    async def test_retryable_error_is_reraised(self):
        """fal 503 → MakeupAdapterError(retryable) propagates to caller."""
        pipeline, _, _, _ = _make_pipeline(
            job_seq=[_fresh_job()],
            fal_error=MakeupAdapterError(
                kind="retryable", reason="fal_server_error_503"
            ),
        )

        with pytest.raises(MakeupAdapterError) as exc_info:
            await pipeline.run("job-1")

        assert exc_info.value.kind == "retryable"


# ---------------------------------------------------------------------------
# Terminal-success leaves makeup_failure_reason NULL
# ---------------------------------------------------------------------------


class TestSuccessLeavesFailureReasonNull:
    @pytest.mark.asyncio
    async def test_completed_job_row_has_no_failure_reason(self):
        """Happy-path completion must NOT write makeup_failure_reason."""
        pipeline, job_repo, _, _ = _make_pipeline(
            job_seq=[_fresh_job()],
        )

        await pipeline.run("job-1")

        # update_makeup_job_failed should never be called on success
        job_repo.update_makeup_job_failed.assert_not_called()
        job_repo.update_makeup_job_completed.assert_called_once()

    @pytest.mark.asyncio
    async def test_output_key_uses_user_and_job_prefix(self):
        """output_key = {user_id}/{job_id}/output.jpg."""
        pipeline, job_repo, _, output_copier = _make_pipeline(
            job_seq=[_fresh_job(job_id="job-1", user_id="user-1")],
        )

        await pipeline.run("job-1")

        call_args = job_repo.update_makeup_job_completed.call_args
        output_key = call_args[0][1]  # positional arg[1]
        assert output_key == "user-1/job-1/output.jpg"
