"""Tests for the ``orphaned_analyses`` DLQ + endpoint wiring.

Two surfaces under test:

1. ``OrphanedAnalysesRepository.record`` — idempotent (unique on
   ``analysis_id``), second call for the same id bumps ``attempts``,
   never raises on underlying DB errors.
2. ``DELETE /v1/jobs/{job_id}`` — when ``delete_analysis_by_id`` raises,
   a DLQ row is recorded with the expected ``(analysis_id, reason)`` and
   the endpoint still returns 204. Happy path writes no DLQ row.

Scope note: this is the write-side only — the future reclaim worker
(out of scope per the plan; see 0047 migration preamble) will test the
read-side (``list_pending`` / ``mark_attempt`` / ``delete``) against a
live DB. This suite uses a tiny in-memory table stub to verify repo
semantics without a Supabase round-trip.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

try:
    from app.api.jobs import delete_job, DELETE_GLOWUP_REASON
    from app.repositories.orphaned_analyses_repo import OrphanedAnalysesRepository
    from fastapi import status

    _ROUTES_AVAILABLE = True
except (ImportError, AttributeError):
    _ROUTES_AVAILABLE = False

from tests.conftest import requires_routers


pytestmark = [
    pytest.mark.skipif(not _ROUTES_AVAILABLE, reason="jobs module unavailable"),
    requires_routers,
]


# ---------------------------------------------------------------------------
# Constants — no magic strings
# ---------------------------------------------------------------------------

_USER_ID = "u-owner"
_JOB_ID = "11111111-1111-1111-1111-111111111111"
_ANALYSIS_ID = "22222222-2222-2222-2222-222222222222"

_SOURCE_TYPE_GLOWUP = "glowup_analysis"
_STATUS_COMPLETED = "completed"

_TABLE_ORPHANED_ANALYSES = "orphaned_analyses"


# ---------------------------------------------------------------------------
# Repository unit tests — in-memory table stub
# ---------------------------------------------------------------------------


class _FakeTable:
    """Minimal supabase-py table stub: INSERT / SELECT / UPDATE / DELETE.

    Only captures the method chain shape the repo actually uses — not a
    general substitute. Each call returns ``self`` until ``.execute()``,
    which inspects the recorded chain and mutates ``rows`` in-place.
    Enough fidelity to prove (a) INSERT on first record, (b) UPDATE on
    conflict bumps attempts, (c) defensive swallow on bad data types.
    """

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self._reset_chain()

    def _reset_chain(self) -> None:
        self._op: str | None = None
        self._select_cols: str | None = None
        self._filters: list[tuple[str, Any]] = []
        self._payload: dict[str, Any] | None = None
        self._maybe_single = False

    # Method chain ------------------------------------------------------

    def select(self, cols: str, **_kwargs: Any) -> "_FakeTable":
        self._op = "select"
        self._select_cols = cols
        return self

    def insert(self, payload: dict[str, Any]) -> "_FakeTable":
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> "_FakeTable":
        self._op = "update"
        self._payload = payload
        return self

    def delete(self) -> "_FakeTable":
        self._op = "delete"
        return self

    def eq(self, col: str, val: Any) -> "_FakeTable":
        self._filters.append((col, val))
        return self

    def maybe_single(self) -> "_FakeTable":
        self._maybe_single = True
        return self

    def order(self, *_a: Any, **_kw: Any) -> "_FakeTable":
        return self

    def limit(self, _n: int) -> "_FakeTable":
        return self

    # Terminal ----------------------------------------------------------

    def execute(self) -> SimpleNamespace:
        op = self._op
        filters = list(self._filters)
        payload = self._payload
        maybe_single = self._maybe_single
        self._reset_chain()

        def _matches(row: dict[str, Any]) -> bool:
            return all(row.get(col) == val for col, val in filters)

        if op == "select":
            matched = [dict(r) for r in self._rows if _matches(r)]
            if maybe_single:
                data: Any = matched[0] if matched else None
            else:
                data = matched
            return SimpleNamespace(data=data, count=len(matched))

        if op == "insert":
            assert payload is not None
            row = {
                "id": str(uuid.uuid4()),
                "attempts": 0,
                "last_attempt_at": None,
                **payload,
            }
            self._rows.append(row)
            return SimpleNamespace(data=[row], count=1)

        if op == "update":
            assert payload is not None
            updated = 0
            for row in self._rows:
                if _matches(row):
                    row.update(payload)
                    updated += 1
            return SimpleNamespace(data=[], count=updated)

        if op == "delete":
            kept: list[dict[str, Any]] = []
            removed = 0
            for row in self._rows:
                if _matches(row):
                    removed += 1
                else:
                    kept.append(row)
            self._rows[:] = kept
            return SimpleNamespace(data=[], count=removed)

        raise RuntimeError(f"unexpected op {op!r}")


class _FakeSupabase:
    """Dict-backed supabase client — one ``_FakeTable`` per name."""

    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {}

    def table(self, name: str) -> _FakeTable:
        rows = self._tables.setdefault(name, [])
        return _FakeTable(rows)


@pytest.mark.skipif(not _ROUTES_AVAILABLE, reason="repo module unavailable")
class TestOrphanedAnalysesRepository:
    """Repo-level tests — prove idempotent upsert semantics."""

    def test_record_inserts_row_on_first_call(self):
        sb = _FakeSupabase()
        repo = OrphanedAnalysesRepository(sb)  # type: ignore[arg-type]

        repo.record(_ANALYSIS_ID, DELETE_GLOWUP_REASON)

        rows = sb._tables[_TABLE_ORPHANED_ANALYSES]
        assert len(rows) == 1
        assert rows[0]["analysis_id"] == _ANALYSIS_ID
        assert rows[0]["reason"] == DELETE_GLOWUP_REASON
        assert rows[0]["attempts"] == 0
        assert rows[0]["last_attempt_at"] is None

    def test_record_is_idempotent_and_bumps_attempts(self):
        """Second call for the same ``analysis_id`` updates in-place.

        Never inserts a duplicate (the real DB has UNIQUE(analysis_id)
        backing this); ``attempts`` is incremented and
        ``last_attempt_at`` is populated.
        """
        sb = _FakeSupabase()
        repo = OrphanedAnalysesRepository(sb)  # type: ignore[arg-type]

        repo.record(_ANALYSIS_ID, DELETE_GLOWUP_REASON)
        repo.record(_ANALYSIS_ID, DELETE_GLOWUP_REASON)
        repo.record(_ANALYSIS_ID, DELETE_GLOWUP_REASON)

        rows = sb._tables[_TABLE_ORPHANED_ANALYSES]
        assert len(rows) == 1, "expected UNIQUE(analysis_id) idempotency"
        assert rows[0]["attempts"] == 2, (
            "two subsequent record() calls should bump attempts from 0 → 1 → 2"
        )
        assert rows[0]["last_attempt_at"] is not None

    def test_record_never_raises_on_underlying_failure(self):
        """If the DB blows up mid-call, ``record`` must swallow — the
        caller is already handling a primary error."""
        sb = MagicMock()
        sb.table.side_effect = RuntimeError("supabase down")
        repo = OrphanedAnalysesRepository(sb)

        # Must not raise.
        repo.record(_ANALYSIS_ID, DELETE_GLOWUP_REASON)

    def test_list_pending_returns_recorded_rows(self):
        """Sanity check for the read path the sweeper will use."""
        sb = _FakeSupabase()
        repo = OrphanedAnalysesRepository(sb)  # type: ignore[arg-type]

        other_id = "33333333-3333-3333-3333-333333333333"
        repo.record(_ANALYSIS_ID, DELETE_GLOWUP_REASON)
        repo.record(other_id, DELETE_GLOWUP_REASON)

        pending = repo.list_pending(limit=10)
        assert {r["analysis_id"] for r in pending} == {_ANALYSIS_ID, other_id}

    def test_delete_removes_row_by_analysis_id(self):
        sb = _FakeSupabase()
        repo = OrphanedAnalysesRepository(sb)  # type: ignore[arg-type]

        repo.record(_ANALYSIS_ID, DELETE_GLOWUP_REASON)
        repo.delete(_ANALYSIS_ID)

        assert sb._tables[_TABLE_ORPHANED_ANALYSES] == []


# ---------------------------------------------------------------------------
# Endpoint integration — delete_job wires record() on exception
# ---------------------------------------------------------------------------


def _make_job() -> dict:
    return {
        "id": _JOB_ID,
        "user_id": _USER_ID,
        "status": _STATUS_COMPLETED,
        "source_type": _SOURCE_TYPE_GLOWUP,
        "source_id": _ANALYSIS_ID,
        "before_image_url": None,
        "after_image_url": None,
    }


class _FakeRedisPipeline:
    """Allow-one-call rate-limiter stub — same shape as cascade tests."""

    def incr(self, _key: str) -> "_FakeRedisPipeline":
        return self

    def expire(self, _key: str, _ttl: int, nx: bool = False) -> "_FakeRedisPipeline":
        return self

    async def execute(self) -> list:
        return [1, True]


def _make_redis() -> MagicMock:
    redis_client = MagicMock()
    redis_client.pipeline = MagicMock(side_effect=lambda: _FakeRedisPipeline())
    redis_client.ttl = AsyncMock(return_value=0)
    return redis_client


def _make_job_repo(*, analysis_raises: bool) -> MagicMock:
    repo = MagicMock()
    repo.get_by_id.return_value = _make_job()
    repo.enumerate_blob_keys_for_delete.return_value = []
    # peer_count = 0 so the endpoint attempts delete_analysis_by_id.
    repo.count_peer_jobs_for_source.return_value = 0
    repo.delete_by_id.return_value = None
    if analysis_raises:
        repo.delete_analysis_by_id.side_effect = RuntimeError("supabase 503")
    else:
        repo.delete_analysis_by_id.return_value = None
    return repo


async def _passthrough_run_sync(fn, *args, **kwargs):
    return fn(*args, **kwargs)


class TestDeleteJobAnalysisDLQ:
    """Endpoint wiring — analysis-delete failure lands in the DLQ."""

    @pytest.mark.asyncio
    async def test_analysis_delete_failure_records_to_dlq_and_returns_204(
        self, monkeypatch
    ):
        """``delete_analysis_by_id`` raises → DLQ has one row with the
        expected ``(analysis_id, reason)``; endpoint still returns 204.
        Jobs row is still gone (cascade ran before the analysis delete).
        """
        monkeypatch.setattr("app.api.jobs.run_sync", _passthrough_run_sync)

        job_repo = _make_job_repo(analysis_raises=True)
        image_repo = MagicMock()
        image_repo.remove.return_value = None
        orphan_repo = MagicMock()
        orphan_repo.record.return_value = None
        orphan_analyses_repo = MagicMock()
        orphan_analyses_repo.record.return_value = None

        response = await delete_job(
            job_id=uuid.UUID(_JOB_ID),
            claims={"sub": _USER_ID},
            redis_client=_make_redis(),
            job_repo=job_repo,
            image_repo=image_repo,
            orphan_repo=orphan_repo,
            orphan_analyses_repo=orphan_analyses_repo,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Jobs row gone — cascade fired before the analysis delete.
        job_repo.delete_by_id.assert_called_once_with(_JOB_ID)

        # DLQ has exactly one record with the expected args.
        orphan_analyses_repo.record.assert_called_once_with(
            _ANALYSIS_ID, DELETE_GLOWUP_REASON
        )

    @pytest.mark.asyncio
    async def test_happy_path_writes_no_dlq_row(self, monkeypatch):
        """Analysis delete succeeds → DLQ is untouched."""
        monkeypatch.setattr("app.api.jobs.run_sync", _passthrough_run_sync)

        job_repo = _make_job_repo(analysis_raises=False)
        image_repo = MagicMock()
        image_repo.remove.return_value = None
        orphan_repo = MagicMock()
        orphan_repo.record.return_value = None
        orphan_analyses_repo = MagicMock()
        orphan_analyses_repo.record.return_value = None

        response = await delete_job(
            job_id=uuid.UUID(_JOB_ID),
            claims={"sub": _USER_ID},
            redis_client=_make_redis(),
            job_repo=job_repo,
            image_repo=image_repo,
            orphan_repo=orphan_repo,
            orphan_analyses_repo=orphan_analyses_repo,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        job_repo.delete_analysis_by_id.assert_called_once_with(_ANALYSIS_ID)
        orphan_analyses_repo.record.assert_not_called()
