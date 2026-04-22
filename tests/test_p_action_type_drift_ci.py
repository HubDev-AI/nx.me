"""CI drift test: every GenerationAction.action_type_ledger must appear in the
credit RPC allowlist defined by migrations 0049 + 0066.

Fails loudly when:
  - A new descriptor is added without a corresponding migration extension, OR
  - A migration removes a type that a descriptor still references.

This is a static parse test — no DB required.
"""

from __future__ import annotations

import re
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parent.parent
_MIGRATIONS_DIR = _REPO_ROOT / "app" / "migrations"

# Migration files that define or extend the action_type allowlist.
_ALLOWLIST_MIGRATIONS = [
    "0049_credit_rpcs.sql",
    "0066_credit_rpcs_action_type_makeup.sql",
]


def _parse_allowlist_from_migration(migration_file: Path) -> set[str]:
    """Extract quoted strings from `NOT IN (...)` clauses in the migration SQL."""
    text = migration_file.read_text()
    # Match: NOT IN ('x', 'y', 'z')
    matches = re.findall(r"NOT IN\s*\(([^)]+)\)", text, re.IGNORECASE)
    found: set[str] = set()
    for group in matches:
        # Extract individual quoted strings
        found.update(re.findall(r"'([^']+)'", group))
    return found


def _build_migration_allowlist() -> set[str]:
    result: set[str] = set()
    for name in _ALLOWLIST_MIGRATIONS:
        path = _MIGRATIONS_DIR / name
        assert path.exists(), f"Migration not found: {path}"
        result |= _parse_allowlist_from_migration(path)
    return result


class TestActionTypeDriftCI:
    def test_all_descriptor_ledger_values_in_migration_allowlist(self):
        """Every action_type_ledger value must appear in the migration allowlist.

        If this test fails it means a new GenerationAction was added without
        a migration extending the credit_reserve RPC allowlist.
        """
        from app.generation.actions import all_actions

        allowlist = _build_migration_allowlist()
        for action in all_actions():
            assert action.action_type_ledger in allowlist, (
                f"GenerationAction(slug={action.slug!r}) has action_type_ledger="
                f"{action.action_type_ledger!r} which is NOT in the credit RPC "
                f"allowlist ({sorted(allowlist)}). "
                f"Add a migration extending NOT IN (..., {action.action_type_ledger!r}) "
                f"before registering this action."
            )

    def test_migration_allowlist_non_empty(self):
        allowlist = _build_migration_allowlist()
        assert "glowup" in allowlist
        assert "makeup" in allowlist

    def test_ada_message_in_allowlist_but_not_a_descriptor(self):
        """ada_message is an allowlisted action_type for the advisor but has no
        GenerationAction descriptor — this is intentional."""
        from app.generation.actions import all_actions

        allowlist = _build_migration_allowlist()
        assert "ada_message" in allowlist
        descriptor_ledgers = {a.action_type_ledger for a in all_actions()}
        assert "ada_message" not in descriptor_ledgers
