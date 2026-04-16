"""Memory cap enforcement — spec §10 (500-per-user).

Tests exercise the in-process logic on `MemoryManager._enforce_memory_cap`
via a stub repo, avoiding Supabase while still covering eviction policy.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.advisor.memory_manager import MemoryManager
from app.advisor.models import MemoryType


class _StubRepo:
    """Minimal AdvisorRepository stand-in for cap testing."""

    def __init__(self, count: int, evict_returns: list[dict] | None = None):
        self._count = count
        self._evict_returns = (
            evict_returns if evict_returns is not None else [{"id": str(uuid4())}]
        )
        self.inserted: list[dict] = []
        self.eviction_calls: list[tuple] = []
        self.count_calls = 0

    def count_memories(self, user_id: str) -> int:
        self.count_calls += 1
        return self._count

    def delete_oldest_memory_excluding_types(self, user_id: str, exclude_types):
        self.eviction_calls.append((user_id, exclude_types))
        return list(self._evict_returns)

    def insert_memory(self, row: dict) -> dict:
        self.inserted.append(row)
        return {**row, "id": str(uuid4())}


def _make_manager(
    count: int, evict_returns: list[dict] | None = None
) -> tuple[MemoryManager, _StubRepo]:
    repo = _StubRepo(count=count, evict_returns=evict_returns)
    embed = SimpleNamespace(compute_embedding=AsyncMock(return_value=[0.0] * 8))
    llm = SimpleNamespace()
    mm = MemoryManager(advisor_repo=repo, llm_adapter=llm, embedding_adapter=embed)
    return mm, repo


@pytest.mark.asyncio
async def test_write_under_cap_does_not_evict(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_MEMORY_CAP", 500)
    mm, repo = _make_manager(count=499)

    await mm.write_memory(uuid4(), MemoryType.USER_NOTE, {"text": "new note"})

    assert repo.eviction_calls == []
    assert len(repo.inserted) == 1


@pytest.mark.asyncio
async def test_write_at_cap_evicts_oldest_non_goal(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_MEMORY_CAP", 500)
    mm, repo = _make_manager(count=500)

    await mm.write_memory(uuid4(), MemoryType.USER_NOTE, {"text": "new note"})

    assert len(repo.eviction_calls) == 1
    _, exclude_types = repo.eviction_calls[0]
    assert MemoryType.GOAL.value in exclude_types
    assert len(repo.inserted) == 1


@pytest.mark.asyncio
async def test_write_at_cap_with_goals_only_still_writes(monkeypatch, caplog):
    """Goal preservation: if cap is full of goals, accept overflow + log warning."""
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_MEMORY_CAP", 500)
    mm, repo = _make_manager(count=500, evict_returns=[])

    with caplog.at_level("WARNING"):
        await mm.write_memory(uuid4(), MemoryType.GOAL, {"text": "next goal"})

    assert len(repo.inserted) == 1
    assert any(
        "goal_only" in r.getMessage() or "goals only" in r.getMessage()
        for r in caplog.records
    )


@pytest.mark.asyncio
async def test_count_failure_does_not_block_write(monkeypatch, caplog):
    """If the count query fails, write still proceeds (cap is best-effort)."""
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_MEMORY_CAP", 500)
    mm, repo = _make_manager(count=500)
    repo.count_memories = lambda _uid: (_ for _ in ()).throw(RuntimeError("db down"))

    with caplog.at_level("WARNING"):
        await mm.write_memory(uuid4(), MemoryType.USER_NOTE, {"text": "x"})

    assert len(repo.inserted) == 1


@pytest.mark.asyncio
async def test_per_user_isolation_on_cap(monkeypatch):
    """Cap check is scoped to the caller's user_id."""
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_MEMORY_CAP", 500)
    mm, repo = _make_manager(count=500)

    user_a = uuid4()
    await mm.write_memory(user_a, MemoryType.USER_NOTE, {"text": "a"})

    # Eviction call must have used A's id.
    called_user_id, _ = repo.eviction_calls[0]
    assert called_user_id == str(user_a)
