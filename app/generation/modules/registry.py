"""Module registry — discovers and returns active transformation modules."""
from __future__ import annotations

from app.generation.modules.base import TransformationModule

_MODULES: dict[str, TransformationModule] = {}


def register(module: TransformationModule) -> None:
    """Register a transformation module."""
    _MODULES[module.slug] = module


def get_active_modules(
    analysis_result,
    enabled_slugs: list[str],
) -> list[TransformationModule]:
    """Return modules that are both enabled and applicable."""
    return [
        m for slug, m in _MODULES.items()
        if slug in enabled_slugs and m.is_applicable(analysis_result)
    ]
