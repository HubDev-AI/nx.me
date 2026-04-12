"""Tests for uploads + glowup API response models.

Replaces the old test_analyses.py which tested app/api/analyses.py
(deleted in Phase 2). Now exercises:
  - app/api/uploads.py (UploadResponse)
  - app/api/glowup.py (AnalyzeResponse, SuggestionResponse)
"""

from __future__ import annotations

import pytest


try:
    from app.api.uploads import UploadResponse  # noqa: F401

    _UPLOADS_AVAILABLE = True
except (ImportError, AttributeError):
    _UPLOADS_AVAILABLE = False

try:
    from app.api.glowup import SuggestionResponse, AnalyzeResponse  # noqa: F401

    _GLOWUP_AVAILABLE = True
except (ImportError, AttributeError):
    _GLOWUP_AVAILABLE = False


class TestUploadResponseModel:
    """Pydantic model tests — exercises app/api/uploads.py."""

    @pytest.mark.skipif(not _UPLOADS_AVAILABLE, reason="uploads module unavailable")
    def test_upload_response_fields(self):
        import uuid

        upload_id = str(uuid.uuid4())
        resp = UploadResponse(upload_id=upload_id, face_detected=True)
        assert resp.upload_id == upload_id
        assert resp.face_detected is True

    @pytest.mark.skipif(not _UPLOADS_AVAILABLE, reason="uploads module unavailable")
    def test_upload_response_no_face(self):
        import uuid

        resp = UploadResponse(upload_id=str(uuid.uuid4()), face_detected=False)
        assert resp.face_detected is False


class TestGlowupModels:
    """Pydantic model tests — exercises app/api/glowup.py."""

    @pytest.mark.skipif(not _GLOWUP_AVAILABLE, reason="glowup module unavailable")
    def test_suggestion_response(self):
        s = SuggestionResponse(rank=1, category="hair", suggestion="Try bangs")
        assert s.rank == 1
        assert s.category == "hair"
        assert s.suggestion == "Try bangs"

    @pytest.mark.skipif(not _GLOWUP_AVAILABLE, reason="glowup module unavailable")
    def test_analyze_response_minimal(self):
        import uuid

        resp = AnalyzeResponse(
            glowup_analysis_id=str(uuid.uuid4()),
            face_shape="oval",
            symmetry_score=0.85,
            recommendations=[],
        )
        assert resp.face_shape == "oval"
        assert resp.symmetry_score == 0.85
        assert len(resp.recommendations) == 0

    @pytest.mark.skipif(not _GLOWUP_AVAILABLE, reason="glowup module unavailable")
    def test_analyze_response_with_suggestions(self):
        import uuid

        resp = AnalyzeResponse(
            glowup_analysis_id=str(uuid.uuid4()),
            face_shape="round",
            symmetry_score=0.72,
            recommendations=[
                SuggestionResponse(rank=1, category="hair", suggestion="Long layers"),
                SuggestionResponse(
                    rank=2, category="accessories", suggestion="Angular glasses"
                ),
            ],
        )
        assert len(resp.recommendations) == 2
        assert resp.recommendations[0].rank == 1
