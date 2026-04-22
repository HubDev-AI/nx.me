"""Tests for ``app.advisor.chat_seeds.build_chat_seeds`` and
``GET /v1/advisor/chat-seeds`` (Plan 2026-04-20-001 Unit 5).

Strategy: direct-handler-call pattern (mirrors ``test_advisor_next_step_endpoint.py``).
  * Patch ``AdvisorRepository`` with a MagicMock whose per-method side
    effects control glow-up resolution and profile fetch.
  * Patch ``_handle_get_latest_glowup`` to return fake image blocks.
  * Replace the LLM adapter with an AsyncMock so we can count Haiku calls
    and inject malformed / good JSON.
  * Use a local Redis double (``_FakeRedis``) that supports ``set(nx=True)``
    returning True/None and a real ``delete`` — conftest's ``MockRedis``
    does not model NX semantics.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.advisor.chat_seed_fallback import FALLBACK_SEEDS
from app.advisor.chat_seeds import (
    CACHE_KEY_FMT,
    COOLDOWN_KEY_FMT,
    COOLDOWN_VALUE,
    LOCK_KEY_FMT,
    SEEDS_COUNT,
    build_chat_seeds,
)


# ---------------------------------------------------------------------------
# Local fakes
# ---------------------------------------------------------------------------


class _FakeRedis:
    """Redis double that models NX semantics and real delete behavior.

    ``set(..., nx=True)`` returns truthy only on first-touch; second SET on
    the same key returns ``None`` — matches ``redis.asyncio`` contract.
    """

    def __init__(self) -> None:
        self.store: dict[str, Any] = {}
        # Records for assertions: how many times each op ran
        self.set_calls: list[tuple[str, Any, dict]] = []
        self.get_calls: list[str] = []
        self.delete_calls: list[str] = []

    async def get(self, key: str) -> Any:
        self.get_calls.append(key)
        return self.store.get(key)

    async def set(
        self,
        key: str,
        value: Any,
        ex: int | None = None,
        nx: bool = False,
        **_: Any,
    ) -> Any:
        self.set_calls.append((key, value, {"ex": ex, "nx": nx}))
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def delete(self, key: str) -> int:
        self.delete_calls.append(key)
        if key in self.store:
            del self.store[key]
            return 1
        return 0


class _RaisingRedis:
    """Redis double where every op raises — simulates total outage."""

    async def get(self, key: str) -> Any:
        raise RuntimeError("redis down")

    async def set(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("redis down")

    async def delete(self, *args: Any, **kwargs: Any) -> int:
        raise RuntimeError("redis down")


def _build_mock_repo(
    *,
    glowup_id: str | None,
    profile_content: dict | None = None,
) -> MagicMock:
    """Return a mocked AdvisorRepository."""
    repo = MagicMock()
    repo.get_latest_completed_glowup_id.return_value = glowup_id
    # Unit 10: build_chat_seeds now uses get_latest_completed_job_with_images
    # to pick the most-recent-of-{glowup, makeup}. Provide a compatible row
    # using the same glowup_id so the cache key stays consistent with tests
    # that assert on CACHE_KEY_FMT.format(..., glowup_id=glowup_id).
    repo.get_latest_completed_job_with_images.return_value = (
        {"id": glowup_id, "source_type": "glowup_analysis"} if glowup_id else None
    )
    repo.get_style_profile.return_value = (
        {"content": profile_content} if profile_content else None
    )
    return repo


def _good_haiku_response_content() -> str:
    """Return a valid strict-JSON response from Haiku with 3 seeds."""
    return json.dumps(
        {
            "seeds": [
                {"label": "Face shape", "text": "what does my face shape suggest?"},
                {"label": "Skin tone", "text": "what makes my skin tone pop?"},
                {"label": "Next glow-up", "text": "what could I try next?"},
            ]
        }
    )


def _llm_mock_returning(text: str) -> MagicMock:
    """Build an LLM adapter mock whose ``create_message`` returns ``text``."""
    llm = MagicMock()

    async def _create(**_: Any) -> Any:
        resp = MagicMock()
        resp.content = text
        resp.input_tokens = 100
        resp.output_tokens = 50
        return resp

    llm.create_message = _create
    # Mirror the wrapped callable so tests can count invocations.
    counter = MagicMock()
    orig = llm.create_message

    async def _counted(**kwargs: Any) -> Any:
        counter(**kwargs)
        return await orig(**kwargs)

    llm.create_message = _counted
    llm.create_message_counter = counter
    return llm


def _image_blocks() -> list[dict[str, Any]]:
    """Return fake image blocks the MCP handler would yield."""
    return [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": "fakebase64before",
            },
        },
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": "fakebase64after",
            },
        },
    ]


async def _fake_handle_get_latest_glowup(_ctx: Any) -> dict[str, Any]:
    """Default MCP handler stub: returns 2 image blocks wrapped in ``content``."""
    return {"content": _image_blocks()}


async def _empty_handle_get_latest_glowup(_ctx: Any) -> dict[str, Any]:
    """MCP handler stub for "no images available"."""
    return {"content": [{"type": "text", "text": "no completed glow-up"}]}


# ---------------------------------------------------------------------------
# Scenario 1: happy cache-miss → Haiku called once → response cached + cooldown set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_miss_calls_haiku_writes_cache_and_cooldown():
    user_id = str(uuid4())
    glowup_id = str(uuid4())
    redis = _FakeRedis()
    llm = _llm_mock_returning(_good_haiku_response_content())
    repo = _build_mock_repo(glowup_id=glowup_id, profile_content={"face_shape": "oval"})

    with (
        patch("app.advisor.chat_seeds.AdvisorRepository", return_value=repo),
        patch(
            "app.advisor.chat_seeds._handle_get_latest_glowup",
            side_effect=_fake_handle_get_latest_glowup,
        ),
    ):
        result = await build_chat_seeds(
            user_id=user_id,
            supabase=MagicMock(),
            redis=redis,
            llm=llm,
        )

    assert len(result.seeds) == SEEDS_COUNT
    assert result.seeds[0].text.endswith("?")
    llm.create_message_counter.assert_called_once()

    cache_key = CACHE_KEY_FMT.format(user_id=user_id, glowup_id=glowup_id)
    cooldown_key = COOLDOWN_KEY_FMT.format(user_id=user_id)
    lock_key = LOCK_KEY_FMT.format(user_id=user_id, glowup_id=glowup_id)

    # Cache + cooldown were set; lock was released.
    assert cache_key in redis.store
    assert redis.store[cooldown_key] == COOLDOWN_VALUE
    assert lock_key not in redis.store


# ---------------------------------------------------------------------------
# Scenario 2: cache hit → no Haiku call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_hit_skips_haiku():
    user_id = str(uuid4())
    glowup_id = str(uuid4())
    redis = _FakeRedis()
    # Pre-populate cache with a valid payload.
    cache_key = CACHE_KEY_FMT.format(user_id=user_id, glowup_id=glowup_id)
    redis.store[cache_key] = json.dumps(
        [
            {"label": "Cached A", "text": "cached question one?"},
            {"label": "Cached B", "text": "cached question two?"},
            {"label": "Cached C", "text": "cached question three?"},
        ]
    )
    llm = _llm_mock_returning("SHOULD NOT BE CALLED")
    repo = _build_mock_repo(glowup_id=glowup_id)

    with (
        patch("app.advisor.chat_seeds.AdvisorRepository", return_value=repo),
        patch(
            "app.advisor.chat_seeds._handle_get_latest_glowup",
            side_effect=_fake_handle_get_latest_glowup,
        ),
    ):
        result = await build_chat_seeds(
            user_id=user_id,
            supabase=MagicMock(),
            redis=redis,
            llm=llm,
        )

    assert [s.label for s in result.seeds] == ["Cached A", "Cached B", "Cached C"]
    llm.create_message_counter.assert_not_called()


# ---------------------------------------------------------------------------
# Scenario 3: no completed glow-up → fallback, no Haiku, no cache write
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_glowup_returns_fallback_without_haiku():
    user_id = str(uuid4())
    redis = _FakeRedis()
    llm = _llm_mock_returning("SHOULD NOT BE CALLED")
    repo = _build_mock_repo(glowup_id=None)

    with patch("app.advisor.chat_seeds.AdvisorRepository", return_value=repo):
        result = await build_chat_seeds(
            user_id=user_id,
            supabase=MagicMock(),
            redis=redis,
            llm=llm,
        )

    # Matches the fallback.
    assert [s.label for s in result.seeds] == [s["label"] for s in FALLBACK_SEEDS]
    llm.create_message_counter.assert_not_called()
    # No cache / cooldown / lock keys were created.
    assert redis.store == {}


# ---------------------------------------------------------------------------
# Scenario 4: cooldown active → fallback, no Haiku
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cooldown_active_returns_fallback_without_haiku():
    user_id = str(uuid4())
    glowup_id = str(uuid4())
    redis = _FakeRedis()
    # Pre-populate cooldown key (no cache — so miss then cooldown-check hits).
    redis.store[COOLDOWN_KEY_FMT.format(user_id=user_id)] = COOLDOWN_VALUE
    llm = _llm_mock_returning("SHOULD NOT BE CALLED")
    repo = _build_mock_repo(glowup_id=glowup_id)

    with patch("app.advisor.chat_seeds.AdvisorRepository", return_value=repo):
        result = await build_chat_seeds(
            user_id=user_id,
            supabase=MagicMock(),
            redis=redis,
            llm=llm,
        )

    assert [s.label for s in result.seeds] == [s["label"] for s in FALLBACK_SEEDS]
    llm.create_message_counter.assert_not_called()


# ---------------------------------------------------------------------------
# Scenario 5: single-flight — two concurrent cold-key requests → exactly 1 Haiku
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_flight_concurrent_requests_call_haiku_once():
    user_id = str(uuid4())
    glowup_id = str(uuid4())
    redis = _FakeRedis()

    # Inject a delay so the second coroutine enters before the first finishes.
    call_count = {"n": 0}

    async def _slow_create(**_: Any) -> Any:
        call_count["n"] += 1
        await asyncio.sleep(0.05)
        resp = MagicMock()
        resp.content = _good_haiku_response_content()
        resp.input_tokens = 100
        resp.output_tokens = 50
        return resp

    llm = MagicMock()
    llm.create_message = _slow_create

    repo = _build_mock_repo(glowup_id=glowup_id)

    with (
        patch("app.advisor.chat_seeds.AdvisorRepository", return_value=repo),
        patch(
            "app.advisor.chat_seeds._handle_get_latest_glowup",
            side_effect=_fake_handle_get_latest_glowup,
        ),
        # Shorten the lock-wait sleep so the test is fast.
        patch("app.advisor.chat_seeds._LOCK_WAIT_SECONDS", 0.01),
    ):
        r1, r2 = await asyncio.gather(
            build_chat_seeds(
                user_id=user_id, supabase=MagicMock(), redis=redis, llm=llm
            ),
            build_chat_seeds(
                user_id=user_id, supabase=MagicMock(), redis=redis, llm=llm
            ),
        )

    # Exactly one Haiku call.
    assert call_count["n"] == 1
    # Both results must be the fresh Haiku payload, not the fallback — the
    # second coroutine hits the cache that the first one wrote.
    _fallback_labels = {s["label"] for s in FALLBACK_SEEDS}
    assert len(r1.seeds) == SEEDS_COUNT
    assert len(r2.seeds) == SEEDS_COUNT
    assert r1.seeds[0].label == "Face shape"
    assert r2.seeds[0].label == "Face shape"
    assert not _fallback_labels.intersection({s.label for s in r1.seeds})
    assert not _fallback_labels.intersection({s.label for s in r2.seeds})


# ---------------------------------------------------------------------------
# Scenario 6: malformed JSON → fallback, cache not written, cooldown IS set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_malformed_json_falls_back_and_sets_cooldown_but_not_cache():
    user_id = str(uuid4())
    glowup_id = str(uuid4())
    redis = _FakeRedis()
    llm = _llm_mock_returning("not valid json at all {{{")
    repo = _build_mock_repo(glowup_id=glowup_id)

    with (
        patch("app.advisor.chat_seeds.AdvisorRepository", return_value=repo),
        patch(
            "app.advisor.chat_seeds._handle_get_latest_glowup",
            side_effect=_fake_handle_get_latest_glowup,
        ),
    ):
        result = await build_chat_seeds(
            user_id=user_id,
            supabase=MagicMock(),
            redis=redis,
            llm=llm,
        )

    assert [s.label for s in result.seeds] == [s["label"] for s in FALLBACK_SEEDS]
    cache_key = CACHE_KEY_FMT.format(user_id=user_id, glowup_id=glowup_id)
    cooldown_key = COOLDOWN_KEY_FMT.format(user_id=user_id)
    assert cache_key not in redis.store
    assert redis.store.get(cooldown_key) == COOLDOWN_VALUE


# ---------------------------------------------------------------------------
# Scenario 7: wrong seed count (2 or 4) → fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("n_seeds", [2, 4])
async def test_wrong_seed_count_falls_back(n_seeds: int):
    user_id = str(uuid4())
    glowup_id = str(uuid4())
    redis = _FakeRedis()
    payload = {
        "seeds": [{"label": f"L{i}", "text": f"question {i}?"} for i in range(n_seeds)]
    }
    llm = _llm_mock_returning(json.dumps(payload))
    repo = _build_mock_repo(glowup_id=glowup_id)

    with (
        patch("app.advisor.chat_seeds.AdvisorRepository", return_value=repo),
        patch(
            "app.advisor.chat_seeds._handle_get_latest_glowup",
            side_effect=_fake_handle_get_latest_glowup,
        ),
    ):
        result = await build_chat_seeds(
            user_id=user_id,
            supabase=MagicMock(),
            redis=redis,
            llm=llm,
        )

    assert [s.label for s in result.seeds] == [s["label"] for s in FALLBACK_SEEDS]


# ---------------------------------------------------------------------------
# Scenario 8: seed missing '?' → fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_missing_question_mark_falls_back():
    user_id = str(uuid4())
    glowup_id = str(uuid4())
    redis = _FakeRedis()
    payload = {
        "seeds": [
            {"label": "A", "text": "question one?"},
            {"label": "B", "text": "question two without mark"},
            {"label": "C", "text": "question three?"},
        ]
    }
    llm = _llm_mock_returning(json.dumps(payload))
    repo = _build_mock_repo(glowup_id=glowup_id)

    with (
        patch("app.advisor.chat_seeds.AdvisorRepository", return_value=repo),
        patch(
            "app.advisor.chat_seeds._handle_get_latest_glowup",
            side_effect=_fake_handle_get_latest_glowup,
        ),
    ):
        result = await build_chat_seeds(
            user_id=user_id,
            supabase=MagicMock(),
            redis=redis,
            llm=llm,
        )

    assert [s.label for s in result.seeds] == [s["label"] for s in FALLBACK_SEEDS]


# ---------------------------------------------------------------------------
# Scenario 9: seed text > 140 chars → fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_text_over_cap_falls_back():
    user_id = str(uuid4())
    glowup_id = str(uuid4())
    redis = _FakeRedis()
    too_long = "a" * 140 + "?"  # 141 chars total
    payload = {
        "seeds": [
            {"label": "A", "text": "ok?"},
            {"label": "B", "text": too_long},
            {"label": "C", "text": "ok?"},
        ]
    }
    llm = _llm_mock_returning(json.dumps(payload))
    repo = _build_mock_repo(glowup_id=glowup_id)

    with (
        patch("app.advisor.chat_seeds.AdvisorRepository", return_value=repo),
        patch(
            "app.advisor.chat_seeds._handle_get_latest_glowup",
            side_effect=_fake_handle_get_latest_glowup,
        ),
    ):
        result = await build_chat_seeds(
            user_id=user_id,
            supabase=MagicMock(),
            redis=redis,
            llm=llm,
        )

    assert [s.label for s in result.seeds] == [s["label"] for s in FALLBACK_SEEDS]


# ---------------------------------------------------------------------------
# Scenario 10: label > 24 chars → fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_label_over_cap_falls_back():
    user_id = str(uuid4())
    glowup_id = str(uuid4())
    redis = _FakeRedis()
    payload = {
        "seeds": [
            {"label": "A", "text": "ok?"},
            {"label": "x" * 25, "text": "ok?"},
            {"label": "C", "text": "ok?"},
        ]
    }
    llm = _llm_mock_returning(json.dumps(payload))
    repo = _build_mock_repo(glowup_id=glowup_id)

    with (
        patch("app.advisor.chat_seeds.AdvisorRepository", return_value=repo),
        patch(
            "app.advisor.chat_seeds._handle_get_latest_glowup",
            side_effect=_fake_handle_get_latest_glowup,
        ),
    ):
        result = await build_chat_seeds(
            user_id=user_id,
            supabase=MagicMock(),
            redis=redis,
            llm=llm,
        )

    assert [s.label for s in result.seeds] == [s["label"] for s in FALLBACK_SEEDS]


# ---------------------------------------------------------------------------
# Scenario 11: Redis outage — every op raises → fallback, no 500
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redis_outage_returns_fallback_without_raising():
    user_id = str(uuid4())
    glowup_id = str(uuid4())
    redis = _RaisingRedis()
    llm = _llm_mock_returning(_good_haiku_response_content())
    repo = _build_mock_repo(glowup_id=glowup_id)

    with (
        patch("app.advisor.chat_seeds.AdvisorRepository", return_value=repo),
        patch(
            "app.advisor.chat_seeds._handle_get_latest_glowup",
            side_effect=_fake_handle_get_latest_glowup,
        ),
        # Keep sleep small in case the flow reaches the lock-wait branch.
        patch("app.advisor.chat_seeds._LOCK_WAIT_SECONDS", 0.01),
    ):
        # Must not raise — the endpoint contract is "never 500s".
        result = await build_chat_seeds(
            user_id=user_id,
            supabase=MagicMock(),
            redis=redis,  # type: ignore[arg-type]
            llm=llm,
        )

    assert len(result.seeds) == SEEDS_COUNT


# ---------------------------------------------------------------------------
# Fallback shape invariants (exactly 3, caps, ends '?')
# ---------------------------------------------------------------------------


def test_fallback_seeds_shape_invariants():
    assert len(FALLBACK_SEEDS) == SEEDS_COUNT
    for seed in FALLBACK_SEEDS:
        assert isinstance(seed["label"], str) and seed["label"]
        assert isinstance(seed["text"], str) and seed["text"]
        assert len(seed["label"]) <= 24
        assert len(seed["text"]) <= 140
        assert seed["text"].endswith("?")


# ---------------------------------------------------------------------------
# Endpoint-level gate tests (advisor_enabled off → 403; unauthenticated → 401)
#
# These mirror ``test_advisor_next_step_endpoint.py`` and exercise the
# router-level require_app_feature("advisor_enabled") dependency.  We call
# the underlying dependency directly rather than spinning up a TestClient
# (the `_ROUTERS_AVAILABLE` guard in conftest would skip it).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feature_disabled_raises_403():
    from app.api.deps import require_app_feature
    from app.config import settings as real_settings

    dep = require_app_feature("advisor_enabled")
    with patch.object(real_settings, "ADVISOR_ENABLED", False):
        with pytest.raises(HTTPException) as exc_info:
            await dep()

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error"]["code"] == "FEATURE_DISABLED"


@pytest.mark.asyncio
async def test_unauthenticated_raises_401():
    """get_current_user — the shared auth dep — returns 401 when JWT is absent.

    The real dep signature is ``(authorization, supabase, redis_client)``.
    Call directly with authorization=None (FastAPI's default when no header
    is present) and stub the downstream deps with MagicMock.
    """
    from app.api.deps import get_current_user

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(
            authorization=None,
            supabase=MagicMock(),
            redis_client=MagicMock(),
        )

    assert exc_info.value.status_code == 401
