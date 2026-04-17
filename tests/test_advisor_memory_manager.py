"""Memory retrieval — analysis_insight pin (spec §4.4, plan Unit 3).

Covers `MemoryManager.get_relevant_memories`: the latest ``analysis_insight``
row must always be present in the output regardless of pgvector similarity
to the current query, and must not be duplicated when pgvector already
returned it.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.advisor.memory_manager import MemoryManager
from app.advisor.models import MemoryType


def _row(
    *,
    content: dict | str,
    similarity: float,
    created_at: str = "2026-04-17T00:00:00+00:00",
    memory_type: str = MemoryType.USER_NOTE.value,
) -> dict:
    """Build a fake pgvector candidate row."""
    return {
        "content": content,
        "similarity": similarity,
        "created_at": created_at,
        "type": memory_type,
    }


class _StubRepo:
    """Minimal AdvisorRepository stand-in for pin testing."""

    def __init__(
        self,
        candidates: list[dict],
        latest_insight: dict | None = None,
    ) -> None:
        self._candidates = candidates
        self._latest_insight = latest_insight
        self.match_calls: list[tuple] = []
        self.insight_calls: list[str] = []

    def match_memories(
        self, user_id: str, embedding: list[float], limit: int
    ) -> list[dict]:
        self.match_calls.append((user_id, len(embedding), limit))
        return list(self._candidates)

    def get_latest_analysis_insight(self, user_id: str) -> dict | None:
        self.insight_calls.append(user_id)
        return self._latest_insight


def _make_manager(
    candidates: list[dict],
    latest_insight: dict | None = None,
) -> tuple[MemoryManager, _StubRepo]:
    repo = _StubRepo(candidates=candidates, latest_insight=latest_insight)
    embed = SimpleNamespace(compute_embedding=AsyncMock(return_value=[0.0] * 8))
    llm = SimpleNamespace()
    mm = MemoryManager(advisor_repo=repo, llm_adapter=llm, embedding_adapter=embed)
    return mm, repo


@pytest.mark.asyncio
async def test_pin_skipped_when_pgvector_already_returned_insight(monkeypatch):
    """High-similarity analysis_insight → single copy, no duplication."""
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_CONTEXT_MEMORY_LIMIT", 5)

    insight_content = {
        "face_shape": "oval",
        "symmetry_score": 0.87,
        "recommendations": ["longer hair", "soft fade"],
    }
    insight_row = _row(
        content=insight_content,
        similarity=0.95,
        memory_type=MemoryType.ANALYSIS_INSIGHT.value,
    )
    mm, repo = _make_manager(
        candidates=[insight_row],
        latest_insight={
            "content": insight_content,
            "created_at": insight_row["created_at"],
        },
    )

    result = await mm.get_relevant_memories(uuid4(), "hairstyle")

    # Exactly one row in output: the pgvector copy.
    insight_rows = [
        r for r in result if r.get("type") == MemoryType.ANALYSIS_INSIGHT.value
    ]
    assert len(insight_rows) == 1
    # Pin dedup consulted the latest insight.
    assert len(repo.insight_calls) == 1


@pytest.mark.asyncio
async def test_pin_splices_insight_when_similarity_below_floor(monkeypatch):
    """Insight dropped by 0.60 floor → pinned at position 0, limit enforced."""
    from app.config import settings

    limit = 3
    monkeypatch.setattr(settings, "ADVISOR_CONTEXT_MEMORY_LIMIT", limit)

    # Three high-scoring non-insight memories fill the limit.
    high_scorers = [
        _row(content={"text": f"note-{i}"}, similarity=0.9) for i in range(limit)
    ]
    insight_content = {
        "face_shape": "oval",
        "symmetry_score": 0.87,
        "recommendations": ["longer hair"],
    }

    mm, _repo = _make_manager(
        candidates=high_scorers,
        latest_insight={
            "content": insight_content,
            "created_at": "2026-04-17T00:00:00+00:00",
        },
    )

    result = await mm.get_relevant_memories(uuid4(), "hairstyle")

    # Limit enforced.
    assert len(result) == limit
    # Pinned at position 0.
    assert result[0]["type"] == MemoryType.ANALYSIS_INSIGHT.value
    assert result[0]["content"] == insight_content
    # Last scored item dropped (only two of the three high scorers survive).
    non_pinned = [r for r in result if r is not result[0]]
    assert len(non_pinned) == limit - 1


@pytest.mark.asyncio
async def test_no_pin_when_user_has_no_analysis_insight(monkeypatch):
    """No insight row → no pin, output identical to current behavior."""
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_CONTEXT_MEMORY_LIMIT", 5)

    candidates = [
        _row(content={"text": "one"}, similarity=0.8),
        _row(content={"text": "two"}, similarity=0.75),
    ]
    mm, _repo = _make_manager(candidates=candidates, latest_insight=None)

    result = await mm.get_relevant_memories(uuid4(), "anything")

    assert len(result) == 2
    assert all(r.get("type") != MemoryType.ANALYSIS_INSIGHT.value for r in result)


@pytest.mark.asyncio
async def test_pin_takes_slot_when_limit_is_one(monkeypatch):
    """limit=1 + high-scoring non-insight → output is pinned insight only."""
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_CONTEXT_MEMORY_LIMIT", 1)

    insight_content = {
        "face_shape": "square",
        "symmetry_score": 0.9,
        "recommendations": ["trim sides"],
    }
    mm, _repo = _make_manager(
        candidates=[_row(content={"text": "high-scoring note"}, similarity=0.95)],
        latest_insight={
            "content": insight_content,
            "created_at": "2026-04-17T00:00:00+00:00",
        },
    )

    result = await mm.get_relevant_memories(uuid4(), "hairstyle")

    assert len(result) == 1
    assert result[0]["type"] == MemoryType.ANALYSIS_INSIGHT.value
    assert result[0]["content"] == insight_content
