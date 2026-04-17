"""Cursor validation in AdvisorRepository.get_messages_page.

Pins behaviour that malformed or filter-smuggling cursors raise ``ValueError``
(which the route maps to HTTP 400), rather than silently breaking PostgREST
filter grammar at the `or_()` call.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.repositories.advisor_repo import AdvisorRepository


def _build_repo() -> AdvisorRepository:
    sb = MagicMock()
    # Chain returns enough to reach `.execute().data`.
    chain = sb.table.return_value.select.return_value.eq.return_value.is_.return_value
    chain = chain.order.return_value.order.return_value.limit.return_value
    chain.or_.return_value.execute.return_value.data = []
    chain.execute.return_value.data = []
    return AdvisorRepository(sb)


class TestMalformedCursor:
    def test_missing_delimiter_raises(self):
        repo = _build_repo()
        with pytest.raises(ValueError, match="Malformed cursor"):
            repo.get_messages_page("conv-1", 50, cursor="no-pipe-here")

    def test_empty_created_at_raises(self):
        repo = _build_repo()
        with pytest.raises(ValueError, match="Malformed cursor"):
            repo.get_messages_page("conv-1", 50, cursor="|abc")

    def test_empty_id_raises(self):
        repo = _build_repo()
        with pytest.raises(ValueError, match="Malformed cursor"):
            repo.get_messages_page("conv-1", 50, cursor="2026-04-15T10:00:00Z|")

    def test_comma_in_cursor_raises(self):
        """Comma would break PostgREST .or_() filter grammar."""
        repo = _build_repo()
        with pytest.raises(ValueError, match="illegal character"):
            repo.get_messages_page("conv-1", 50, cursor="2026-04-15T10:00:00Z,evil|abc")

    def test_paren_in_cursor_raises(self):
        repo = _build_repo()
        with pytest.raises(ValueError, match="illegal character"):
            repo.get_messages_page("conv-1", 50, cursor="2026-04-15T10:00:00Z|abc)")

    def test_quote_in_cursor_raises(self):
        repo = _build_repo()
        with pytest.raises(ValueError, match="illegal character"):
            repo.get_messages_page("conv-1", 50, cursor="2026-04-15T10:00:00Z|abc'")


class TestValidCursor:
    def test_iso_ts_pipe_uuid_accepted(self):
        repo = _build_repo()
        # Should not raise.
        repo.get_messages_page(
            "conv-1",
            50,
            cursor="2026-04-15T10:00:00+00:00|11111111-2222-3333-4444-555555555555",
        )

    def test_none_cursor_skips_validation(self):
        repo = _build_repo()
        repo.get_messages_page("conv-1", 50, cursor=None)

    def test_empty_string_cursor_is_treated_as_none(self):
        repo = _build_repo()
        # Empty string is falsy — validation path is skipped (no filter applied).
        repo.get_messages_page("conv-1", 50, cursor="")
