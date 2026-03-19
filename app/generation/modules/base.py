"""Transformation module protocol — pluggable feature types.

Each transformation (styling, teeth, eyes, etc.) is a module that
contributes prompt fragments and parameter adjustments. Adding a new
feature = new module file + config flag. No pipeline changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class TransformationOutput:
    """What a module contributes to the generation prompt."""

    prompt_fragment: str
    negative_fragment: str
    keywords_used: list[str] = field(default_factory=list)
    wow_weight: float = 1.0


class TransformationModule(Protocol):
    """A pluggable transformation type."""

    @property
    def slug(self) -> str:
        ...

    @property
    def display_name(self) -> str:
        ...

    def is_applicable(self, analysis_result) -> bool:
        ...

    def build_output(self, analysis_result, mode: str) -> TransformationOutput:
        ...

    def get_allowed_keywords(self) -> frozenset[str]:
        ...

    def get_blocked_keywords(self) -> frozenset[str]:
        ...

    def adjust_params(self, base_params: dict) -> dict:
        ...
