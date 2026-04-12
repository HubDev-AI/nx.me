"""Analytics event emitter — log-only stub for v1.

All events are emitted to the structured logger under the 'analytics' namespace.
No external sink in this release; add a real sink (Mixpanel / PostHog / Segment)
by replacing _emit() without touching call sites.

Usage:
    from app.analytics import events
    events.glowup_upload_created(upload_id="...", user_id="...", face_detected=True)
"""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger("analytics")


def _emit(event: str, **props: Any) -> None:
    """Emit a structured analytics event to the logger.

    All event calls are wrapped in try/except at call sites so a logging failure
    never surfaces to the request layer. This function itself is intentionally
    simple — swap the body here when adding a real sink.
    """
    _log.info("event=%s %s", event, props)


# ---------------------------------------------------------------------------
# Glow Up — upload
# ---------------------------------------------------------------------------


def glowup_upload_created(
    *,
    upload_id: str,
    user_id: str,
    face_detected: bool,
) -> None:
    """Fired after a selfie is successfully uploaded and processed."""
    _emit(
        "glowup.upload.created",
        upload_id=upload_id,
        user_id=user_id,
        face_detected=face_detected,
    )


# ---------------------------------------------------------------------------
# Glow Up — analyze
# ---------------------------------------------------------------------------


def glowup_analyze_completed(
    *,
    glowup_analysis_id: str,
    upload_id: str,
    user_id: str,
    face_shape: str | None,
    symmetry_score: float | None,
    duration_ms: int,
) -> None:
    """Fired after face analysis completes successfully."""
    _emit(
        "glowup.analyze.completed",
        glowup_analysis_id=glowup_analysis_id,
        upload_id=upload_id,
        user_id=user_id,
        face_shape=face_shape,
        symmetry_score=symmetry_score,
        duration_ms=duration_ms,
    )


def glowup_analyze_failed(
    *,
    upload_id: str,
    user_id: str,
    failure_code: str,
) -> None:
    """Fired when face analysis fails (e.g. FACE_NOT_DETECTED)."""
    _emit(
        "glowup.analyze.failed",
        upload_id=upload_id,
        user_id=user_id,
        failure_code=failure_code,
    )


# ---------------------------------------------------------------------------
# Glow Up — generation
# ---------------------------------------------------------------------------


def glowup_generation_completed(
    *,
    job_id: str,
    source_id: str,
    user_id: str,
    arcface_score: float | None,
    latency_ms: int,
) -> None:
    """Fired after a generation job completes successfully."""
    _emit(
        "glowup.generation.completed",
        job_id=job_id,
        source_id=source_id,
        user_id=user_id,
        arcface_score=arcface_score,
        latency_ms=latency_ms,
    )


def glowup_generation_failed(
    *,
    job_id: str,
    source_id: str,
    user_id: str,
    failure_code: str,
) -> None:
    """Fired when a generation job fails for any reason."""
    _emit(
        "glowup.generation.failed",
        job_id=job_id,
        source_id=source_id,
        user_id=user_id,
        failure_code=failure_code,
    )


# ---------------------------------------------------------------------------
# Glow Up — save & share
# ---------------------------------------------------------------------------


def glowup_save(
    *,
    job_id: str,
    user_id: str,
) -> None:
    """Fired when a user saves a completed generation result."""
    _emit("glowup.save", job_id=job_id, user_id=user_id)


def glowup_share(
    *,
    job_id: str,
    user_id: str,
) -> None:
    """Fired when a user shares a completed generation result."""
    _emit("glowup.share", job_id=job_id, user_id=user_id)


# ---------------------------------------------------------------------------
# Glow Up — consent
# ---------------------------------------------------------------------------


def glowup_consent_granted(
    *,
    user_id: str,
) -> None:
    """Fired the first time a user grants face-modification consent."""
    _emit("glowup.consent.granted", user_id=user_id)
