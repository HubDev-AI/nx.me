"""Tests for app.generation.preset_registry."""

from __future__ import annotations

import textwrap

import pytest
import yaml

from app.generation.preset_registry import (
    Preset,
    PresetNotFound,
    PresetRegistry,
    PresetRegistryModel,
    _reset_registry,
    load_presets,
)


@pytest.fixture(autouse=True)
def reset_singleton():
    _reset_registry()
    yield
    _reset_registry()


def _registry_from_yaml(src: str) -> PresetRegistry:
    raw = yaml.safe_load(src)
    model = PresetRegistryModel.model_validate(raw)
    return PresetRegistry(model)


MINIMAL_YAML = textwrap.dedent("""
    fal_endpoint_version: "image-apps-v2/makeup-application"
    presets:
      - slug: bold_red
        display_name: Bold Red
        fal_style: bold_lips
        thumbnail: bold_red.jpg
        description: Classic bold red lip.
        supported_intensities: [medium, bold]
        intensity_mapping:
          medium: medium
          bold: heavy
        mst_bin_blocklist: []
        deprecated: false
      - slug: soft_glam
        display_name: Soft Glam
        fal_style: soft_glam
        thumbnail: soft_glam.jpg
        description: Everyday glam.
        supported_intensities: [subtle, light]
        intensity_mapping:
          subtle: light
          light: medium
        mst_bin_blocklist: []
        deprecated: false
""")


class TestLoadPresets:
    def test_loads_committed_yaml(self):
        registry = load_presets()
        assert len(registry.get_available_presets()) == 7

    def test_returns_same_singleton(self):
        r1 = load_presets()
        r2 = load_presets()
        assert r1 is r2

    def test_raises_on_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_presets(path=tmp_path / "nonexistent.yaml")

    def test_raises_on_malformed_yaml(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("fal_endpoint_version: x\npresets:\n  - slug: s\n")
        with pytest.raises(Exception):
            load_presets(path=bad)


class TestMapToFal:
    def test_bold_red_medium_returns_bold_lips_medium(self):
        reg = _registry_from_yaml(MINIMAL_YAML)
        assert reg.map_to_fal("bold_red", "medium") == ("bold_lips", "medium")

    def test_bold_red_bold_returns_bold_lips_heavy(self):
        reg = _registry_from_yaml(MINIMAL_YAML)
        assert reg.map_to_fal("bold_red", "bold") == ("bold_lips", "heavy")

    def test_unknown_slug_raises_preset_not_found(self):
        reg = _registry_from_yaml(MINIMAL_YAML)
        with pytest.raises(PresetNotFound):
            reg.map_to_fal("unknown_slug", "medium")

    def test_unknown_intensity_raises_key_error(self):
        reg = _registry_from_yaml(MINIMAL_YAML)
        with pytest.raises(KeyError):
            reg.map_to_fal("bold_red", "subtle")  # not in intensity_mapping


class TestGetAvailablePresets:
    def test_returns_all_non_deprecated(self):
        reg = _registry_from_yaml(MINIMAL_YAML)
        assert len(reg.get_available_presets()) == 2

    def test_filters_deprecated(self):
        src = textwrap.dedent("""
            fal_endpoint_version: v1
            presets:
              - slug: old
                display_name: Old
                fal_style: old_style
                thumbnail: old.jpg
                description: Deprecated.
                supported_intensities: [subtle]
                intensity_mapping:
                  subtle: light
                deprecated: true
              - slug: new
                display_name: New
                fal_style: new_style
                thumbnail: new.jpg
                description: Active.
                supported_intensities: [subtle]
                intensity_mapping:
                  subtle: light
                deprecated: false
        """)
        reg = _registry_from_yaml(src)
        available = reg.get_available_presets()
        slugs = [p.slug for p in available]
        assert "old" not in slugs
        assert "new" in slugs

    def test_none_mst_bin_skips_blocklist_filter(self):
        reg = _registry_from_yaml(MINIMAL_YAML)
        assert len(reg.get_available_presets(mst_bin=None)) == 2

    def test_get_preset_returns_none_for_unknown(self):
        reg = _registry_from_yaml(MINIMAL_YAML)
        assert reg.get_preset("does_not_exist") is None

    def test_get_preset_returns_preset_object(self):
        reg = _registry_from_yaml(MINIMAL_YAML)
        p = reg.get_preset("bold_red")
        assert p is not None
        assert p.fal_style == "bold_lips"


class TestPresetValidation:
    def test_rejects_unknown_intensity_in_supported(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="Unknown intensity values"):
            Preset(
                slug="x",
                display_name="X",
                fal_style="y",
                thumbnail="x.jpg",
                description="",
                supported_intensities=["ultra"],
                intensity_mapping={"ultra": "dramatic"},
            )

    def test_rejects_missing_mapping_for_supported_intensity(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="intensity_mapping is missing"):
            Preset(
                slug="x",
                display_name="X",
                fal_style="y",
                thumbnail="x.jpg",
                description="",
                supported_intensities=["subtle", "bold"],
                intensity_mapping={"subtle": "light"},
            )
