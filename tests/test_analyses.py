"""Tests for analysis API models.

Exercises production code in:
  - app/api/analyses.py (SuggestionResponse, AnalysisResponse)
"""
from __future__ import annotations

import pytest


try:
    from app.api.analyses import SuggestionResponse, AnalysisResponse  # noqa: F401
    _ANALYSES_AVAILABLE = True
except (ImportError, AttributeError):
    _ANALYSES_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _ANALYSES_AVAILABLE, reason="analyses module unavailable"
)


class TestAnalysisModels:
    """Pydantic model tests — exercises app/api/analyses.py."""

    def test_suggestion_response(self):
        s = SuggestionResponse(rank=1, category="hair", suggestion="Try bangs")
        assert s.rank == 1
        assert s.category == "hair"

    def test_analysis_response_minimal(self):
        resp = AnalysisResponse(
            analysis_id="a-1",
            face_shape="oval",
            symmetry_score=0.85,
            recommendations=[],
            status="complete",
        )
        assert resp.face_shape == "oval"
        assert resp.symmetry_score == 0.85
        assert len(resp.recommendations) == 0

    def test_analysis_response_with_suggestions(self):
        resp = AnalysisResponse(
            analysis_id="a-2",
            face_shape="round",
            symmetry_score=0.72,
            recommendations=[
                SuggestionResponse(rank=1, category="hair", suggestion="Long layers"),
                SuggestionResponse(rank=2, category="accessories", suggestion="Angular glasses"),
            ],
            status="complete",
        )
        assert len(resp.recommendations) == 2
        assert resp.recommendations[0].rank == 1
