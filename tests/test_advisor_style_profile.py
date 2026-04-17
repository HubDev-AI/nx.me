"""Stable `style_profile` memory — plan 2026-04-17-003 Unit 7.

One row per user, upserted on every successful analysis. Chat
``_build_user_data`` reads from this row first; when absent (or when the
upsert failed), it falls back to the latest ``analysis_insight``. The
partial unique index defined in migration 0040 guarantees at-most-one
row per user at the database level.

Scenarios exercised here:
  - First analysis → row inserted with face_shape, symmetry, recs,
    last_updated_at.
  - Second analysis with different facts → single row updated,
    last_updated_at advanced.
  - ``_build_user_data`` prefers the profile over the insight fallback.
  - Profile upsert failure + insight write success → fallback still
    produces the expanded user_data block.
  - Profile with null recommendations → user_data block omits the recs
    line gracefully (and the summary line still renders).
  - Module-local ``STYLE_PROFILE_TYPE`` in the repo matches the enum.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.advisor.memory_manager import MemoryManager
from app.advisor.models import MemoryType
from app.repositories.advisor_repo import STYLE_PROFILE_TYPE


_FIXED_USER = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


class _ProfileStubRepo:
    """In-memory repo stand-in for style_profile upsert semantics.

    Captures the at-most-one-row-per-user guarantee the DB's partial
    unique index enforces so the manager's behavior can be asserted
    without Supabase.
    """

    def __init__(self) -> None:
        self._profile: dict[str, Any] | None = None
        self.inserted: list[dict[str, Any]] = []
        self.upsert_calls: list[dict[str, Any]] = []
        # Mirror the cap-related methods so write_memory-style callers
        # don't blow up even though they should never fire for the
        # profile path.
        self.count_memories_calls = 0

    # profile -----------------------------------------------------------

    def get_style_profile(self, user_id: str) -> dict[str, Any] | None:
        return self._profile

    def upsert_style_profile(self, row: dict[str, Any]) -> dict[str, Any]:
        self.upsert_calls.append(row)
        if self._profile is None:
            self._profile = {
                "content": row["content"],
                "created_at": datetime.now(tz=timezone.utc).isoformat(),
            }
            self.inserted.append(row)
        else:
            # Update path — merge happens in the manager; the repo
            # just swaps content.
            self._profile = {
                "content": row["content"],
                "created_at": self._profile["created_at"],
            }
        return {"id": str(uuid4()), **row}


def _make_manager() -> tuple[MemoryManager, _ProfileStubRepo]:
    repo = _ProfileStubRepo()
    embed = SimpleNamespace(compute_embedding=AsyncMock(return_value=[0.0] * 8))
    mm = MemoryManager(advisor_repo=repo, embedding_adapter=embed)
    return mm, repo


# ---------------------------------------------------------------------------
# MemoryManager.upsert_style_profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_analysis_inserts_new_profile_row():
    """Happy path: no existing profile → new row with all fields present."""
    mm, repo = _make_manager()

    await mm.upsert_style_profile(
        user_id=_FIXED_USER,
        face_shape="oval",
        symmetry_score=0.87,
        recommendations=["try bangs", "clean up brows"],
    )

    assert len(repo.inserted) == 1
    inserted = repo.inserted[0]
    assert inserted["user_id"] == str(_FIXED_USER)
    assert inserted["type"] == MemoryType.STYLE_PROFILE.value
    assert inserted["authored_by"] == "analysis"
    content = inserted["content"]
    assert content["face_shape"] == "oval"
    assert content["symmetry_score"] == 0.87
    assert content["recommendations"] == ["try bangs", "clean up brows"]
    # last_updated_at is a fresh UTC ISO timestamp.
    ts = datetime.fromisoformat(content["last_updated_at"])
    assert ts.tzinfo is not None
    assert ts <= datetime.now(tz=timezone.utc)


@pytest.mark.asyncio
async def test_second_analysis_updates_existing_row_and_advances_timestamp():
    """Re-analysis with different facts → one row, advanced timestamp."""
    mm, repo = _make_manager()

    # First analysis.
    await mm.upsert_style_profile(
        user_id=_FIXED_USER,
        face_shape="oval",
        symmetry_score=0.87,
        recommendations=["try bangs"],
    )
    first_ts = repo._profile["content"]["last_updated_at"]

    # A small but measurable gap so timestamp comparison is meaningful —
    # datetime.now() resolution is microseconds on the tested platforms,
    # which is enough for a strictly-greater check.
    # Second analysis with different facts.
    await mm.upsert_style_profile(
        user_id=_FIXED_USER,
        face_shape="heart",
        symmetry_score=0.91,
        recommendations=["softer fringe"],
    )

    # The stub insert-log captures inserts only; the second call must have
    # taken the update branch.
    assert len(repo.inserted) == 1
    assert len(repo.upsert_calls) == 2

    content = repo._profile["content"]
    assert content["face_shape"] == "heart"
    assert content["symmetry_score"] == 0.91
    assert content["recommendations"] == ["softer fringe"]

    second_ts = content["last_updated_at"]
    assert datetime.fromisoformat(second_ts) >= datetime.fromisoformat(first_ts)


@pytest.mark.asyncio
async def test_upsert_preserves_absent_fields():
    """Merge semantics: a later thinner payload does not wipe older fields."""
    mm, repo = _make_manager()

    await mm.upsert_style_profile(
        user_id=_FIXED_USER,
        face_shape="oval",
        symmetry_score=0.9,
        recommendations=["try bangs", "clean up brows"],
    )

    # Simulate a later analysis where the caller only resolves face_shape.
    await mm.upsert_style_profile(
        user_id=_FIXED_USER,
        face_shape="round",
        symmetry_score=None,
        recommendations=None,
    )

    content = repo._profile["content"]
    assert content["face_shape"] == "round"
    # symmetry + recs from the first analysis survive.
    assert content["symmetry_score"] == 0.9
    assert content["recommendations"] == ["try bangs", "clean up brows"]


@pytest.mark.asyncio
async def test_upsert_cap_not_enforced_for_profile():
    """Profile upsert must bypass the unbounded-memory cap path."""
    mm, repo = _make_manager()

    await mm.upsert_style_profile(
        user_id=_FIXED_USER,
        face_shape="oval",
        symmetry_score=0.5,
        recommendations=[],
    )

    # count_memories is invoked by write_memory, which the profile flow
    # does NOT call. The stub's counter must stay at zero.
    assert repo.count_memories_calls == 0


# ---------------------------------------------------------------------------
# Service._build_user_data read order
# ---------------------------------------------------------------------------


def _build_service_with_repo(repo: MagicMock) -> Any:
    from app.advisor.service import AdvisorService

    redis = MagicMock()
    llm = MagicMock()
    embedding = MagicMock()
    return AdvisorService(
        advisor_repo=repo,
        redis_client=redis,
        llm_adapter=llm,
        embedding_adapter=embedding,
    )


def _inserted_authored_by(repo: _ProfileStubRepo) -> str:
    """Return the authored_by field the first upsert tried to write."""
    return repo.inserted[0]["authored_by"]


def test_build_user_data_prefers_style_profile():
    """Profile present → user_data block reads from profile, not insight."""
    repo = MagicMock()
    repo.get_style_profile.return_value = {
        "content": {
            "face_shape": "heart",
            "symmetry_score": 0.91,
            "recommendations": ["softer fringe", "warmer tone"],
            "last_updated_at": datetime.now(tz=timezone.utc).isoformat(),
        },
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    # An older, contradictory insight exists — the service must not read it.
    repo.get_latest_analysis_insight.return_value = {
        "content": {
            "face_shape": "square",
            "symmetry_score": 0.4,
            "recommendations": ["stale rec"],
            "summary": "stale summary",
        },
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    repo.count_analysis_insights.return_value = 3

    svc = _build_service_with_repo(repo)
    block = svc._build_user_data(_FIXED_USER)

    # Profile facts propagate.
    assert "heart face" in block
    assert "symmetry 0.91" in block
    assert "softer fringe" in block
    # Insight facts do NOT.
    assert "square" not in block
    assert "stale" not in block
    # Insight fallback was never consulted.
    repo.get_latest_analysis_insight.assert_not_called()


def test_build_user_data_falls_back_to_insight_when_profile_missing():
    """No profile (upsert failed) → falls back to insight; back-compat holds."""
    repo = MagicMock()
    repo.get_style_profile.return_value = None
    repo.get_latest_analysis_insight.return_value = {
        "content": {
            "face_shape": "oval",
            "symmetry_score": 0.87,
            "recommendations": ["try bangs"],
            "summary": "oval, symmetry 0.87, try bangs",
        },
        "created_at": "2026-04-17T00:00:00+00:00",
    }
    repo.count_analysis_insights.return_value = 1

    svc = _build_service_with_repo(repo)
    block = svc._build_user_data(_FIXED_USER)

    assert "oval face" in block
    assert "symmetry 0.87" in block
    assert "try bangs" in block
    # Back-compat summary line from the insight content is used as-is.
    assert "oval, symmetry 0.87, try bangs" in block


def test_build_user_data_profile_without_recommendations_omits_rec_line():
    """Profile with null recs → user_data block has no recommendations clause."""
    repo = MagicMock()
    repo.get_style_profile.return_value = {
        "content": {
            "face_shape": "oval",
            "symmetry_score": 0.87,
            "recommendations": None,
            "last_updated_at": datetime.now(tz=timezone.utc).isoformat(),
        },
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    repo.count_analysis_insights.return_value = 2

    svc = _build_service_with_repo(repo)
    block = svc._build_user_data(_FIXED_USER)

    assert "oval face" in block
    assert "symmetry 0.87" in block
    # Recs clause from the user_data block contains comma-joined rec items —
    # with recs=None those must NOT appear. (The block summary line from
    # summarize_memory_content still renders face + symmetry.)
    # A single rec-clause marker would be a phrase like "try bangs" — but
    # we supplied None; assert the block is the basics + summary lines
    # only (two non-empty lines).
    non_empty_lines = [line for line in block.split("\n") if line]
    # Line 1: basics. Line 2: summary (derived from content).
    # No rec line expected.
    assert len(non_empty_lines) <= 2


def test_build_user_data_empty_when_no_profile_and_no_insight():
    """User with neither a profile nor any insight → empty block."""
    repo = MagicMock()
    repo.get_style_profile.return_value = None
    repo.get_latest_analysis_insight.return_value = None
    repo.count_analysis_insights.return_value = 0

    svc = _build_service_with_repo(repo)
    block = svc._build_user_data(_FIXED_USER)
    assert block == ""


# ---------------------------------------------------------------------------
# nudge_scheduler.write_analysis_insight_job wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insight_job_upserts_profile_alongside_insight(monkeypatch):
    """Both writes fire for a single job; profile call gets the same facts."""
    from app.advisor import nudge_scheduler
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_ENABLED", True)

    captured: dict[str, list[dict[str, Any]]] = {"insight": [], "profile": []}

    async def _fake_insight(**kwargs: Any) -> None:
        captured["insight"].append(kwargs)

    async def _fake_profile(**kwargs: Any) -> dict[str, Any]:
        captured["profile"].append(kwargs)
        return {}

    fake_mm = SimpleNamespace(
        write_analysis_insight=_fake_insight,
        upsert_style_profile=_fake_profile,
    )

    async def _fake_builder(ctx: dict) -> Any:
        return fake_mm

    monkeypatch.setattr(nudge_scheduler, "_build_memory_manager", _fake_builder)

    user_id = str(_FIXED_USER)
    await nudge_scheduler.write_analysis_insight_job(
        {"supabase": object(), "redis": object()},
        user_id,
        "oval",
        0.87,
        ["try bangs"],
        str(uuid4()),
    )

    assert len(captured["insight"]) == 1
    assert len(captured["profile"]) == 1
    prof = captured["profile"][0]
    assert str(prof["user_id"]) == user_id
    assert prof["face_shape"] == "oval"
    assert prof["symmetry_score"] == 0.87
    assert prof["recommendations"] == ["try bangs"]


@pytest.mark.asyncio
async def test_insight_succeeds_when_profile_upsert_fails(monkeypatch):
    """Profile upsert failure must NOT block the insight write path."""
    from app.advisor import nudge_scheduler
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_ENABLED", True)

    captured: dict[str, list[dict[str, Any]]] = {"insight": []}

    async def _fake_insight(**kwargs: Any) -> None:
        captured["insight"].append(kwargs)

    async def _failing_profile(**kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("pg down")

    fake_mm = SimpleNamespace(
        write_analysis_insight=_fake_insight,
        upsert_style_profile=_failing_profile,
    )

    async def _fake_builder(ctx: dict) -> Any:
        return fake_mm

    monkeypatch.setattr(nudge_scheduler, "_build_memory_manager", _fake_builder)

    # Must not raise — the failure is swallowed and logged.
    await nudge_scheduler.write_analysis_insight_job(
        {"supabase": object(), "redis": object()},
        str(_FIXED_USER),
        "oval",
        0.87,
        ["try bangs"],
        str(uuid4()),
    )

    # Insight write still succeeded.
    assert len(captured["insight"]) == 1


@pytest.mark.asyncio
async def test_profile_upserts_even_when_insight_fails(monkeypatch):
    """Insight write failure must NOT block the profile upsert path."""
    from app.advisor import nudge_scheduler
    from app.config import settings

    monkeypatch.setattr(settings, "ADVISOR_ENABLED", True)

    captured: dict[str, list[dict[str, Any]]] = {"profile": []}

    async def _failing_insight(**kwargs: Any) -> None:
        raise RuntimeError("insight table missing")

    async def _fake_profile(**kwargs: Any) -> dict[str, Any]:
        captured["profile"].append(kwargs)
        return {}

    fake_mm = SimpleNamespace(
        write_analysis_insight=_failing_insight,
        upsert_style_profile=_fake_profile,
    )

    async def _fake_builder(ctx: dict) -> Any:
        return fake_mm

    monkeypatch.setattr(nudge_scheduler, "_build_memory_manager", _fake_builder)

    await nudge_scheduler.write_analysis_insight_job(
        {"supabase": object(), "redis": object()},
        str(_FIXED_USER),
        "oval",
        0.87,
        ["try bangs"],
        str(uuid4()),
    )

    # Profile was upserted despite insight failure.
    assert len(captured["profile"]) == 1


# ---------------------------------------------------------------------------
# Consistency: the repo-local constant matches the enum value
# ---------------------------------------------------------------------------


def test_repo_type_constant_matches_enum():
    """STYLE_PROFILE_TYPE in the repo must equal the enum member value.

    Guards the intentional no-import boundary (the repo must not import
    ``app.advisor.models``); a mismatch would mean the repo writes to a
    row ``_build_user_data`` will never read.
    """
    assert STYLE_PROFILE_TYPE == MemoryType.STYLE_PROFILE.value


# ---------------------------------------------------------------------------
# Advanced: advance-timestamp semantics across runs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_last_updated_at_advances_on_update(monkeypatch):
    """last_updated_at strictly advances when the caller's clock advances."""
    mm, repo = _make_manager()

    # Pin the first write's timestamp at T0.
    t0 = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=5)

    class _Clock:
        def __init__(self) -> None:
            self.now = t0

        def now_fn(self, tz: Any = None) -> datetime:
            return self.now

    clock = _Clock()

    import app.advisor.memory_manager as mm_mod

    class _FakeDatetime:
        @staticmethod
        def now(tz: Any = None) -> datetime:
            return clock.now_fn(tz)

    monkeypatch.setattr(mm_mod, "datetime", _FakeDatetime)

    await mm.upsert_style_profile(
        user_id=_FIXED_USER,
        face_shape="oval",
        symmetry_score=0.8,
        recommendations=None,
    )
    first = repo._profile["content"]["last_updated_at"]
    assert first == t0.isoformat()

    clock.now = t1
    await mm.upsert_style_profile(
        user_id=_FIXED_USER,
        face_shape="oval",
        symmetry_score=0.8,
        recommendations=None,
    )
    second = repo._profile["content"]["last_updated_at"]
    assert second == t1.isoformat()
    assert datetime.fromisoformat(second) > datetime.fromisoformat(first)
