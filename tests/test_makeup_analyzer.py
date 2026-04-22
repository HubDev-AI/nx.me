"""Tests for app.generation.makeup_analyzer."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.generation.makeup_analyzer import (
    AnalysisError,
    MakeupAnalysis,
    _classify_mst,
    _classify_undertone,
    _rank_presets,
    analyze,
    analyzer_stale,
)
from app.generation.preset_registry import _reset_registry


@pytest.fixture(autouse=True)
def reset_registry():
    _reset_registry()
    yield
    _reset_registry()


# ---------------------------------------------------------------------------
# MST classifier
# ---------------------------------------------------------------------------


class TestClassifyMst:
    def test_very_light_skin_bin_1(self):
        assert _classify_mst((240, 240, 240)) == 1

    def test_dark_skin_bin_10(self):
        assert _classify_mst((40, 30, 25)) == 10

    def test_mid_tone_in_range(self):
        bin_ = _classify_mst((160, 130, 110))
        assert 4 <= bin_ <= 7

    def test_returns_int(self):
        assert isinstance(_classify_mst((200, 180, 170)), int)


# ---------------------------------------------------------------------------
# Undertone classifier
# ---------------------------------------------------------------------------


class TestClassifyUndertone:
    def test_warm_when_red_exceeds_blue(self):
        assert _classify_undertone((200, 150, 170)) == "warm"

    def test_cool_when_blue_exceeds_red(self):
        assert _classify_undertone((150, 150, 200)) == "cool"

    def test_neutral_when_close(self):
        assert _classify_undertone((180, 160, 175)) == "neutral"


# ---------------------------------------------------------------------------
# analyze() — happy path via mocking
# ---------------------------------------------------------------------------


class TestAnalyze:
    _FAKE_ANCHORS = {
        "lip": (10, 200, 90, 220),
        "eye": (30, 100, 120, 130),
        "cheek": (20, 160, 180, 200),
    }

    def test_returns_makeup_analysis_with_valid_fields(self):
        with (
            patch(
                "app.generation.makeup_analyzer.get_region_anchors",
                return_value=self._FAKE_ANCHORS,
            ),
            patch(
                "app.generation.makeup_analyzer._mean_skin_rgb",
                return_value=(200.0, 170.0, 155.0),
            ),
        ):
            result = analyze("https://example.com/selfie.jpg", "user-1")

        assert isinstance(result, MakeupAnalysis)
        assert 1 <= result.mst_bin <= 10
        assert result.undertone in {"warm", "neutral", "cool"}
        assert isinstance(result.region_anchors, dict)
        assert "lip" in result.region_anchors
        assert "eye" in result.region_anchors
        assert isinstance(result.recommended_preset_ranking, list)
        assert len(result.recommended_preset_ranking) > 0

    def test_raises_analysis_error_when_no_face(self):
        with patch(
            "app.generation.makeup_analyzer.get_region_anchors",
            return_value=None,
        ):
            with pytest.raises(AnalysisError) as exc_info:
                analyze("https://example.com/selfie.jpg", "user-1")
        assert exc_info.value.reason == "no_face"

    def test_created_at_is_utc(self):
        with (
            patch(
                "app.generation.makeup_analyzer.get_region_anchors",
                return_value=self._FAKE_ANCHORS,
            ),
            patch(
                "app.generation.makeup_analyzer._mean_skin_rgb",
                return_value=(200.0, 170.0, 155.0),
            ),
        ):
            result = analyze("https://example.com/selfie.jpg", "user-1")
        assert result.created_at.tzinfo is not None


# ---------------------------------------------------------------------------
# analyzer_stale()
# ---------------------------------------------------------------------------


class TestAnalyzerStale:
    def _fresh_row(self, **overrides) -> dict:
        row = {
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
            "mst_bin": 5,
            "undertone": "warm",
            "region_anchors": {"lip": [10, 200, 90, 220]},
        }
        row.update(overrides)
        return row

    def test_fresh_row_not_stale(self):
        assert analyzer_stale(self._fresh_row()) is False

    def test_row_older_than_89_days_is_stale(self):
        old_ts = (datetime.now(tz=timezone.utc) - timedelta(days=90)).isoformat()
        assert analyzer_stale(self._fresh_row(created_at=old_ts)) is True

    def test_row_just_under_89_days_not_stale(self):
        ts = (datetime.now(tz=timezone.utc) - timedelta(days=88, hours=23)).isoformat()
        assert analyzer_stale(self._fresh_row(created_at=ts)) is False

    def test_nullified_mst_bin_is_stale(self):
        assert analyzer_stale(self._fresh_row(mst_bin=None)) is True

    def test_nullified_undertone_is_stale(self):
        assert analyzer_stale(self._fresh_row(undertone=None)) is True

    def test_nullified_region_anchors_is_stale(self):
        assert analyzer_stale(self._fresh_row(region_anchors=None)) is True

    def test_missing_created_at_is_stale(self):
        row = {"mst_bin": 5, "undertone": "warm", "region_anchors": {}}
        assert analyzer_stale(row) is True


# ---------------------------------------------------------------------------
# _rank_presets()
# ---------------------------------------------------------------------------


class TestRankPresets:
    def test_returns_non_empty_list(self):
        ranking = _rank_presets(mst_bin=5, undertone="warm")
        assert isinstance(ranking, list)
        assert len(ranking) > 0

    def test_all_slugs_are_strings(self):
        for slug in _rank_presets(5, "neutral"):
            assert isinstance(slug, str)

    def test_warm_preferred_presets_ranked_first_for_warm_undertone(self):
        ranking = _rank_presets(5, "warm")
        top = set(ranking[:2])
        warm_preferred = {"bold_red", "soft_glam", "bridal"}
        assert top & warm_preferred, (
            f"Expected warm presets near top, got {ranking[:3]}"
        )
