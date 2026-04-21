"""Two-stage idempotent makeup generation pipeline.

Stage A — fal_call_committed
    Checks consent, entitlement, pre-writes fal_idempotency_key, calls fal,
    commits fal_request_id + fal_url.  Skipped if fal_request_id IS NOT NULL
    (idempotent on retry).

Stage B — output_persisted
    Downloads fal output, uploads to private makeup-outputs bucket, marks job
    completed.  Skipped only if already completed.  Never re-runs Stage A.

Design: all dependencies are injected so unit tests mock at the boundary
without patch() acrobatics.  The worker constructs the pipeline from ctx.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Callable

from app.generation.adapters.falai import MakeupAdapterError
from app.repositories.job_repo import (
    MAKEUP_FAILURE_NON_RETRYABLE,
    MAKEUP_FAILURE_REFUSED,
    MAKEUP_FAILURE_RETRYABLE,
)

logger = logging.getLogger(__name__)

_MAKEUP_CONSENT_MIN_VERSION = "makeup_v1"


def _now_utc() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


async def _decrement_fair_use(
    redis_client: object,
    user_id: str,
    namespaced_key: str | None,
) -> None:
    """Stub — Unit 6 replaces with Lua-backed DECR + marker DEL."""
    # No-op until the fair-use Lua scripts land in Unit 6.
    pass


class MakeupPipeline:
    """Orchestrates the two-stage makeup generation pipeline for one job."""

    def __init__(
        self,
        *,
        job_repo,
        fal_adapter,
        output_copier,
        redis_client,
        entitlements_check: Callable,
        image_repo=None,
        upload_repo=None,
    ) -> None:
        self._job_repo = job_repo
        self._fal = fal_adapter
        self._copier = output_copier
        self._redis = redis_client
        self._entitlements_check = entitlements_check
        self._image_repo = image_repo
        self._upload_repo = upload_repo

    async def run(self, job_id: str) -> None:
        """Run Stage A then Stage B; each stage is idempotent on retry."""
        job = self._job_repo.get_for_makeup_worker(job_id)
        if not job:
            logger.error("Makeup job %s not found", job_id)
            return

        if not job.get("fal_request_id"):
            fal_url = await self._stage_a(job)
            if fal_url is None:
                return
            job = {**job, "fal_url": fal_url}

        await self._stage_b(job)

    async def _stage_a(self, job: dict) -> str | None:
        """Run Stage A: consent check, entitlement, pre-write key, call fal, commit.

        Returns the fal output URL on success, or None if job was terminal-failed.
        Raises MakeupAdapterError(retryable) on transient fal errors.
        """
        job_id = job["id"]
        user_id = job["user_id"]
        now = _now_utc()

        # Consent gating
        consent_snapshot = job.get("consent_version_at_enqueue")
        if not consent_snapshot:
            logger.error("Job %s missing consent_version_at_enqueue", job_id)
            self._job_repo.update_makeup_job_failed(job_id, MAKEUP_FAILURE_NON_RETRYABLE, now)
            return None

        # Entitlement check — Pro may have lapsed between enqueue and worker entry
        if not await self._entitlements_check(user_id):
            await _decrement_fair_use(self._redis, user_id, job.get("idempotency_key"))
            self._job_repo.update_makeup_job_failed(job_id, MAKEUP_FAILURE_REFUSED, now)
            return None

        # Pre-write fal_idempotency_key before calling fal (crash safety)
        if not job.get("fal_idempotency_key"):
            key = secrets.token_urlsafe(16)
            self._job_repo.pre_write_fal_idempotency_key(job_id, key)
            job = {**job, "fal_idempotency_key": key}

        # Resolve source image URL
        source_url = self._resolve_source_url(job)

        # Map preset slug + our intensity → fal style + fal intensity
        from app.generation.preset_registry import map_to_fal

        fal_style, fal_intensity = map_to_fal(job["preset_slug"], job["intensity"])

        try:
            result = await self._fal.apply_makeup_preset(
                source_url,
                fal_style,
                fal_intensity,
                idempotency_key=job["fal_idempotency_key"],
            )
        except MakeupAdapterError as exc:
            if exc.kind == "retryable":
                raise  # let ARQ retry
            # non_retryable or config → terminal failure, refund fair-use
            await _decrement_fair_use(self._redis, user_id, job.get("idempotency_key"))
            failure_code = (
                MAKEUP_FAILURE_NON_RETRYABLE
                if exc.kind == "non_retryable"
                else MAKEUP_FAILURE_RETRYABLE
            )
            self._job_repo.update_makeup_job_failed(job_id, failure_code, now)
            return None

        self._job_repo.commit_stage_a(
            job_id, result.fal_request_id, result.fal_output_url, now
        )
        return result.fal_output_url

    async def _stage_b(self, job: dict) -> None:
        """Download fal output, store in Supabase, mark job completed."""
        job_id = job["id"]
        user_id = job["user_id"]
        fal_url = job["fal_url"]
        target_key = f"{user_id}/{job_id}/output.jpg"
        now = _now_utc()

        await self._copier.copy(fal_url, target_key)
        self._job_repo.update_makeup_job_completed(job_id, target_key, now)

    def _resolve_source_url(self, job: dict) -> str:
        """Resolve the signed source image URL from the job's source_id (upload_id)."""
        source_id = job.get("source_id")
        if source_id and self._upload_repo and self._image_repo:
            upload = self._upload_repo.get_by_id(source_id, touch_access=False)
            if upload and upload.get("image_url"):
                return self._image_repo.create_signed_url(
                    "raw-selfies", upload["image_url"], 300
                )

        # Fallback for tests / edge cases without repos injected
        before_url = job.get("before_image_url")
        if before_url:
            return before_url

        raise ValueError(
            f"Cannot resolve source URL for makeup job {job.get('id')}: "
            f"source_id={source_id}"
        )
