"""write_analysis_insight persists a human-readable `summary` in content.

Regression guard: the mobile Memories row reads `content.summary`. Without
this field the row falls back to `JSON.stringify(content)` and shows a raw
blob. See `mobile/components/advisor/MemoryList.tsx::memoryContentText`.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.advisor.memory_manager import MemoryManager


class _StubRepo:
    def __init__(self):
        self.inserted: list[dict] = []

    def find_memory_by_content_hash(self, **_: object) -> None:
        return None

    def find_semantic_duplicate(self, **_: object) -> None:
        return None

    def count_memories(self, user_id: str) -> int:
        return 0

    def delete_oldest_memory_by_authored_by(
        self, user_id: str, *, authored_by: str, exclude_types: tuple[str, ...]
    ) -> list[dict]:
        return []

    def insert_memory(self, row: dict) -> dict:
        self.inserted.append(row)
        return {**row, "id": str(uuid4())}


def _make_manager() -> tuple[MemoryManager, _StubRepo]:
    repo = _StubRepo()
    embed = SimpleNamespace(compute_embedding=AsyncMock(return_value=[0.0] * 8))
    mm = MemoryManager(advisor_repo=repo, embedding_adapter=embed)
    return mm, repo


@pytest.mark.asyncio
async def test_analysis_insight_stores_human_summary():
    mm, repo = _make_manager()

    await mm.write_analysis_insight(
        user_id=uuid4(),
        face_shape="oval",
        symmetry_score=0.9953,
        recommendations=["Try bangs", "Clean up brows", "Hydrate skin"],
        upload_id=str(uuid4()),
    )

    assert len(repo.inserted) == 1
    assert repo.inserted[0]["authored_by"] == "analysis"
    content = repo.inserted[0]["content"]

    # Structured fields preserved for any downstream consumer.
    assert content["face_shape"] == "oval"
    assert content["symmetry_score"] == 0.9953
    assert content["recommendations"] == ["Try bangs", "Clean up brows", "Hydrate skin"]

    # Human-readable summary must be present and non-empty.
    summary = content.get("summary")
    assert isinstance(summary, str) and summary, (
        "analysis_insight content must carry a non-empty `summary` field"
    )
    # Summary should mention face shape — the exact format is owned by
    # summarize_memory_content; we assert on its most distinctive signal.
    assert "oval" in summary
