"""Smoke tests for the analytics event module.

Verifies that all event functions in app/analytics/events.py can be called
without raising. No assertions on log output — the functions are log-only stubs.
"""

from __future__ import annotations

import pytest


try:
    from app.analytics import events

    _AVAILABLE = True
except (ImportError, AttributeError):
    _AVAILABLE = False

pytestmark = pytest.mark.skipif(not _AVAILABLE, reason="analytics module unavailable")


# ---------------------------------------------------------------------------
# Upload events
# ---------------------------------------------------------------------------


def test_glowup_upload_created_does_not_raise() -> None:
    events.glowup_upload_created(
        upload_id="upload-1", user_id="user-1", face_detected=True
    )


def test_glowup_upload_created_no_face_does_not_raise() -> None:
    events.glowup_upload_created(
        upload_id="upload-2", user_id="user-2", face_detected=False
    )


# ---------------------------------------------------------------------------
# Analyze events
# ---------------------------------------------------------------------------


def test_glowup_analyze_completed_does_not_raise() -> None:
    events.glowup_analyze_completed(
        glowup_analysis_id="analysis-1",
        upload_id="upload-1",
        user_id="user-1",
        face_shape="oval",
        symmetry_score=0.85,
        duration_ms=3200,
    )


def test_glowup_analyze_completed_none_values_does_not_raise() -> None:
    events.glowup_analyze_completed(
        glowup_analysis_id="analysis-2",
        upload_id="upload-2",
        user_id="user-2",
        face_shape=None,
        symmetry_score=None,
        duration_ms=1000,
    )


def test_glowup_analyze_failed_does_not_raise() -> None:
    events.glowup_analyze_failed(
        upload_id="upload-1",
        user_id="user-1",
        failure_code="FACE_NOT_DETECTED",
    )


# ---------------------------------------------------------------------------
# Generation events
# ---------------------------------------------------------------------------


def test_glowup_generation_completed_does_not_raise() -> None:
    events.glowup_generation_completed(
        job_id="job-1",
        source_id="analysis-1",
        user_id="user-1",
        arcface_score=0.92,
        latency_ms=15000,
    )


def test_glowup_generation_completed_no_arcface_does_not_raise() -> None:
    events.glowup_generation_completed(
        job_id="job-2",
        source_id="analysis-2",
        user_id="user-2",
        arcface_score=None,
        latency_ms=12000,
    )


def test_glowup_generation_failed_does_not_raise() -> None:
    events.glowup_generation_failed(
        job_id="job-1",
        source_id="analysis-1",
        user_id="user-1",
        failure_code="PROVIDER_ERROR",
    )


# ---------------------------------------------------------------------------
# Save and share events
# ---------------------------------------------------------------------------


def test_glowup_save_does_not_raise() -> None:
    events.glowup_save(job_id="job-1", user_id="user-1")


def test_glowup_share_does_not_raise() -> None:
    events.glowup_share(job_id="job-1", user_id="user-1")


# ---------------------------------------------------------------------------
# Consent events
# ---------------------------------------------------------------------------


def test_glowup_consent_granted_does_not_raise() -> None:
    events.glowup_consent_granted(user_id="user-1")
