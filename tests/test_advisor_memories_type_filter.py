"""GET /v1/memories ?type= filter — handler/service plumbing + 422 contract.

Plan: docs/plans/2026-04-16-004-feat-memories-goals-notes-subtabs-plan.md (Unit 1)

The repository (`get_memories_page`) already supports `type_filter`. This
test pins the new handler -> service -> repo passthrough and the
intentionally-narrow `Literal["goal", "user_note"]` Query contract that
prevents callers from filtering on Ada-internal memory types.

Two layers of coverage:

1. Service-level (fast, no FastAPI lifecycle): build an AdvisorService
   wrapping a fake repo that records the kwargs it receives. Verify that
   ``type_filter`` arrives at the repo verbatim and that pagination
   (``cursor``/``next_cursor``) composes with it.

2. API-level (TestClient against the live app, with auth + service
   dependency-overridden): verify the route returns 422 for any value
   outside the {goal, user_note} allowlist — including the spec'd
   ``analysis_insight`` smuggling case that motivated the narrow Literal.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

# ---------------------------------------------------------------------------
# Service-level fake repo
# ---------------------------------------------------------------------------


class _RecordingMemoryRepo:
    """Fake repo that filters seeded memories by user_id + optional type.

    Mirrors the production behaviour of ``AdvisorRepository.get_memories_page``
    closely enough to exercise the handler/service plumbing without standing
    up Supabase. Records every call so tests can assert kwargs.
    """

    def __init__(self) -> None:
        self.memories: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []

    def add(
        self,
        user_id: str,
        mem_type: str,
        text: str,
        created_at: str,
        memory_id: str | None = None,
    ) -> str:
        mid = memory_id or str(uuid4())
        self.memories.append(
            {
                "id": mid,
                "user_id": user_id,
                "type": mem_type,
                "content": {"text": text},
                "created_at": created_at,
            }
        )
        return mid

    def get_memories_page(
        self,
        user_id: str,
        fetch_limit: int,
        cursor: str | None = None,
        type_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {
                "user_id": user_id,
                "fetch_limit": fetch_limit,
                "cursor": cursor,
                "type_filter": type_filter,
            }
        )
        rows = [m for m in self.memories if m["user_id"] == user_id]
        if type_filter is not None:
            rows = [m for m in rows if m["type"] == type_filter]
        # newest first by created_at, then id (ties)
        rows.sort(key=lambda m: (m["created_at"], m["id"]), reverse=True)
        if cursor:
            cursor_created_at, cursor_id = cursor.split("|", 1)
            rows = [
                m
                for m in rows
                if (m["created_at"], m["id"]) < (cursor_created_at, cursor_id)
            ]
        return rows[:fetch_limit]


def _make_service(repo: _RecordingMemoryRepo):
    """Construct an AdvisorService bypassing __init__ deps not used here."""
    from app.advisor.memory_manager import MemoryManager
    from app.advisor.service import AdvisorService

    svc = AdvisorService.__new__(AdvisorService)
    svc._repo = repo
    embed = MagicMock(compute_embedding=AsyncMock(return_value=[0.0] * 8))
    svc._memory_manager = MemoryManager(
        advisor_repo=repo, llm_adapter=MagicMock(), embedding_adapter=embed
    )
    return svc


def _seed_mixed(
    repo: _RecordingMemoryRepo, user_id: str
) -> tuple[list[str], list[str], list[str]]:
    """Seed 2 goals + 1 user_note + 1 analysis_insight. Return ids per type."""
    g1 = repo.add(user_id, "goal", "g1", "2026-04-10T00:00:00+00:00")
    g2 = repo.add(user_id, "goal", "g2", "2026-04-11T00:00:00+00:00")
    n1 = repo.add(user_id, "user_note", "n1", "2026-04-12T00:00:00+00:00")
    a1 = repo.add(user_id, "analysis_insight", "a1", "2026-04-13T00:00:00+00:00")
    return [g1, g2], [n1], [a1]


# ---------------------------------------------------------------------------
# Service-level happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filter_goal_returns_only_goals():
    repo = _RecordingMemoryRepo()
    user_id = str(uuid4())
    goal_ids, _note_ids, _insight_ids = _seed_mixed(repo, user_id)
    svc = _make_service(repo)

    result = await svc.list_memories_page(UUID(user_id), limit=50, type_filter="goal")

    returned_types = {m["type"] for m in result["memories"]}
    returned_ids = {m["id"] for m in result["memories"]}
    assert returned_types == {"goal"}
    assert returned_ids == set(goal_ids)
    # Plumbing: type_filter reached the repo verbatim.
    assert repo.calls[-1]["type_filter"] == "goal"


@pytest.mark.asyncio
async def test_filter_user_note_returns_only_notes():
    repo = _RecordingMemoryRepo()
    user_id = str(uuid4())
    _goal_ids, note_ids, _insight_ids = _seed_mixed(repo, user_id)
    svc = _make_service(repo)

    result = await svc.list_memories_page(
        UUID(user_id), limit=50, type_filter="user_note"
    )

    returned_types = {m["type"] for m in result["memories"]}
    returned_ids = {m["id"] for m in result["memories"]}
    assert returned_types == {"user_note"}
    assert returned_ids == set(note_ids)
    assert repo.calls[-1]["type_filter"] == "user_note"


@pytest.mark.asyncio
async def test_no_filter_returns_all_types_unchanged():
    """Default behaviour with no type kwarg: every memory type for the user."""
    repo = _RecordingMemoryRepo()
    user_id = str(uuid4())
    _seed_mixed(repo, user_id)
    svc = _make_service(repo)

    result = await svc.list_memories_page(UUID(user_id), limit=50)

    returned_types = {m["type"] for m in result["memories"]}
    assert returned_types == {"goal", "user_note", "analysis_insight"}
    # Plumbing: None must propagate so the repo skips the .eq() filter.
    assert repo.calls[-1]["type_filter"] is None


@pytest.mark.asyncio
async def test_envelope_well_formed_when_filtered_query_exhausts():
    """Single page covers the whole filtered set: has_more=False, next_cursor=None."""
    repo = _RecordingMemoryRepo()
    user_id = str(uuid4())
    _seed_mixed(repo, user_id)
    svc = _make_service(repo)

    result = await svc.list_memories_page(UUID(user_id), limit=50, type_filter="goal")

    assert result["has_more"] is False
    assert result["next_cursor"] is None
    assert len(result["memories"]) == 2


@pytest.mark.asyncio
async def test_filter_composes_with_cursor():
    """Cursor + type_filter compose: page 2 is filtered AND respects the cursor."""
    repo = _RecordingMemoryRepo()
    user_id = str(uuid4())
    # Three goals so the limit=1 cursor walk has somewhere to go.
    g_old = repo.add(user_id, "goal", "old", "2026-04-10T00:00:00+00:00")
    g_mid = repo.add(user_id, "goal", "mid", "2026-04-11T00:00:00+00:00")
    g_new = repo.add(user_id, "goal", "new", "2026-04-12T00:00:00+00:00")
    # Plus a non-goal that must never appear.
    repo.add(user_id, "user_note", "note", "2026-04-13T00:00:00+00:00")
    svc = _make_service(repo)

    page1 = await svc.list_memories_page(UUID(user_id), limit=1, type_filter="goal")
    assert [m["id"] for m in page1["memories"]] == [g_new]
    assert page1["has_more"] is True
    assert page1["next_cursor"] is not None

    page2 = await svc.list_memories_page(
        UUID(user_id),
        limit=1,
        cursor=page1["next_cursor"],
        type_filter="goal",
    )
    assert [m["id"] for m in page2["memories"]] == [g_mid]
    # Repo received both the cursor AND the type_filter together.
    last_call = repo.calls[-1]
    assert last_call["type_filter"] == "goal"
    assert last_call["cursor"] == page1["next_cursor"]

    # Final page: only the oldest goal remains (the user_note is filtered out).
    page3 = await svc.list_memories_page(
        UUID(user_id),
        limit=1,
        cursor=page2["next_cursor"],
        type_filter="goal",
    )
    assert [m["id"] for m in page3["memories"]] == [g_old]
    assert page3["has_more"] is False
    assert page3["next_cursor"] is None


# ---------------------------------------------------------------------------
# API-level: 422 validation contract
# ---------------------------------------------------------------------------
#
# The handler declares ``type: Literal["goal", "user_note"] | None``. FastAPI
# auto-validates the literal and rejects anything else with 422 BEFORE the
# handler body runs — that's the contract Unit 2 will rely on. We probe the
# live app with TestClient and dependency-overrides for auth + service so the
# request reaches FastAPI's query validation without needing Supabase.


_TEST_USER_ID = "11111111-2222-3333-4444-555555555555"


@pytest.fixture(scope="module")
def app_under_test():
    from app.main import app

    return app


@pytest.fixture(scope="module")
def memories_client(app_under_test):
    """TestClient with auth + service overridden so /v1/memories is reachable
    without Supabase. Mirrors the bootstrap pattern in test_auth_invariants.

    The advisor_enabled feature gate is forced on via patching ``is_enabled``
    in the deps module so this test does not depend on the local env's
    ADVISOR_ENABLED setting.
    """
    from fastapi.testclient import TestClient

    from app.api.advisor import get_advisor_service
    from app.api.deps import get_user_or_guest
    from app.api.middleware.auth import UserClaims

    # Stand in for app.state.* that lifespan would normally populate.
    app_under_test.state.supabase = MagicMock()
    redis_mock = AsyncMock()
    redis_mock.incr = AsyncMock(return_value=1)
    redis_mock.expire = AsyncMock(return_value=True)
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock(return_value=True)
    app_under_test.state.redis = redis_mock

    async def _fake_user() -> UserClaims:
        return UserClaims(sub=_TEST_USER_ID, role="authenticated", exp=9999999999)

    fake_svc = MagicMock()
    fake_svc.list_memories_page = AsyncMock(
        return_value={"memories": [], "next_cursor": None, "has_more": False}
    )

    app_under_test.dependency_overrides[get_user_or_guest] = _fake_user
    app_under_test.dependency_overrides[get_advisor_service] = lambda: fake_svc

    try:
        # `require_app_feature("advisor_enabled")` calls into
        # `app.features.is_enabled`. Patch the lookup the deps module uses
        # so the gate always opens for this test, regardless of the local
        # ADVISOR_ENABLED env setting.
        with patch("app.features.is_enabled", return_value=True):
            client = TestClient(app_under_test)
            yield client, fake_svc
    finally:
        app_under_test.dependency_overrides.pop(get_user_or_guest, None)
        app_under_test.dependency_overrides.pop(get_advisor_service, None)
        for attr in ("supabase", "redis"):
            try:
                delattr(app_under_test.state, attr)
            except AttributeError:
                pass


class TestTypeQueryParamValidation:
    """The Literal["goal", "user_note"] contract — must 422 anything else."""

    def test_no_type_param_returns_200(self, memories_client):
        client, fake_svc = memories_client
        resp = client.get("/v1/memories")
        assert resp.status_code == 200, resp.text
        # Service was called with type_filter=None (default propagation).
        kwargs = fake_svc.list_memories_page.call_args.kwargs
        assert kwargs.get("type_filter") is None

    def test_type_goal_returns_200(self, memories_client):
        client, fake_svc = memories_client
        resp = client.get("/v1/memories?type=goal")
        assert resp.status_code == 200, resp.text
        kwargs = fake_svc.list_memories_page.call_args.kwargs
        assert kwargs.get("type_filter") == "goal"

    def test_type_user_note_returns_200(self, memories_client):
        client, fake_svc = memories_client
        resp = client.get("/v1/memories?type=user_note")
        assert resp.status_code == 200, resp.text
        kwargs = fake_svc.list_memories_page.call_args.kwargs
        assert kwargs.get("type_filter") == "user_note"

    def test_type_analysis_insight_returns_422(self, memories_client):
        """Smuggling Ada-internal memory types must be rejected at the gate."""
        client, _fake_svc = memories_client
        resp = client.get("/v1/memories?type=analysis_insight")
        assert resp.status_code == 422, resp.text

    def test_type_accepted_suggestion_returns_422(self, memories_client):
        client, _fake_svc = memories_client
        resp = client.get("/v1/memories?type=accepted_suggestion")
        assert resp.status_code == 422, resp.text

    def test_type_dismissed_suggestion_returns_422(self, memories_client):
        client, _fake_svc = memories_client
        resp = client.get("/v1/memories?type=dismissed_suggestion")
        assert resp.status_code == 422, resp.text

    def test_type_bogus_returns_422(self, memories_client):
        client, _fake_svc = memories_client
        resp = client.get("/v1/memories?type=bogus")
        assert resp.status_code == 422, resp.text
