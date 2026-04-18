"""purge_expired_username_reservations — nightly cleanup of stale reservations.

Availability logic already ignores expired rows; this purge is pure
table-hygiene that bounds table growth over years.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.workers.retention import purge_expired_username_reservations


def _build_supabase_with_delete_result(
    result_data: list[dict] | None,
) -> tuple[MagicMock, dict]:
    """Build a Supabase client mock whose delete-lt-execute chain returns result_data.

    Returns (supabase_mock, captured_calls) where captured_calls records the
    table name, the lt column/value, and the terminal execute call.
    """
    captured: dict = {}

    execute_result = MagicMock()
    execute_result.data = result_data

    lt_chain = MagicMock()
    lt_chain.execute = MagicMock(return_value=execute_result)

    def lt_capture(column: str, value: str) -> MagicMock:
        captured["lt_column"] = column
        captured["lt_value"] = value
        return lt_chain

    delete_chain = MagicMock()
    delete_chain.lt = MagicMock(side_effect=lt_capture)

    table_chain = MagicMock()
    table_chain.delete = MagicMock(return_value=delete_chain)

    def table_capture(name: str) -> MagicMock:
        captured["table"] = name
        return table_chain

    supabase = MagicMock()
    supabase.table = MagicMock(side_effect=table_capture)

    return supabase, captured


@pytest.mark.asyncio
async def test_purge_targets_username_reservations_with_lt_filter():
    """Calls .delete() on username_reservations and filters reserved_until < now (ISO)."""
    supabase, captured = _build_supabase_with_delete_result(
        [{"id": "r1"}, {"id": "r2"}, {"id": "r3"}]
    )

    deleted = await purge_expired_username_reservations(supabase)

    assert deleted == 3
    assert captured["table"] == "username_reservations"
    assert captured["lt_column"] == "reserved_until"
    # ISO 8601 UTC timestamp; sanity check shape rather than exact value.
    lt_value = captured["lt_value"]
    assert isinstance(lt_value, str)
    assert "T" in lt_value  # date/time separator
    assert lt_value.endswith("+00:00") or lt_value.endswith("Z")


@pytest.mark.asyncio
async def test_purge_returns_zero_when_nothing_to_delete():
    """Empty result (no expired rows) → returns 0 without raising."""
    supabase, _ = _build_supabase_with_delete_result([])

    deleted = await purge_expired_username_reservations(supabase)

    assert deleted == 0


@pytest.mark.asyncio
async def test_purge_tolerates_none_data():
    """Supabase client returning .data=None → returns 0, no exception."""
    supabase, _ = _build_supabase_with_delete_result(None)

    deleted = await purge_expired_username_reservations(supabase)

    assert deleted == 0
