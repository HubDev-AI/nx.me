"""reconcile_orphaned_users — compensating cleanup for delete_account partial failure.

Covers the window where auth.admin.delete_user succeeded (step 3 of the
endpoint) but DELETE FROM users failed (step 5). The orphan public.users
row has no working auth identity and would survive forever without this
sweeper.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.workers.retention import reconcile_orphaned_users


def _build_supabase(
    public_ids: list[str],
    auth_ids_pages: list[list[str]],
) -> tuple[MagicMock, list[list[str]]]:
    """Mock Supabase whose public.users contains ``public_ids`` and
    auth.admin.list_users returns ``auth_ids_pages`` across paginated calls.

    Returns (supabase, captured_deletes) where captured_deletes records
    the id lists passed to .delete().in_("id", ...).
    """
    captured_deletes: list[list[str]] = []

    users_select_result = MagicMock()
    users_select_result.data = [{"id": uid} for uid in public_ids]
    users_select_chain = MagicMock()
    users_select_chain.execute = MagicMock(return_value=users_select_result)

    users_delete_chain = MagicMock()

    def in_capture(column: str, ids: list[str]) -> MagicMock:
        captured_deletes.append(list(ids))
        chain = MagicMock()
        chain.execute = MagicMock(return_value=MagicMock(data=[{"id": i} for i in ids]))
        return chain

    users_delete_chain.in_ = MagicMock(side_effect=in_capture)

    users_table = MagicMock()
    users_table.select = MagicMock(return_value=users_select_chain)
    users_table.delete = MagicMock(return_value=users_delete_chain)

    page_iter = iter(auth_ids_pages)

    def list_users(page: int, per_page: int):
        try:
            page_ids = next(page_iter)
        except StopIteration:
            return SimpleNamespace(users=[])
        return SimpleNamespace(users=[SimpleNamespace(id=uid) for uid in page_ids])

    supabase = MagicMock()
    supabase.table = MagicMock(return_value=users_table)
    supabase.auth.admin.list_users = MagicMock(side_effect=list_users)

    return supabase, captured_deletes


@pytest.mark.asyncio
async def test_no_orphans_returns_zero():
    """Every public.users row has a matching auth identity → no-op."""
    supabase, captured = _build_supabase(
        public_ids=["u-1", "u-2"],
        auth_ids_pages=[["u-1", "u-2"]],
    )
    deleted = await reconcile_orphaned_users(supabase)
    assert deleted == 0
    assert captured == []


@pytest.mark.asyncio
async def test_empty_users_returns_zero_without_auth_probe():
    """Empty public.users → skip auth probe entirely, return 0."""
    supabase, captured = _build_supabase(public_ids=[], auth_ids_pages=[])
    deleted = await reconcile_orphaned_users(supabase)
    assert deleted == 0
    assert captured == []
    supabase.auth.admin.list_users.assert_not_called()


@pytest.mark.asyncio
async def test_orphan_with_missing_auth_identity_is_deleted():
    """public.users row whose id is not in auth.users → deleted in batch."""
    supabase, captured = _build_supabase(
        public_ids=["u-1", "u-2", "u-3"],
        auth_ids_pages=[["u-1", "u-3"]],
    )
    deleted = await reconcile_orphaned_users(supabase)
    assert deleted == 1
    assert captured == [["u-2"]]


@pytest.mark.asyncio
async def test_multiple_orphans_deleted_together():
    """All missing auth identities deleted in a single batch call."""
    supabase, captured = _build_supabase(
        public_ids=["u-1", "u-2", "u-3", "u-4"],
        auth_ids_pages=[["u-1", "u-2"]],
    )
    deleted = await reconcile_orphaned_users(supabase)
    assert deleted == 2
    assert sorted(captured[0]) == ["u-3", "u-4"]
