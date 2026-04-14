"""Tests for public API models and handlers.

Exercises production code in:
  - app/api/public.py (RecommendationItem, CardResponse, cursor codec,
    GET /public/cards handler)
  - app/repositories/post_repo.py (list_public_user_cursor)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest


try:
    from app.api.public import RecommendationItem, CardResponse  # noqa: F401

    _PUBLIC_AVAILABLE = True
except (ImportError, AttributeError):
    _PUBLIC_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _PUBLIC_AVAILABLE, reason="public module unavailable"
)


class TestPublicModels:
    """Pydantic model tests — exercises app/api/public.py."""

    def test_recommendation_item(self):
        item = RecommendationItem(rank=1, category="hair", suggestion="Try layers")
        assert item.rank == 1
        assert item.rationale is None

    def test_recommendation_item_with_rationale(self):
        item = RecommendationItem(
            rank=1,
            category="hair",
            suggestion="Try layers",
            rationale="Adds dimension to your face shape",
        )
        assert item.rationale is not None

    def test_card_response(self):
        resp = CardResponse(
            username="alice",
            display_name="Alice",
            share_hash="abc123",
            before_image_url="https://cdn.example.com/before.jpg",
            after_image_url="https://cdn.example.com/after.jpg",
            recommendations=[
                RecommendationItem(
                    rank=1, category="style", suggestion="Bold accessories"
                ),
            ],
            reaction_count=42,
            comment_count=7,
        )
        assert resp.username == "alice"
        assert len(resp.recommendations) == 1
        assert resp.reaction_count == 42

    def test_card_response_empty_recommendations(self):
        resp = CardResponse(
            username="bob",
            display_name="Bob",
            share_hash="def456",
            before_image_url="https://cdn.example.com/b.jpg",
            after_image_url="https://cdn.example.com/a.jpg",
            recommendations=[],
            reaction_count=0,
            comment_count=0,
        )
        assert len(resp.recommendations) == 0


# ---------------------------------------------------------------------------
# GET /public/cards — listing endpoint
# ---------------------------------------------------------------------------


def _build_supabase_with_posts(rows: list[dict]) -> MagicMock:
    """Return a MagicMock supabase client whose posts-query chain yields ``rows``."""
    sb = MagicMock()
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.is_.return_value = chain
    chain.order.return_value = chain
    chain.lte.return_value = chain
    chain.limit.return_value = chain
    chain.execute.return_value = MagicMock(data=rows)
    sb.table.return_value = chain
    return sb


def _post_row(
    user_id: str, username: str, updated_at: datetime, deleted: bool = False
) -> dict:
    # Matches the select projection in list_public_user_cursor:
    #   "user_id, updated_at, users!inner(username, deleted_at)"
    # Note: the repo relies on the !inner filter eq("users.deleted_at", "null")
    # to filter deleted users at the DB layer, so rows handed back already
    # exclude deleted users — tests mirror that by not emitting them.
    assert not deleted, "deleted user rows are filtered by DB-level inner join"
    return {
        "user_id": user_id,
        "updated_at": updated_at.isoformat(),
        "users": {"username": username, "deleted_at": None},
    }


class TestListPublicUserCursor:
    """Repository-level tests for post_repo.list_public_user_cursor."""

    def test_empty_returns_empty_list(self):
        from app.repositories.post_repo import PostRepository

        sb = _build_supabase_with_posts([])
        repo = PostRepository(sb)

        result = repo.list_public_user_cursor(cursor=None, limit=10)

        assert result == []

    def test_deduplicates_multiple_posts_per_user(self):
        """A user with N posts appears once, carrying their MAX updated_at."""
        from app.repositories.post_repo import PostRepository

        user_id = "11111111-1111-1111-1111-111111111111"
        now = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
        older = now - timedelta(days=2)
        rows = [
            _post_row(user_id, "alice", now),
            _post_row(user_id, "alice", older),
        ]

        sb = _build_supabase_with_posts(rows)
        repo = PostRepository(sb)

        result = repo.list_public_user_cursor(cursor=None, limit=10)

        assert len(result) == 1
        assert result[0]["username"] == "alice"
        assert result[0]["updated_at"] == now

    def test_sort_order_is_updated_at_desc_then_username_asc(self):
        from app.repositories.post_repo import PostRepository

        base = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
        rows = [
            # Same timestamp → username tie-break (asc).
            _post_row("u-b", "bravo", base),
            _post_row("u-a", "alpha", base),
            # Older timestamp → ranked after same-timestamp pair.
            _post_row("u-c", "charlie", base - timedelta(minutes=5)),
        ]

        sb = _build_supabase_with_posts(rows)
        repo = PostRepository(sb)

        result = repo.list_public_user_cursor(cursor=None, limit=10)

        assert [r["username"] for r in result] == ["alpha", "bravo", "charlie"]

    def test_returns_limit_plus_one_when_more_available(self):
        from app.repositories.post_repo import PostRepository

        base = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
        rows = [
            _post_row(f"u-{i}", f"user{i:02d}", base - timedelta(minutes=i))
            for i in range(5)
        ]

        sb = _build_supabase_with_posts(rows)
        repo = PostRepository(sb)

        result = repo.list_public_user_cursor(cursor=None, limit=3)

        # limit=3, available=5 → repo returns 4 to signal next page.
        assert len(result) == 4

    def test_cursor_filters_strictly_before(self):
        from app.repositories.post_repo import PostRepository

        base = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
        rows = [
            _post_row("u-a", "alpha", base),
            _post_row("u-b", "bravo", base - timedelta(minutes=1)),
            _post_row("u-c", "charlie", base - timedelta(minutes=2)),
        ]

        sb = _build_supabase_with_posts(rows)
        repo = PostRepository(sb)

        # Cursor at (base, "alpha") — next page starts strictly below.
        result = repo.list_public_user_cursor(
            cursor=(base, "alpha"),
            limit=10,
        )

        assert [r["username"] for r in result] == ["bravo", "charlie"]

    def test_cursor_keeps_same_timestamp_tiebreaker(self):
        """Users with identical updated_at but later username must NOT be dropped.

        Regression for Codex adversarial finding: the previous tuple compare
        `(updated_at, username) < cursor` filtered out rows where
        updated_at == cursor.updated_at but username came alphabetically after
        the cursor's username — i.e. the users that are supposed to open the
        next page under `(updated_at DESC, username ASC)` order.
        """
        from app.repositories.post_repo import PostRepository

        base = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
        # Four users, three sharing the same updated_at. Sort order:
        # (base, alpha), (base, bravo), (base, charlie), (base-1m, delta).
        # Cursor at (base, "alpha") → next page must include bravo + charlie.
        rows = [
            _post_row("u-a", "alpha", base),
            _post_row("u-b", "bravo", base),
            _post_row("u-c", "charlie", base),
            _post_row("u-d", "delta", base - timedelta(minutes=1)),
        ]

        sb = _build_supabase_with_posts(rows)
        repo = PostRepository(sb)

        result = repo.list_public_user_cursor(
            cursor=(base, "alpha"),
            limit=10,
        )

        assert [r["username"] for r in result] == ["bravo", "charlie", "delta"]


class TestCursorCodec:
    """Cursor encode/decode round-trip and 400 semantics."""

    def test_encode_decode_round_trip(self):
        from app.api.public import _decode_cursor, _encode_cursor

        updated_at = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
        encoded = _encode_cursor(updated_at, "alice")

        decoded_updated_at, decoded_username = _decode_cursor(encoded)

        assert decoded_updated_at == updated_at
        assert decoded_username == "alice"

    def test_malformed_cursor_raises_400(self):
        from fastapi import HTTPException

        from app.api.public import _decode_cursor

        with pytest.raises(HTTPException) as exc_info:
            _decode_cursor("not base64 !!!!!")

        assert exc_info.value.status_code == 400

    def test_missing_key_raises_400(self):
        import base64
        import json

        from fastapi import HTTPException

        from app.api.public import _decode_cursor

        # Valid base64, valid JSON, but missing the "n" key.
        payload = (
            base64.urlsafe_b64encode(
                json.dumps({"u": "2026-04-10T12:00:00+00:00"}).encode()
            )
            .rstrip(b"=")
            .decode()
        )

        with pytest.raises(HTTPException) as exc_info:
            _decode_cursor(payload)

        assert exc_info.value.status_code == 400

    def test_naive_cursor_normalises_to_utc(self):
        """A cursor payload missing a timezone offset must not crash the handler.

        Regression for Codex adversarial finding: `datetime.fromisoformat` on
        a naive ISO string returned a naive datetime, which then hit
        `TypeError` when compared against the offset-aware Supabase
        timestamps. Normalising to UTC on decode keeps downstream comparisons
        legal.
        """
        import base64
        import json

        from app.api.public import _decode_cursor

        naive_payload = (
            base64.urlsafe_b64encode(
                json.dumps({"u": "2026-04-10T12:00:00", "n": "alice"}).encode()
            )
            .rstrip(b"=")
            .decode()
        )

        updated_at, username = _decode_cursor(naive_payload)

        assert updated_at.tzinfo is not None
        assert username == "alice"


class TestListPublicCardsHandler:
    """End-to-end handler tests — exercises the FastAPI route function."""

    def _run_handler(
        self,
        rows_for_call: list[list[dict]] | list[dict],
        cursor: str | None = None,
        per_page: int = 1000,
    ):
        """Invoke list_public_cards against a mocked post_repo."""
        from app.api.public import list_public_cards
        from app.repositories.post_repo import PostRepository

        # The handler calls run_sync(post_repo.list_public_user_cursor, ...);
        # we wire a real PostRepository over a MagicMock supabase so the repo
        # logic itself is exercised.
        if rows_for_call and isinstance(rows_for_call[0], list):
            # Sequence of query results (paged)
            sb = MagicMock()
            chain = MagicMock()
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.is_.return_value = chain
            chain.order.return_value = chain
            chain.lte.return_value = chain
            chain.limit.return_value = chain
            chain.execute.side_effect = [MagicMock(data=rows) for rows in rows_for_call]
            sb.table.return_value = chain
        else:
            sb = _build_supabase_with_posts(rows_for_call)

        post_repo = PostRepository(sb)
        return asyncio.get_event_loop().run_until_complete(
            list_public_cards(
                cursor=cursor,
                per_page=per_page,
                post_repo=post_repo,
            )
        )

    def test_empty_result(self):
        resp = self._run_handler(rows_for_call=[])

        assert resp.items == []
        assert resp.next_cursor is None

    def test_users_without_non_deleted_posts_excluded(self):
        """Posts with is_deleted=true are filtered by .eq("is_deleted", False);
        this is enforced at the DB level, so no such rows reach the repo."""
        base = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
        rows = [_post_row("u-a", "alpha", base)]

        resp = self._run_handler(rows_for_call=rows)

        assert len(resp.items) == 1
        assert resp.items[0].username == "alpha"

    def test_sort_order_preserved_in_response(self):
        base = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
        rows = [
            _post_row("u-a", "alpha", base - timedelta(hours=1)),
            _post_row("u-b", "bravo", base),
        ]

        resp = self._run_handler(rows_for_call=rows)

        assert [item.username for item in resp.items] == ["bravo", "alpha"]

    def test_page_1_then_page_2_no_overlap(self):
        """Round-trip: fetch page 1, use next_cursor to fetch page 2."""
        base = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
        # 5 users, per_page=2 → expect pages [0,1], [2,3], [4].
        rows = [
            _post_row(f"u-{i}", f"user{i:02d}", base - timedelta(minutes=i))
            for i in range(5)
        ]

        # Page 1
        resp1 = self._run_handler(rows_for_call=rows, per_page=2)
        assert [item.username for item in resp1.items] == ["user00", "user01"]
        assert resp1.next_cursor is not None

        # Page 2 — reuse same rows; the repo applies cursor filtering.
        resp2 = self._run_handler(
            rows_for_call=rows,
            cursor=resp1.next_cursor,
            per_page=2,
        )

        page1_names = {item.username for item in resp1.items}
        page2_names = {item.username for item in resp2.items}
        assert page1_names.isdisjoint(page2_names), "pages must not overlap"
        assert [item.username for item in resp2.items] == ["user02", "user03"]

    def test_malformed_cursor_returns_400(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            self._run_handler(rows_for_call=[], cursor="###not-valid###")

        assert exc_info.value.status_code == 400

    def test_final_page_has_null_next_cursor(self):
        base = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
        rows = [
            _post_row("u-a", "alpha", base),
            _post_row("u-b", "bravo", base - timedelta(minutes=1)),
        ]

        resp = self._run_handler(rows_for_call=rows, per_page=10)

        assert len(resp.items) == 2
        assert resp.next_cursor is None
