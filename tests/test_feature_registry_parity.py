"""Feature-flag registry parity between backend and mobile.

Backend source of truth: ``app.features.FeatureFlags`` pydantic model.
Mobile mirror: ``FeatureFlags`` TypeScript interface in
``mobile/constants/features.ts``.

This test regex-parses the TypeScript interface body and asserts its field
set equals ``FeatureFlags.model_fields.keys()``. Drift in either direction
fails CI.

When this test fails:
- Missing on mobile → add field to the ``FeatureFlags`` interface and default
  to ``PROD_DEFAULT_FEATURES`` in ``mobile/constants/features.ts``.
- Missing on backend → add field to ``app.features.FeatureFlags`` + a
  config.setting entry + default in ``app/.env.example``.

Refactoring the mobile interface shape (for example, switching to
``type FeatureFlags = {...}``) breaks the regex on purpose: the source shape
is part of the contract. Update the regex below if the shape intentionally
changes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.features import FeatureFlags

# Repo layout: this file lives at <repo>/tests/, mobile file at <repo>/mobile/constants/features.ts
REPO_ROOT = Path(__file__).resolve().parent.parent
MOBILE_FEATURES_PATH = REPO_ROOT / "mobile" / "constants" / "features.ts"

# Matches `export interface FeatureFlags { ... }` with arbitrary whitespace
# and newlines inside the body. `re.DOTALL` lets `.` cross line boundaries.
_INTERFACE_RE = re.compile(
    r"export\s+interface\s+FeatureFlags\s*\{(.+?)\}",
    re.DOTALL,
)

# Matches a single `<name>: boolean;` field line. Leading whitespace is
# tolerated. Non-boolean fields would signal an unintended shape change and
# are ignored here (the equality assertion will then surface the mismatch).
_FIELD_RE = re.compile(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*boolean\s*;", re.MULTILINE)


def _extract_mobile_flag_names(source: str) -> set[str]:
    match = _INTERFACE_RE.search(source)
    if not match:
        raise AssertionError(
            "Could not find `export interface FeatureFlags { ... }` in the "
            "mobile features file. If the interface was renamed or converted "
            "to a type alias, update the regex in tests/test_feature_registry_parity.py."
        )
    body = match.group(1)
    names = {m.group(1) for m in _FIELD_RE.finditer(body)}
    if not names:
        raise AssertionError(
            "Found the FeatureFlags interface but parsed zero boolean fields. "
            "Check the interface body for non-boolean field types that the "
            "parity test does not cover."
        )
    return names


def _backend_flag_names() -> set[str]:
    return set(FeatureFlags.model_fields.keys())


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_mobile_features_file_exists():
    assert MOBILE_FEATURES_PATH.is_file(), (
        f"Mobile FeatureFlags mirror not found at {MOBILE_FEATURES_PATH.relative_to(REPO_ROOT)}"
    )


def test_backend_and_mobile_registries_match():
    mobile = _extract_mobile_flag_names(MOBILE_FEATURES_PATH.read_text())
    backend = _backend_flag_names()

    missing_on_mobile = backend - mobile
    missing_on_backend = mobile - backend

    assert not missing_on_mobile and not missing_on_backend, (
        "Feature-flag registry drift:\n"
        f"  missing on mobile (add to mobile/constants/features.ts): {sorted(missing_on_mobile) or 'none'}\n"
        f"  missing on backend (add to app/features/__init__.py):    {sorted(missing_on_backend) or 'none'}"
    )


# ---------------------------------------------------------------------------
# Drift detection — both directions, using in-memory source strings so the
# test is hermetic and doesn't require touching the on-disk mirror.
# ---------------------------------------------------------------------------


def test_drift_detection_mobile_missing_field():
    fake_source = (
        "export interface FeatureFlags {\n"
        "  auth_required: boolean;\n"
        # Intentionally omitting social_enabled to simulate drift.
        "  share_enabled: boolean;\n"
        "  onboarding_enabled: boolean;\n"
        "  advisor_enabled: boolean;\n"
        "}\n"
    )
    mobile = _extract_mobile_flag_names(fake_source)
    assert "social_enabled" not in mobile
    assert "social_enabled" in _backend_flag_names()


def test_drift_detection_mobile_extra_field():
    fake_source = (
        "export interface FeatureFlags {\n"
        "  auth_required: boolean;\n"
        "  social_enabled: boolean;\n"
        "  share_enabled: boolean;\n"
        "  onboarding_enabled: boolean;\n"
        "  advisor_enabled: boolean;\n"
        "  phantom_flag: boolean;\n"
        "}\n"
    )
    mobile = _extract_mobile_flag_names(fake_source)
    assert "phantom_flag" in mobile
    assert "phantom_flag" not in _backend_flag_names()


def test_malformed_interface_body_is_rejected():
    fake_source = "export interface Unrelated { foo: boolean; }\n"
    with pytest.raises(AssertionError, match="Could not find"):
        _extract_mobile_flag_names(fake_source)


def test_empty_interface_body_is_rejected():
    fake_source = "export interface FeatureFlags {\n  /* no boolean fields */\n}\n"
    with pytest.raises(AssertionError, match="parsed zero boolean fields"):
        _extract_mobile_flag_names(fake_source)
