"""Reverse-chronological pagination for advisor conversation history.

Pins the contract that:

- Initial ``get_conversation_history_page(cursor=None)`` returns the
  NEWEST ``limit`` messages, in ascending (oldest → newest) order.
- ``next_cursor`` anchors the next page to rows OLDER than the current
  page's oldest row.
- A follow-up call with that cursor returns the next page of older
  messages, again in ascending order.

The repository method queries newest-first and reverses the batch to
ascending before returning, so the service layer sees ASC rows and
does the ``has_more`` / cursor bookkeeping against that ordering.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.advisor.service import AdvisorService
from app.repositories.advisor_repo import AdvisorRepository


def _make_row(index: int) -> dict[str, Any]:
    """Construct a message row whose ordinal encodes its chronology.

    ``index`` is treated as the message's position in time — lower
    means older. The created_at string sorts lexicographically in the
    same order as real ISO timestamps would.
    """
    return {
        "id": f"msg-{index:04d}",
        "role": "user" if index % 2 == 0 else "assistant",
        "content": f"msg #{index}",
        "created_at": f"2026-04-17T00:00:{index:02d}+00:00",
    }


class _StubRepo:
    """In-memory repository stub with the ordering semantics the real
    PostgREST query guarantees — newest-first DESC with ``.lt.`` cursor.

    We only implement the chat-messages paths used by AdvisorService."""

    def __init__(self, rows: list[dict[str, Any]]):
        # Store newest-first so slicing mirrors the real query order.
        self._rows = sorted(rows, key=lambda r: r["created_at"], reverse=True)

    def get_messages_page(
        self,
        conversation_id: str,
        fetch_limit: int,
        cursor: str | None = None,
    ) -> list[dict[str, Any]]:
        del conversation_id  # stub ignores tenancy
        rows = self._rows
        if cursor:
            cursor_ts, cursor_id = cursor.split("|", 1)
            rows = [
                r
                for r in rows
                if r["created_at"] < cursor_ts
                or (r["created_at"] == cursor_ts and r["id"] < cursor_id)
            ]
        # Mirror the real repo: return ASC order, already capped at fetch_limit.
        page = list(reversed(rows[:fetch_limit]))
        return page


class _FixedConversationStub(AdvisorService):
    """AdvisorService with `_get_or_create_conversation` pinned so the
    test exercises only the pagination math, not the conversation
    lookup path."""

    def __init__(self, repo: _StubRepo):
        self._repo = repo  # type: ignore[assignment]
        self._conversation_id = str(uuid4())

    def _get_or_create_conversation(self, user_id):  # type: ignore[override]
        return {"id": self._conversation_id}


@pytest.mark.asyncio
async def test_initial_page_returns_newest_messages_ascending():
    """First load returns the last ``limit`` messages sorted ASC so the
    client can render oldest-at-top / newest-at-bottom directly."""
    repo = _StubRepo([_make_row(i) for i in range(1, 21)])  # 20 msgs
    svc = _FixedConversationStub(repo)

    result = await svc.get_conversation_history_page(uuid4(), limit=5)

    assert result["has_more"] is True
    returned = [m["id"] for m in result["messages"]]
    # Newest 5: msg-0016..0020, ascending.
    assert returned == [
        "msg-0016",
        "msg-0017",
        "msg-0018",
        "msg-0019",
        "msg-0020",
    ]
    # Cursor anchors the next page to "older than the OLDEST row" = msg-0016.
    assert result["next_cursor"] == "2026-04-17T00:00:16+00:00|msg-0016"


@pytest.mark.asyncio
async def test_follow_up_cursor_returns_older_messages_ascending():
    """The page after ``next_cursor`` is the NEXT batch of older
    messages, not newer ones, and stays in ascending order."""
    repo = _StubRepo([_make_row(i) for i in range(1, 21)])  # 20 msgs
    svc = _FixedConversationStub(repo)

    first = await svc.get_conversation_history_page(uuid4(), limit=5)
    assert first["next_cursor"] is not None
    second = await svc.get_conversation_history_page(
        uuid4(), limit=5, cursor=first["next_cursor"]
    )

    returned = [m["id"] for m in second["messages"]]
    # Next older 5 before msg-0016: msg-0011..0015, ascending.
    assert returned == [
        "msg-0011",
        "msg-0012",
        "msg-0013",
        "msg-0014",
        "msg-0015",
    ]
    assert second["has_more"] is True
    # Cursor now anchors to the oldest of this page — msg-0011.
    assert second["next_cursor"] == "2026-04-17T00:00:11+00:00|msg-0011"


@pytest.mark.asyncio
async def test_last_page_signals_has_more_false_and_no_cursor():
    """When no older rows remain, ``has_more`` is False and
    ``next_cursor`` is None — client stops paginating."""
    repo = _StubRepo([_make_row(i) for i in range(1, 8)])  # 7 msgs, limit=5
    svc = _FixedConversationStub(repo)

    first = await svc.get_conversation_history_page(uuid4(), limit=5)
    assert first["has_more"] is True
    second = await svc.get_conversation_history_page(
        uuid4(), limit=5, cursor=first["next_cursor"]
    )

    returned = [m["id"] for m in second["messages"]]
    # Only 2 older rows remain.
    assert returned == ["msg-0001", "msg-0002"]
    assert second["has_more"] is False
    assert second["next_cursor"] is None


@pytest.mark.asyncio
async def test_single_page_when_total_below_limit():
    """Total messages under the limit — all returned ASC, no cursor."""
    repo = _StubRepo([_make_row(i) for i in range(1, 4)])  # 3 msgs
    svc = _FixedConversationStub(repo)

    result = await svc.get_conversation_history_page(uuid4(), limit=5)

    returned = [m["id"] for m in result["messages"]]
    assert returned == ["msg-0001", "msg-0002", "msg-0003"]
    assert result["has_more"] is False
    assert result["next_cursor"] is None


class TestRepoReturnsAscendingAfterReverse:
    """Repository contract: query is newest-first DESC but the returned
    batch is flipped to ascending so service / API callers never see
    the raw DB order."""

    @staticmethod
    def _build_repo_with_rows(rows: list[dict[str, Any]]) -> AdvisorRepository:
        sb = MagicMock()
        chain = (
            sb.table.return_value.select.return_value.eq.return_value.is_.return_value
        )
        chain = chain.order.return_value.order.return_value.limit.return_value
        # No cursor path — plain `.execute()` returns the rows.
        chain.execute.return_value.data = rows
        # Cursor path (`.or_()`) returns the same stub for ordering verification.
        chain.or_.return_value.execute.return_value.data = rows
        return AdvisorRepository(sb)

    def test_reverses_db_order_to_ascending(self):
        # Emulate the real DB order: newest-first DESC.
        newest_first_rows = [_make_row(3), _make_row(2), _make_row(1)]
        repo = self._build_repo_with_rows(newest_first_rows)

        page = repo.get_messages_page("conv-1", 50)

        # Returned ascending.
        assert [r["id"] for r in page] == ["msg-0001", "msg-0002", "msg-0003"]
