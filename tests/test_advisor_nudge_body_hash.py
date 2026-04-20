"""Body-hash dedup — ``AdvisorRepository.find_duplicate_body``.

Plan 2026-04-20-001 Unit 3. Covers the repo method's query shape and
return contract. Scheduler-level dedup logic is in
``test_advisor_nudge_post_glowup.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.repositories.advisor_repo import AdvisorRepository


_SINCE = datetime(2026, 3, 21, 0, 0, 0, tzinfo=timezone.utc)
_SINCE_ISO = _SINCE.isoformat()
_USER_ID = "user-abc"
_BODY_HASH = "a" * 64


def _build_repo(rows: list[dict] | None) -> tuple[AdvisorRepository, MagicMock]:
    """Return (repo, supabase_mock) with leaf chain wired to return rows."""
    sb = MagicMock()
    table = sb.table.return_value
    select = table.select.return_value
    eq1 = select.eq.return_value
    eq2 = eq1.eq.return_value
    gte = eq2.gte.return_value
    leaf = gte.limit.return_value
    leaf.execute.return_value.data = rows
    return AdvisorRepository(sb), sb


class TestFindDuplicateBodyQueryShape:
    def test_selects_id_column(self):
        """Query selects only ``id`` — minimal projection for existence check."""
        repo, sb = _build_repo([])
        repo.find_duplicate_body(_USER_ID, _BODY_HASH, _SINCE)
        sb.table.return_value.select.assert_called_with("id")

    def test_filters_by_user_id(self):
        """First eq filter is on ``user_id``."""
        repo, sb = _build_repo([])
        repo.find_duplicate_body(_USER_ID, _BODY_HASH, _SINCE)
        sb.table.return_value.select.return_value.eq.assert_called_with(
            "user_id", _USER_ID
        )

    def test_filters_by_body_hash(self):
        """Second eq filter is on ``body_hash``."""
        repo, sb = _build_repo([])
        repo.find_duplicate_body(_USER_ID, _BODY_HASH, _SINCE)
        sb.table.return_value.select.return_value.eq.return_value.eq.assert_called_with(
            "body_hash", _BODY_HASH
        )

    def test_gte_filter_uses_since_isoformat(self):
        """gte filter uses ``created_at`` and ``since.isoformat()``."""
        repo, sb = _build_repo([])
        repo.find_duplicate_body(_USER_ID, _BODY_HASH, _SINCE)
        (
            sb.table.return_value.select.return_value.eq.return_value.eq.return_value.gte.assert_called_with(
                "created_at", _SINCE_ISO
            )
        )

    def test_limit_1(self):
        """Query limits to 1 row — existence check, not a full scan."""
        repo, sb = _build_repo([])
        repo.find_duplicate_body(_USER_ID, _BODY_HASH, _SINCE)
        (
            sb.table.return_value.select.return_value.eq.return_value.eq.return_value.gte.return_value.limit.assert_called_with(
                1
            )
        )


class TestFindDuplicateBodyReturnContract:
    def test_returns_true_when_row_exists(self):
        """A matching row → True."""
        repo, _ = _build_repo([{"id": "row-1"}])
        assert repo.find_duplicate_body(_USER_ID, _BODY_HASH, _SINCE) is True

    def test_returns_false_when_no_rows(self):
        """Empty result → False."""
        repo, _ = _build_repo([])
        assert repo.find_duplicate_body(_USER_ID, _BODY_HASH, _SINCE) is False

    def test_returns_false_when_data_none(self):
        """``execute().data is None`` → False."""
        repo, _ = _build_repo(None)
        assert repo.find_duplicate_body(_USER_ID, _BODY_HASH, _SINCE) is False
