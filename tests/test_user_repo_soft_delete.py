"""Regression tests for ``UserRepository.soft_delete`` scrubbing unique columns.

Before this fix, ``soft_delete`` only set ``deleted_at`` + ``username_reserved_until``,
leaving ``email`` and ``tiktok_open_id`` on the soft-deleted row. Re-signup with
the same email then failed with ``users_email_key`` unique-constraint violation.
Fix: scrub both identifier columns during soft-delete. Username is deliberately
preserved for the 180-day reservation window.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.repositories.user_repo import UserRepository


def _build_repo_and_capture_updates() -> tuple[UserRepository, list[dict]]:
    sb = MagicMock()
    update_calls: list[dict] = []

    def fake_update(payload: dict) -> MagicMock:
        update_calls.append(payload)
        chain = MagicMock()
        chain.eq.return_value = chain
        chain.is_.return_value = chain
        chain.execute.return_value = MagicMock(data=[{"id": "user-1"}])
        return chain

    table = MagicMock()
    table.update.side_effect = fake_update
    sb.table.return_value = table
    return UserRepository(sb), update_calls


class TestSoftDeleteScrubsUniqueColumns:
    def test_scrubs_email_and_tiktok_open_id(self):
        repo, update_calls = _build_repo_and_capture_updates()
        now = datetime.now(tz=timezone.utc)
        reserved_until = now + timedelta(days=180)

        repo.soft_delete("user-1", now, reserved_until)

        assert len(update_calls) == 1
        payload = update_calls[0]
        assert payload["email"] is None
        assert payload["tiktok_open_id"] is None

    def test_preserves_username_reservation_fields(self):
        repo, update_calls = _build_repo_and_capture_updates()
        now = datetime.now(tz=timezone.utc)
        reserved_until = now + timedelta(days=180)

        repo.soft_delete("user-1", now, reserved_until)

        payload = update_calls[0]
        assert payload["deleted_at"] == now.isoformat()
        assert payload["username_reserved_until"] == reserved_until.isoformat()
        assert "username" not in payload

    def test_returns_updated_rows(self):
        repo, _ = _build_repo_and_capture_updates()
        now = datetime.now(tz=timezone.utc)
        reserved_until = now + timedelta(days=180)

        result = repo.soft_delete("user-1", now, reserved_until)

        assert result == [{"id": "user-1"}]
