"""Tests for MST bin blocklist filtering in preset_registry."""

from __future__ import annotations

import textwrap

import yaml
import pytest

from app.generation.preset_registry import (
    PresetRegistry,
    PresetRegistryModel,
    _reset_registry,
)


@pytest.fixture(autouse=True)
def reset():
    _reset_registry()
    yield
    _reset_registry()


def _make_registry(presets_yaml: str) -> PresetRegistry:
    full = f"fal_endpoint_version: v1\npresets:\n{presets_yaml}"
    raw = yaml.safe_load(full)
    return PresetRegistry(PresetRegistryModel.model_validate(raw))


BLOCKED_YAML = textwrap.dedent("""
  - slug: warm_tones
    display_name: Warm Tones
    fal_style: warm
    thumbnail: warm.jpg
    description: For warm undertones.
    supported_intensities: [subtle]
    intensity_mapping:
      subtle: light
    mst_bin_blocklist: [9, 10]
    deprecated: false
  - slug: universal
    display_name: Universal
    fal_style: natural
    thumbnail: universal.jpg
    description: Works for all MST bins.
    supported_intensities: [subtle]
    intensity_mapping:
      subtle: light
    mst_bin_blocklist: []
    deprecated: false
""")


class TestMstBinBlocklist:
    def test_excludes_preset_when_mst_bin_in_blocklist(self):
        reg = _make_registry(BLOCKED_YAML)
        available = reg.get_available_presets(mst_bin=9)
        slugs = [p.slug for p in available]
        assert "warm_tones" not in slugs
        assert "universal" in slugs

    def test_excludes_preset_for_bin_10(self):
        reg = _make_registry(BLOCKED_YAML)
        available = reg.get_available_presets(mst_bin=10)
        slugs = [p.slug for p in available]
        assert "warm_tones" not in slugs

    def test_includes_preset_when_mst_bin_not_in_blocklist(self):
        reg = _make_registry(BLOCKED_YAML)
        available = reg.get_available_presets(mst_bin=5)
        slugs = [p.slug for p in available]
        assert "warm_tones" in slugs
        assert "universal" in slugs

    def test_none_mst_bin_returns_all_non_deprecated(self):
        reg = _make_registry(BLOCKED_YAML)
        available = reg.get_available_presets(mst_bin=None)
        slugs = [p.slug for p in available]
        assert "warm_tones" in slugs
        assert "universal" in slugs

    def test_committed_yaml_has_seven_presets_for_bin_5(self):
        """Sanity check: all 7 presets available for a mid-range MST bin."""
        from app.generation.preset_registry import load_presets

        reg = load_presets()
        available = reg.get_available_presets(mst_bin=5)
        assert len(available) == 7
