"""Tests for the makeup dispatch arm in process_generation_job."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_ctx(supabase=None, redis=None):
    return {
        "supabase": supabase or MagicMock(),
        "redis": redis or MagicMock(),
        "arq_pool": None,
    }


def _makeup_job(job_id="job-1", user_id="user-1"):
    return {
        "id": job_id,
        "user_id": user_id,
        "status": "queued",
        "source_type": "makeup_session",
        "source_id": "upload-abc",
        "preset_slug": "bold_red",
        "intensity": "medium",
        "credit_reservation_id": None,
    }


def _glowup_job(job_id="job-2", user_id="user-1"):
    return {
        "id": job_id,
        "user_id": user_id,
        "status": "queued",
        "source_type": "glowup_analysis",
        "source_id": "analysis-123",
        "credit_reservation_id": None,
    }


class TestMakeupDispatch:
    @pytest.mark.asyncio
    async def test_makeup_job_calls_pipeline_not_glowup_path(self):
        """source_type=makeup_session → _run_makeup_pipeline called, glow-up skipped."""
        ctx = _make_ctx()
        job = _makeup_job()

        with (
            patch("app.generation.worker.JobRepository"),
            patch(
                "app.generation.worker._fetch_and_claim_job",
                new_callable=AsyncMock,
                return_value=job,
            ),
            patch(
                "app.generation.worker._run_makeup_pipeline",
                new_callable=AsyncMock,
            ) as mock_makeup,
            patch("app.generation.worker._release_concurrent_counter", new_callable=AsyncMock),
        ):
            from app.generation.worker import process_generation_job

            await process_generation_job(ctx, "job-1")

        mock_makeup.assert_awaited_once()
        call_args = mock_makeup.call_args
        assert call_args[0][1] == "job-1"  # job_id positional arg

    @pytest.mark.asyncio
    async def test_glowup_job_does_not_call_makeup_pipeline(self):
        """source_type=glowup_analysis → makeup pipeline never called."""
        ctx = _make_ctx()

        # Return None from _fetch_and_claim_job so glow-up path returns early
        with (
            patch(
                "app.generation.worker._fetch_and_claim_job",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.generation.worker._run_makeup_pipeline",
                new_callable=AsyncMock,
            ) as mock_makeup,
        ):
            from app.generation.worker import process_generation_job

            await process_generation_job(ctx, "job-2")

        mock_makeup.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_makeup_pipeline_exception_propagates(self):
        """Unhandled exception from pipeline bubbles up (ARQ handles retries)."""
        ctx = _make_ctx()
        job = _makeup_job()

        with (
            patch(
                "app.generation.worker._fetch_and_claim_job",
                new_callable=AsyncMock,
                return_value=job,
            ),
            patch(
                "app.generation.worker._run_makeup_pipeline",
                new_callable=AsyncMock,
                side_effect=RuntimeError("pipeline exploded"),
            ),
            patch("app.generation.worker._release_concurrent_counter", new_callable=AsyncMock),
        ):
            from app.generation.worker import process_generation_job

            with pytest.raises(RuntimeError, match="pipeline exploded"):
                await process_generation_job(ctx, "job-1")
