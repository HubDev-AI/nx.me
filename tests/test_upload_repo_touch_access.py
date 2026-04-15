"""Tests for ``upload_repo.get_by_id`` / ``get_by_id_for_owner_check``
``touch_access`` semantics.

Background: Q19 of the glowup-tier3 spec says upload retention is a rolling
30-day clock that refreshes when the user returns. Previously every read
touched ``last_accessed_at`` — including worker reads during generation, which
are not user-initiated. The ``touch_access`` kwarg lets callers opt out.

These tests pin:

- Default (``True``) still fires the update (existing user-facing behaviour).
- Explicit ``False`` skips the update (new worker-facing behaviour).
- Both default and explicit ``True`` behave identically.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.repositories.upload_repo import UploadRepository


def _build_repo_and_capture_updates():
    sb = MagicMock()
    update_calls: list[dict] = []

    def fake_update(payload):
        update_calls.append(payload)
        # Return a chain that terminates at .execute() (no return needed for update path).
        eq_chain = MagicMock()
        eq_chain.eq.return_value = eq_chain
        eq_chain.execute.return_value = None
        return eq_chain

    table = MagicMock()
    table.update.side_effect = fake_update

    select_chain = MagicMock()
    select_chain.eq.return_value = select_chain
    select_chain.maybe_single.return_value.execute.return_value = MagicMock(
        data={"id": "u-1", "user_id": "user-1", "image_url": "raw/x.jpg"}
    )
    table.select.return_value = select_chain

    sb.table.return_value = table
    return UploadRepository(sb), update_calls


class TestGetByIdTouchAccess:
    def test_default_true_fires_update(self):
        repo, update_calls = _build_repo_and_capture_updates()
        repo.get_by_id("u-1")
        assert len(update_calls) == 1
        assert "last_accessed_at" in update_calls[0]

    def test_explicit_true_fires_update(self):
        repo, update_calls = _build_repo_and_capture_updates()
        repo.get_by_id("u-1", touch_access=True)
        assert len(update_calls) == 1

    def test_false_skips_update(self):
        repo, update_calls = _build_repo_and_capture_updates()
        repo.get_by_id("u-1", touch_access=False)
        assert update_calls == []

    def test_false_still_returns_row(self):
        repo, _ = _build_repo_and_capture_updates()
        result = repo.get_by_id("u-1", touch_access=False)
        assert result is not None
        assert result["id"] == "u-1"


class TestGetByIdForOwnerCheckTouchAccess:
    def test_default_true_fires_update(self):
        repo, update_calls = _build_repo_and_capture_updates()
        repo.get_by_id_for_owner_check("u-1", "user-1")
        assert len(update_calls) == 1
        assert "last_accessed_at" in update_calls[0]

    def test_false_skips_update(self):
        repo, update_calls = _build_repo_and_capture_updates()
        repo.get_by_id_for_owner_check("u-1", "user-1", touch_access=False)
        assert update_calls == []
