"""Memory cap enforcement — per-user 500 soft cap with provenance-aware eviction.

Tests exercise the in-process logic on ``MemoryManager._enforce_memory_cap``
via a stub repo, avoiding Supabase while still covering eviction policy.

Eviction priority (post-Plan-2026-04-18):
  1. ``authored_by='model'``   — Ada's saves evict first.
  2. ``authored_by='analysis'`` (except ``style_profile``).
  3. ``authored_by='user'``    — last resort; ``goal`` is always protected.
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

    def __init__(
        self,
        count: int,
        *,
        evict_plan: dict[str, list[dict]] | None = None,
    ) -> None:
        """``evict_plan`` maps authored_by → rows returned on that tier's call.

        Default: every tier returns a single fake deleted row so the first
        tier always wins. Tests that care about fallthrough pass an explicit
        plan.
        """
        self._count = count
        self._evict_plan = evict_plan or {
            "model": [{"id": str(uuid4())}],
            "analysis": [{"id": str(uuid4())}],
            "user": [{"id": str(uuid4())}],
        }
        self.inserted: list[dict] = []
        self.eviction_calls: list[tuple[str, str, tuple[str, ...]]] = []
        self.count_calls = 0

    def find_memory_by_content_hash(self, **_: object) -> None:
        return None

    def find_semantic_duplicate(self, **_: object) -> None:
        return None

    def count_memories(self, user_id: str) -> int:
        self.count_calls += 1
        return self._count

    def delete_oldest_memory_by_authored_by(
        self,
        user_id: str,
        *,
        authored_by: str,
        exclude_types: tuple[str, ...],
    ) -> list[dict]:
        self.eviction_calls.append((user_id, authored_by, exclude_types))
        return list(self._evict_plan.get(authored_by, []))

    def insert_memory(self, row: dict) -> dict:
        self.inserted.append(row)
        return {**row, "id": str(uuid4())}


def _make_manager(
    count: int,
    *,
    evict_plan: dict[str, list[dict]] | None = None,
) -> tuple[MemoryManager, _StubRepo]:
    repo = _StubRepo(count=count, evict_plan=evict_plan)
    embed = SimpleNamespace(compute_embedding=AsyncMock(return_value=[0.0] * 8))
    mm = MemoryManager(advisor_repo=repo, embedding_adapter=embed)
    return mm, repo


@pytest.mark.asyncio
async def test_write_under_cap_does_not_evict(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_MEMORY_CAP", 500)
    mm, repo = _make_manager(count=499)

    await mm.write_memory(
        uuid4(), MemoryType.USER_NOTE, {"text": "new note"}, authored_by="user"
    )

    assert repo.eviction_calls == []
    assert len(repo.inserted) == 1


@pytest.mark.asyncio
async def test_write_at_cap_evicts_model_first(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_MEMORY_CAP", 500)
    mm, repo = _make_manager(count=500)

    await mm.write_memory(
        uuid4(), MemoryType.USER_NOTE, {"text": "new note"}, authored_by="user"
    )

    # First tier is 'model' — single call, no fallthrough.
    assert len(repo.eviction_calls) == 1
    _, tier, exclude = repo.eviction_calls[0]
    assert tier == "model"
    assert MemoryType.GOAL.value in exclude


@pytest.mark.asyncio
async def test_eviction_falls_through_to_analysis_when_no_model_rows(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_MEMORY_CAP", 500)
    mm, repo = _make_manager(
        count=500,
        evict_plan={"model": [], "analysis": [{"id": "an-id"}], "user": []},
    )

    await mm.write_memory(
        uuid4(), MemoryType.USER_NOTE, {"text": "x"}, authored_by="user"
    )

    # Tried model, fell through to analysis — stopped there.
    tiers = [c[1] for c in repo.eviction_calls]
    assert tiers == ["model", "analysis"]


@pytest.mark.asyncio
async def test_eviction_falls_through_to_user_as_last_resort(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_MEMORY_CAP", 500)
    mm, repo = _make_manager(
        count=500,
        evict_plan={"model": [], "analysis": [], "user": [{"id": "u-id"}]},
    )

    await mm.write_memory(
        uuid4(), MemoryType.USER_NOTE, {"text": "x"}, authored_by="user"
    )

    tiers = [c[1] for c in repo.eviction_calls]
    assert tiers == ["model", "analysis", "user"]


@pytest.mark.asyncio
async def test_analysis_tier_excludes_style_profile(monkeypatch):
    """style_profile rows are never evicted — only one row per user exists."""
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_MEMORY_CAP", 500)
    mm, repo = _make_manager(
        count=500,
        evict_plan={"model": [], "analysis": [{"id": "x"}], "user": []},
    )

    await mm.write_memory(
        uuid4(), MemoryType.USER_NOTE, {"text": "x"}, authored_by="user"
    )

    analysis_call = [c for c in repo.eviction_calls if c[1] == "analysis"][0]
    _, _, exclude = analysis_call
    assert MemoryType.STYLE_PROFILE.value in exclude
    assert MemoryType.GOAL.value in exclude


@pytest.mark.asyncio
async def test_write_at_cap_with_goals_only_still_writes(monkeypatch, caplog):
    """Every tier empty (all goals) → accept overflow + log warning."""
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_MEMORY_CAP", 500)
    mm, repo = _make_manager(
        count=500,
        evict_plan={"model": [], "analysis": [], "user": []},
    )

    with caplog.at_level("WARNING"):
        await mm.write_memory(
            uuid4(), MemoryType.GOAL, {"text": "next goal"}, authored_by="user"
        )

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
        await mm.write_memory(
            uuid4(), MemoryType.USER_NOTE, {"text": "x"}, authored_by="user"
        )

    assert len(repo.inserted) == 1


@pytest.mark.asyncio
async def test_per_user_isolation_on_cap(monkeypatch):
    """Cap check is scoped to the caller's user_id."""
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_MEMORY_CAP", 500)
    mm, repo = _make_manager(count=500)

    user_a = uuid4()
    await mm.write_memory(
        user_a, MemoryType.USER_NOTE, {"text": "a"}, authored_by="user"
    )

    called_user_id, _, _ = repo.eviction_calls[0]
    assert called_user_id == str(user_a)
