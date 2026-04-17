"""Memory writes — dedup + authored_by enforcement (Plan 2026-04-18).

Covers ``MemoryManager.write_memory``:
- exact-content dedup (skips embedding call)
- semantic-similarity dedup (skips insert when nearest neighbor ≥ threshold)
- authored_by validation (must be one of user/model/analysis)
- clean insert when no duplicate exists

The pin-insight retrieval logic was deleted in the same PR that moved
memory retrieval to an explicit model-driven tool surface; the
corresponding tests live in the MCP tool-level integration tests.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.advisor.memory_manager import MemoryManager, _content_fingerprint
from app.advisor.models import MemoryType


class _StubRepo:
    """Minimal AdvisorRepository stand-in for write_memory tests."""

    def __init__(
        self,
        *,
        exact_match: dict | None = None,
        semantic_match: dict | None = None,
        count: int = 0,
    ) -> None:
        self._exact_match = exact_match
        self._semantic_match = semantic_match
        self._count = count
        self.insert_calls: list[dict] = []
        self.count_calls = 0
        self.hash_calls: list[tuple[str, str, str]] = []
        self.semantic_calls: list[tuple[str, str, list[float], float]] = []

    def find_memory_by_content_hash(
        self,
        *,
        user_id: str,
        memory_type: str,
        content_hash: str,
    ) -> dict | None:
        self.hash_calls.append((user_id, memory_type, content_hash))
        return self._exact_match

    def find_semantic_duplicate(
        self,
        *,
        user_id: str,
        memory_type: str,
        embedding: list[float],
        threshold: float,
    ) -> dict | None:
        self.semantic_calls.append((user_id, memory_type, embedding, threshold))
        return self._semantic_match

    def count_memories(self, user_id: str) -> int:
        self.count_calls += 1
        return self._count

    def delete_oldest_memory_by_authored_by(
        self, user_id: str, *, authored_by: str, exclude_types: tuple[str, ...]
    ) -> list[dict]:
        return []

    def insert_memory(self, row: dict) -> dict:
        self.insert_calls.append(row)
        return {**row, "id": "inserted-id", "created_at": "2026-04-18T00:00:00+00:00"}


def _make_manager(repo: _StubRepo) -> tuple[MemoryManager, AsyncMock]:
    embed = AsyncMock(return_value=[0.1] * 8)
    mm = MemoryManager(
        advisor_repo=repo,
        embedding_adapter=SimpleNamespace(compute_embedding=embed),
    )
    return mm, embed


@pytest.mark.asyncio
async def test_exact_content_dedup_skips_embedding_and_insert():
    repo = _StubRepo(
        exact_match={"id": "existing", "content": {"text": "grow my hair"}},
    )
    mm, embed = _make_manager(repo)

    result = await mm.write_memory(
        uuid4(), MemoryType.GOAL, {"text": "grow my hair"}, authored_by="user"
    )

    assert result["_dedup"] == "exact_content"
    assert result["id"] == "existing"
    # No embedding call — dedup short-circuited.
    embed.assert_not_called()
    # No semantic check — stage 1 caught it.
    assert repo.semantic_calls == []
    # No insert — dedup returned the existing row.
    assert repo.insert_calls == []


@pytest.mark.asyncio
async def test_semantic_dedup_skips_insert_when_similarity_above_threshold():
    repo = _StubRepo(
        semantic_match={
            "id": "existing-semantic",
            "content": {"text": "growing my hair out"},
            "similarity": 0.95,
        },
    )
    mm, embed = _make_manager(repo)

    result = await mm.write_memory(
        uuid4(), MemoryType.GOAL, {"text": "grow hair longer"}, authored_by="user"
    )

    assert result["_dedup"].startswith("semantic_")
    assert result["id"] == "existing-semantic"
    # Embedding was computed (needed for semantic lookup).
    embed.assert_called_once()
    # No insert — semantic match blocked it.
    assert repo.insert_calls == []


@pytest.mark.asyncio
async def test_clean_insert_when_no_duplicate():
    repo = _StubRepo()
    mm, embed = _make_manager(repo)

    result = await mm.write_memory(
        uuid4(),
        MemoryType.USER_NOTE,
        {"text": "prefer minimal jewelry"},
        authored_by="user",
    )

    assert "_dedup" not in result
    assert result["authored_by"] == "user"
    assert len(repo.insert_calls) == 1
    inserted = repo.insert_calls[0]
    assert inserted["type"] == MemoryType.USER_NOTE.value
    assert inserted["authored_by"] == "user"
    assert inserted["embedding"] == embed.return_value


@pytest.mark.asyncio
async def test_rejects_invalid_authored_by():
    repo = _StubRepo()
    mm, _ = _make_manager(repo)

    with pytest.raises(ValueError, match="authored_by"):
        await mm.write_memory(
            uuid4(),
            MemoryType.GOAL,
            {"text": "x"},
            authored_by="extraction",  # no longer valid
        )


@pytest.mark.asyncio
async def test_model_authored_passes_through_to_insert():
    repo = _StubRepo()
    mm, _ = _make_manager(repo)

    await mm.write_memory(
        uuid4(),
        MemoryType.ACCEPTED_SUGGESTION,
        {"text": "got the fringe"},
        authored_by="model",
    )

    assert repo.insert_calls[0]["authored_by"] == "model"


def test_fingerprint_is_order_insensitive():
    """Canonical JSON hash must be identical for key-reordered dicts.

    Regression guard for F1: previously ``str(dict)`` was order-sensitive,
    so a row written with one key order could miss its own dedup lookup
    after a JSONB round-trip reordered the keys.
    """
    a = {"face_shape": "oval", "symmetry_score": 0.87, "summary": "x"}
    b = {"summary": "x", "face_shape": "oval", "symmetry_score": 0.87}
    assert _content_fingerprint(a) == _content_fingerprint(b)


def test_fingerprint_differs_for_different_content():
    assert _content_fingerprint({"text": "a"}) != _content_fingerprint({"text": "b"})


@pytest.mark.asyncio
async def test_concurrent_identical_writes_produce_one_row(monkeypatch):
    """TOCTOU backstop — a unique-violation on the DB short-circuits to
    the winning row. Two concurrent ``write_memory`` calls for the same
    (user_id, type, content) must yield exactly one insert.
    """

    class _UniqueViolation(Exception):
        code = "23505"

    class _RacingRepo:
        """Simulates the DB partial unique index: the second insert raises."""

        def __init__(self) -> None:
            self.inserts: list[dict] = []
            self._winner: dict | None = None

        def find_memory_by_content_hash(
            self,
            *,
            user_id: str,
            memory_type: str,
            content_hash: str,
        ) -> dict | None:
            # Pre-insert lookup: both racing calls miss; post-violation
            # lookup returns the winning row.
            return self._winner

        def find_semantic_duplicate(self, **_: object) -> None:
            return None

        def count_memories(self, user_id: str) -> int:
            return 0

        def delete_oldest_memory_by_authored_by(
            self, user_id: str, *, authored_by: str, exclude_types: tuple[str, ...]
        ) -> list[dict]:
            return []

        def insert_memory(self, row: dict) -> dict:
            if self._winner is not None:
                # Second writer loses to the unique index.
                raise _UniqueViolation("duplicate key value violates unique constraint")
            self.inserts.append(row)
            self._winner = {**row, "id": "winner-id"}
            return self._winner

    repo = _RacingRepo()
    embed = AsyncMock(return_value=[0.1] * 8)
    mm = MemoryManager(
        advisor_repo=repo,
        embedding_adapter=SimpleNamespace(compute_embedding=embed),
    )

    user_id = uuid4()
    results = await asyncio.gather(
        mm.write_memory(
            user_id, MemoryType.GOAL, {"text": "grow my hair"}, authored_by="user"
        ),
        mm.write_memory(
            user_id, MemoryType.GOAL, {"text": "grow my hair"}, authored_by="user"
        ),
    )

    # Exactly one insert survived.
    assert len(repo.inserts) == 1
    # Both callers received a row — one fresh, one dedup-race marker.
    dedup_markers = [r.get("_dedup") for r in results]
    assert dedup_markers.count("race") == 1


def test_canonical_hash_survives_jsonb_reorder():
    """Simulate a JSONB round-trip (re-sort) — hash stays stable.

    Cheap simulation: re-serialize via ``json.loads(json.dumps(..., sort_keys=True))``.
    Identical hashes before and after prove the ``sort_keys=True`` in
    ``_content_fingerprint`` protects us from JSONB's unordered storage.
    """
    original = {"z": 1, "a": 2, "m": 3}
    reordered = json.loads(json.dumps(original, sort_keys=True))
    # Reordered dict has a different repr but the same canonical hash.
    assert repr(original) != repr(reordered)
    assert _content_fingerprint(original) == _content_fingerprint(reordered)
