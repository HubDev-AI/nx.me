"""Makeup preset registry — loads and validates the YAML preset catalogue.

Single source of truth for the preset ↔ fal mapping. Loaded once at startup
via ``load_presets()`` (singleton pattern). All callers access presets through
the registry functions; no code path reads the YAML after startup.

Startup contract: if the YAML is missing or malformed, ``load_presets()`` raises
so the lifespan hook can fail-fast before the server accepts traffic.
"""

from __future__ import annotations

import logging
from pathlib import Path
import yaml
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)

_VALID_INTENSITIES = frozenset({"subtle", "light", "medium", "bold"})

PRESETS_YAML_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "makeup_presets.yaml"


class PresetNotFound(KeyError):
    """Raised when a slug is not in the registry."""


class Preset(BaseModel):
    slug: str
    display_name: str
    fal_style: str
    thumbnail: str
    description: str
    supported_intensities: list[str]
    intensity_mapping: dict[str, str]
    mst_bin_blocklist: list[int] = []
    deprecated: bool = False

    @field_validator("supported_intensities")
    @classmethod
    def _validate_intensities(cls, v: list[str]) -> list[str]:
        bad = set(v) - _VALID_INTENSITIES
        if bad:
            raise ValueError(f"Unknown intensity values: {bad}")
        return v

    @field_validator("intensity_mapping")
    @classmethod
    def _validate_mapping_covers_supported(cls, v: dict[str, str], info) -> dict[str, str]:
        supported = set(info.data.get("supported_intensities", []))
        missing = supported - set(v.keys())
        if missing:
            raise ValueError(
                f"intensity_mapping is missing entries for supported_intensities: {missing}"
            )
        return v


class PresetRegistryModel(BaseModel):
    fal_endpoint_version: str
    presets: list[Preset]


class PresetRegistry:
    """Loaded registry — thin wrapper around a validated ``PresetRegistryModel``."""

    def __init__(self, model: PresetRegistryModel) -> None:
        self._model = model
        self._by_slug: dict[str, Preset] = {p.slug: p for p in model.presets}

    @property
    def fal_endpoint_version(self) -> str:
        return self._model.fal_endpoint_version

    def get_preset(self, slug: str) -> Preset | None:
        return self._by_slug.get(slug)

    def get_available_presets(self, mst_bin: int | None = None) -> list[Preset]:
        """Return non-deprecated presets, filtered by mst_bin blocklist when given."""
        return [
            p
            for p in self._model.presets
            if not p.deprecated and (mst_bin is None or mst_bin not in p.mst_bin_blocklist)
        ]

    def map_to_fal(self, preset_slug: str, our_intensity: str) -> tuple[str, str]:
        """Translate (preset_slug, our_intensity) to (fal_style, fal_intensity).

        Raises ``PresetNotFound`` for unknown slug.
        Raises ``KeyError`` when *our_intensity* has no mapping for the preset.
        """
        preset = self._by_slug.get(preset_slug)
        if preset is None:
            raise PresetNotFound(f"Unknown preset slug: {preset_slug!r}")
        fal_intensity = preset.intensity_mapping[our_intensity]
        return preset.fal_style, fal_intensity


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_registry: PresetRegistry | None = None


def load_presets(path: Path | None = None) -> PresetRegistry:
    """Load and validate the preset YAML, cache as singleton.

    Raises ``FileNotFoundError`` or ``pydantic.ValidationError`` on failure —
    callers (including the startup hook) must not silence these.
    """
    global _registry
    if _registry is not None:
        return _registry

    yaml_path = path or PRESETS_YAML_PATH
    raw = yaml.safe_load(yaml_path.read_text())
    model = PresetRegistryModel.model_validate(raw)
    _registry = PresetRegistry(model)
    logger.info(
        "Makeup preset registry loaded: %d presets from %s",
        len(model.presets),
        yaml_path.name,
    )
    return _registry


def _reset_registry() -> None:
    """Test helper — reset singleton so tests can load custom YAML."""
    global _registry
    _registry = None


def get_preset(slug: str) -> Preset | None:
    return load_presets().get_preset(slug)


def get_available_presets(mst_bin: int | None = None) -> list[Preset]:
    return load_presets().get_available_presets(mst_bin)


def map_to_fal(preset_slug: str, our_intensity: str) -> tuple[str, str]:
    return load_presets().map_to_fal(preset_slug, our_intensity)
