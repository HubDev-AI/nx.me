"""Shared persona source — SOUL.md loaded once, used by chat, nudges, summary.

Keeping the load in a dedicated module avoids duplicating the file read and
prevents voice drift between the three generation paths (spec §1, §12).
"""

from __future__ import annotations

from pathlib import Path

_SOUL_MD_PATH = Path(__file__).parent / "SOUL.md"

try:
    SOUL_MD: str = _SOUL_MD_PATH.read_text(encoding="utf-8")
except FileNotFoundError as exc:
    raise RuntimeError(
        f"SOUL.md not found at {_SOUL_MD_PATH}. Advisor module cannot start."
    ) from exc


def get_soul_md() -> str:
    """Return the full SOUL.md persona text."""
    return SOUL_MD
