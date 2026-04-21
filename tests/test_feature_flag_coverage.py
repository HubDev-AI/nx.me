"""Router-coverage test for app-wide feature gates.

Statically scans router files for the expected
``Depends(require_app_feature("<flag>"))`` declaration on the router itself,
not on individual routes. Fails CI if a watched router is missing its gate
or the gate's flag name drifts.

Why this exists
---------------
``require_app_feature`` lives in ``app/api/deps.py`` and raises
``403 FEATURE_DISABLED`` when the named flag is off. The contract is that
**flag-gated routers carry the dep at the router prefix** so adding a new
route to the router automatically inherits the gate.

The allowlist below is the explicit declaration of "which routers must be
gated on which flag." Adding a new flag-gated router is a one-line edit
here, visible in code review. Routers NOT in the allowlist are intentionally
ungated (auth, health, features, users, uploads, etc.) — they're either
public or have per-route auth that doesn't depend on a global flag.

When this test fails
--------------------
- ``Missing gate``  → add ``Depends(require_app_feature("<flag>"))`` to the
  router's ``dependencies=`` list at the top of the file.
- ``Wrong flag``    → the router was gated on the wrong flag name; verify
  intent and either fix the gate or update the allowlist.
- ``Refactor drift`` → if router construction moved to a programmatic
  builder, update the regex below or drop the file from the allowlist with
  a justification comment.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_API = REPO_ROOT / "app" / "api"

# Router file (relative to repo root) → expected flag name.
# Adding a new flag-gated router? Add one line here AND the
# `Depends(require_app_feature("<flag>"))` declaration at the router
# prefix. Both halves are needed: this test guards the router side; the
# matching mobile capability + grep guard guards the UI side.
FLAG_GATED_ROUTERS: dict[str, str] = {
    "app/api/posts.py": "social_enabled",
    "app/api/social.py": "social_enabled",
    "app/api/blocks.py": "social_enabled",
    "app/api/advisor.py": "advisor_enabled",
    "app/api/makeup.py": "makeup_enabled",
}

# Routers NOT in the allowlist are ungated by design. Listed here for
# review-time clarity — if a new router lands and isn't covered by either
# list, reviewers should ask why.
EXPECTED_UNGATED_ROUTERS: frozenset[str] = frozenset(
    {
        "app/api/__init__.py",
        "app/api/admin.py",
        "app/api/auth.py",
        "app/api/deps.py",
        "app/api/entitlement.py",
        "app/api/errors.py",
        "app/api/features.py",
        "app/api/glowup.py",
        "app/api/health.py",
        "app/api/jobs.py",
        "app/api/public.py",
        "app/api/refund.py",
        "app/api/uploads.py",
        "app/api/user_consent.py",
        "app/api/users.py",
        "app/api/webhooks.py",
    }
)

# Captures the ``APIRouter(...)`` constructor call and its arguments,
# stopping at the matching closing paren. The router ``dependencies=``
# list lives inside this body.
_ROUTER_BODY_RE = re.compile(
    r"APIRouter\s*\(\s*(.+?)\n\)",
    re.DOTALL,
)

# Captures any ``Depends(require_app_feature("<name>"))`` argument. The
# router decl may contain other deps (e.g. ``Depends(rate_limit)``); the
# capture group reads only the flag string.
_REQUIRE_FEATURE_RE = re.compile(
    r"Depends\s*\(\s*require_app_feature\s*\(\s*[\"']([^\"']+)[\"']\s*\)\s*\)"
)


def _read_router_body(repo_relative: str) -> str:
    path = REPO_ROOT / repo_relative
    if not path.is_file():
        raise AssertionError(
            f"Router file in FLAG_GATED_ROUTERS does not exist: {repo_relative}"
        )
    source = path.read_text()
    match = _ROUTER_BODY_RE.search(source)
    if not match:
        raise AssertionError(
            f"Could not find APIRouter(...) constructor in {repo_relative}. "
            f"If router construction moved to a builder/factory, update the "
            f"regex in tests/test_feature_flag_coverage.py."
        )
    return match.group(1)


def _gates_in_router(router_body: str) -> set[str]:
    return {m.group(1) for m in _REQUIRE_FEATURE_RE.finditer(router_body)}


# ---------------------------------------------------------------------------
# Happy paths — every allowlisted router carries the expected gate.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "router_file,expected_flag",
    sorted(FLAG_GATED_ROUTERS.items()),
)
def test_router_carries_required_gate(router_file: str, expected_flag: str):
    body = _read_router_body(router_file)
    gates = _gates_in_router(body)
    assert expected_flag in gates, (
        f"{router_file} is missing Depends(require_app_feature({expected_flag!r})) "
        f"in its router declaration. Found gates: {sorted(gates) or 'none'}.\n"
        f"Add it to the APIRouter(prefix=..., dependencies=[...]) call."
    )


# ---------------------------------------------------------------------------
# Drift detection — both directions.
# ---------------------------------------------------------------------------


def test_drift_detection_missing_gate_in_fake_source():
    """A router body lacking the dep should fail _gates_in_router lookup."""
    fake = (
        '    prefix="/posts",\n'
        '    tags=["posts"],\n'
        "    dependencies=[Depends(get_current_user)],\n"
    )
    gates = _gates_in_router(fake)
    assert "social_enabled" not in gates


def test_drift_detection_wrong_flag_in_fake_source():
    """A router body gated on the wrong flag name should be detected."""
    fake = (
        '    prefix="/posts",\n'
        '    tags=["posts"],\n'
        '    dependencies=[Depends(require_app_feature("sozial_enabled"))],\n'
    )
    gates = _gates_in_router(fake)
    # The (typo'd) flag string is captured verbatim; the per-router test
    # would fail because "social_enabled" is not in {"sozial_enabled"}.
    assert "social_enabled" not in gates
    assert "sozial_enabled" in gates


def test_router_body_extraction_rejects_unparseable_source():
    """If APIRouter(...) is missing the regex raises with a clear message."""
    bogus_path = REPO_ROOT / "app" / "api" / "__init__.py"
    if not bogus_path.is_file() or "APIRouter" in bogus_path.read_text():
        pytest.skip("Need a router-free api/ file to assert the negative case.")
    with pytest.raises(AssertionError, match="Could not find APIRouter"):
        _read_router_body("app/api/__init__.py")


# ---------------------------------------------------------------------------
# Inventory check — every Python file in app/api/ should be in exactly one
# of FLAG_GATED_ROUTERS or EXPECTED_UNGATED_ROUTERS. New router files force
# a one-line review decision instead of slipping in unannounced.
# ---------------------------------------------------------------------------


def test_no_router_file_is_unaccounted_for():
    declared = set(FLAG_GATED_ROUTERS.keys()) | EXPECTED_UNGATED_ROUTERS
    discovered = {
        f"app/api/{p.name}"
        for p in APP_API.iterdir()
        if p.is_file() and p.suffix == ".py"
    }
    new_files = discovered - declared
    removed_files = declared - discovered
    assert not new_files, (
        f"New router file(s) detected with no coverage decision: "
        f"{sorted(new_files)}.\nAdd each to FLAG_GATED_ROUTERS (with the "
        f"required flag) or EXPECTED_UNGATED_ROUTERS (with intent)."
    )
    assert not removed_files, (
        f"Allowlist references file(s) that no longer exist: "
        f"{sorted(removed_files)}.\nRemove them from FLAG_GATED_ROUTERS / "
        f"EXPECTED_UNGATED_ROUTERS."
    )
