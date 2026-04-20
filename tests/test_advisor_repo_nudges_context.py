"""Unit-4 repo helper — ``AdvisorRepository.get_recent_nudges_for_context``.

Plan 2026-04-17-003 Unit 4 / Plan 2026-04-20-001 Unit 3.

Covers:

- Select set is now ``body, next_step_label, next_step_seed, created_at``
  (content + trigger columns dropped in Unit 3 migration).
- Filter chain: ``eq(user_id) -> gte(created_at, since_iso) -> order desc -> limit``.
- Read-only contract: the method never touches ``read_at`` (no update path).
- Empty result (``.data = None`` from supabase-py) returns ``[]``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.repositories.advisor_repo import AdvisorRepository


def _build_repo_with_data(
    rows: list[dict] | None,
) -> tuple[AdvisorRepository, MagicMock, MagicMock]:
    """Return (repo, supabase_mock, leaf_chain_mock) for direct chain assertions."""
    sb = MagicMock()
    # ``table(..).select(..).eq(..).gte(..).order(..).limit(..).execute()``
    table = sb.table.return_value
    select = table.select.return_value
    eq = select.eq.return_value
    gte = eq.gte.return_value
    order = gte.order.return_value
    leaf = order.limit.return_value
    leaf.execute.return_value.data = rows
    return AdvisorRepository(sb), sb, leaf


class TestQueryShape:
    def test_select_columns_are_body_next_step_label_next_step_seed_created_at(self):
        """Plan Unit 3 — repo selects exactly these four columns."""
        repo, sb, _leaf = _build_repo_with_data([])
        repo.get_recent_nudges_for_context(
            "user-1", limit=5, since_iso="2026-04-03T00:00:00+00:00"
        )
        sb.table.assert_called_with("advisor_nudges")
        sb.table.return_value.select.assert_called_with(
            "body, next_step_label, next_step_seed, created_at"
        )

    def test_filter_chain_uses_eq_then_gte(self):
        """Filter chain: eq(user_id) → gte(created_at, since) — user scoping and time window."""
        repo, sb, _leaf = _build_repo_with_data([])
        repo.get_recent_nudges_for_context(
            "user-1", limit=5, since_iso="2026-04-03T00:00:00+00:00"
        )
        sb.table.return_value.select.return_value.eq.assert_called_with(
            "user_id", "user-1"
        )
        sb.table.return_value.select.return_value.eq.return_value.gte.assert_called_with(
            "created_at", "2026-04-03T00:00:00+00:00"
        )

    def test_order_is_created_at_desc_newest_first(self):
        """Rows are ordered created_at desc so callers get newest-first without re-sorting."""
        repo, sb, _leaf = _build_repo_with_data([])
        repo.get_recent_nudges_for_context(
            "user-1", limit=5, since_iso="2026-04-03T00:00:00+00:00"
        )
        order_mock = sb.table.return_value.select.return_value.eq.return_value.gte.return_value.order
        order_mock.assert_called_with("created_at", desc=True)

    def test_limit_value_is_forwarded(self):
        """Repo honors the ``limit`` arg from the service layer config."""
        repo, sb, _leaf = _build_repo_with_data([])
        repo.get_recent_nudges_for_context(
            "user-1", limit=7, since_iso="2026-04-03T00:00:00+00:00"
        )
        limit_mock = sb.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit
        limit_mock.assert_called_with(7)

    def test_no_read_at_mutation(self):
        """Read-only contract: the repo method never calls ``.update(..)`` on advisor_nudges."""
        repo, sb, _leaf = _build_repo_with_data([])
        repo.get_recent_nudges_for_context(
            "user-1", limit=5, since_iso="2026-04-03T00:00:00+00:00"
        )
        calls = [str(c) for c in sb.table.return_value.mock_calls]
        assert not any(".update(" in c for c in calls), (
            f"get_recent_nudges_for_context must not call .update(): saw {calls!r}"
        )


class TestReturnShape:
    def test_returns_rows_when_data_present(self):
        """Rows from Supabase are passed through unchanged (newest first)."""
        rows = [
            {
                "body": "Your brow arch looks beautifully defined.",
                "next_step_label": "Ask Ada",
                "next_step_seed": "How can I keep my brows this defined?",
                "created_at": "2026-04-17T00:00:00+00:00",
            },
            {
                "body": "Softer jaw contouring reads really well here.",
                "next_step_label": "Tell me more",
                "next_step_seed": "What jaw contouring techniques work for my face shape?",
                "created_at": "2026-04-15T00:00:00+00:00",
            },
        ]
        repo, _sb, _leaf = _build_repo_with_data(rows)
        out = repo.get_recent_nudges_for_context(
            "user-1", limit=5, since_iso="2026-04-03T00:00:00+00:00"
        )
        assert out == rows

    def test_returns_empty_list_when_supabase_data_none(self):
        """``execute().data is None`` → ``[]`` (caller never sees ``None``)."""
        repo, _sb, _leaf = _build_repo_with_data(None)
        out = repo.get_recent_nudges_for_context(
            "user-1", limit=5, since_iso="2026-04-03T00:00:00+00:00"
        )
        assert out == []

    def test_returns_empty_list_when_no_rows_match_window(self):
        """Empty ``.data`` list → ``[]`` (the no-recent-nudges path)."""
        repo, _sb, _leaf = _build_repo_with_data([])
        out = repo.get_recent_nudges_for_context(
            "user-1", limit=5, since_iso="2026-04-03T00:00:00+00:00"
        )
        assert out == []
