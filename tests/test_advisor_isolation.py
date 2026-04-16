"""Per-user isolation regression — characterization lock.

Spec §14: every advisor/memories operation is scoped to the caller's user_id
sourced from the JWT. This test fails loudly if a future PR forgets to pass
the authenticated user_id into a repo call.

Strategy: inject a fake repo that actually filters rows by user_id, seed
rows for users A and B, then call each service method as A with B-owned
ids. Expect empty results / False returns / no B rows touched.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.advisor.memory_manager import MemoryManager
from app.advisor.service import AdvisorService


class _IsolatingFakeRepo:
    """Fake AdvisorRepository that enforces user_id on every read/write.

    Any method called without passing the caller's user_id raises, which
    turns the silent-leak regression into a loud test failure.
    """

    def __init__(self) -> None:
        self.nudges: list[dict] = []
        self.memories: list[dict] = []

    # Nudges ----------------------------------------------------------------

    def get_nudges(self, user_id: str) -> list[dict]:
        return [n for n in self.nudges if n["user_id"] == user_id]

    def get_nudges_page(
        self, user_id: str, fetch_limit: int, cursor=None, unread_only=False
    ):
        rows = [n for n in self.nudges if n["user_id"] == user_id]
        return rows[:fetch_limit]

    def get_nudge_by_id(self, nudge_id: str, user_id: str):
        for n in self.nudges:
            if n["id"] == nudge_id and n["user_id"] == user_id:
                return n
        return None

    def mark_nudge_read(self, nudge_id: str):  # called only after ownership verified
        for n in self.nudges:
            if n["id"] == nudge_id:
                n["read_at"] = "2026-04-16T00:00:00+00:00"
                return

    # Memories --------------------------------------------------------------

    def get_memories(self, user_id: str, type_filter=None):
        return [m for m in self.memories if m["user_id"] == user_id]

    def get_memories_page(
        self, user_id: str, fetch_limit: int, cursor=None, type_filter=None
    ):
        rows = [m for m in self.memories if m["user_id"] == user_id]
        return rows[:fetch_limit]

    def delete_memory(self, memory_id: str, user_id: str) -> list[dict]:
        deleted: list[dict] = []
        remaining: list[dict] = []
        for m in self.memories:
            if m["id"] == memory_id and m["user_id"] == user_id:
                deleted.append(m)
            else:
                remaining.append(m)
        self.memories = remaining
        return deleted


def _make_service(repo: _IsolatingFakeRepo) -> AdvisorService:
    """Build an AdvisorService with the fake repo (no chat dependencies used)."""
    svc = AdvisorService.__new__(AdvisorService)
    svc._repo = repo
    # MemoryManager sits atop the same repo.
    from types import SimpleNamespace

    embed = SimpleNamespace(compute_embedding=AsyncMock(return_value=[0.0] * 8))
    svc._memory_manager = MemoryManager(
        advisor_repo=repo, llm_adapter=SimpleNamespace(), embedding_adapter=embed
    )
    return svc


def _seed_users(repo: _IsolatingFakeRepo) -> tuple[str, str, str, str]:
    """Create users A, B, each with one nudge and one memory. Return ids."""
    a, b = str(uuid4()), str(uuid4())
    nudge_b, memory_b = str(uuid4()), str(uuid4())
    repo.nudges.append(
        {
            "id": nudge_b,
            "user_id": b,
            "trigger": "weekly_checkin",
            "content": "b's nudge",
            "read_at": None,
            "created_at": "2026-04-15T00:00:00+00:00",
        }
    )
    repo.memories.append(
        {
            "id": memory_b,
            "user_id": b,
            "type": "user_note",
            "content": {"text": "b's note"},
            "created_at": "2026-04-15T00:00:00+00:00",
        }
    )
    return a, b, nudge_b, memory_b


@pytest.mark.asyncio
async def test_list_nudges_excludes_other_users():
    repo = _IsolatingFakeRepo()
    a, _b, _, _ = _seed_users(repo)
    svc = _make_service(repo)

    result = await svc.get_nudges_page(UUID(a), limit=50)

    assert result["nudges"] == []


@pytest.mark.asyncio
async def test_mark_foreign_nudge_read_returns_false_and_does_not_mutate():
    repo = _IsolatingFakeRepo()
    a, _b, nudge_b, _ = _seed_users(repo)
    svc = _make_service(repo)

    ok = await svc.mark_nudge_read(UUID(a), UUID(nudge_b))

    assert ok is False
    assert repo.nudges[0]["read_at"] is None


@pytest.mark.asyncio
async def test_list_memories_excludes_other_users():
    repo = _IsolatingFakeRepo()
    a, _b, _, _ = _seed_users(repo)
    svc = _make_service(repo)

    result = await svc.list_memories_page(UUID(a), limit=50)

    assert result["memories"] == []


@pytest.mark.asyncio
async def test_delete_foreign_memory_returns_false_and_leaves_row():
    repo = _IsolatingFakeRepo()
    a, _b, _, memory_b = _seed_users(repo)
    svc = _make_service(repo)

    ok = await svc.delete_memory(UUID(a), UUID(memory_b))

    assert ok is False
    assert any(m["id"] == memory_b for m in repo.memories)


@pytest.mark.asyncio
async def test_each_user_sees_only_own_rows():
    repo = _IsolatingFakeRepo()
    a, b, _, _ = _seed_users(repo)
    # Seed a memory for A too.
    repo.memories.append(
        {
            "id": str(uuid4()),
            "user_id": a,
            "type": "goal",
            "content": {"text": "a's goal"},
            "created_at": "2026-04-15T00:00:00+00:00",
        }
    )
    svc = _make_service(repo)

    res_a = await svc.list_memories_page(UUID(a), limit=50)
    res_b = await svc.list_memories_page(UUID(b), limit=50)

    a_user_ids = {m["user_id"] for m in res_a["memories"]}
    b_user_ids = {m["user_id"] for m in res_b["memories"]}
    assert a_user_ids == {a}
    assert b_user_ids == {b}
