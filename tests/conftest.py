"""Shared test fixtures for the NXME test suite.

All fixtures use mocks to avoid requiring a live Supabase or Redis connection.
"""
from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import jwt
import pytest

from app.config import settings


# ---------------------------------------------------------------------------
# FastAPI route-import guard
# ---------------------------------------------------------------------------
# Importing router modules (app.api.posts, app.api.users) triggers FastAPI
# dependency resolution which fails on some FastAPI/Pydantic combos
# (FieldInfo.in_ AttributeError). Detect this once and expose a skip marker.

def _can_import_routers() -> bool:
    try:
        import app.api.users  # noqa: F401
        return True
    except (AttributeError, ImportError):
        return False


_ROUTERS_AVAILABLE = _can_import_routers()

requires_routers = pytest.mark.skipif(
    not _ROUTERS_AVAILABLE,
    reason="FastAPI/Pydantic version mismatch — router import fails (FieldInfo.in_)",
)


# ---------------------------------------------------------------------------
# JWT helper
# ---------------------------------------------------------------------------

_JWT_SECRET = settings.SUPABASE_JWT_SECRET


def make_jwt(
    user_id: str | None = None,
    expired: bool = False,
    extra_claims: dict | None = None,
) -> str:
    """Create a valid (or expired) test JWT signed with the configured secret."""
    uid = user_id or str(uuid4())
    now = int(time.time())
    payload = {
        "sub": uid,
        "iat": now,
        "exp": now - 10 if expired else now + 3600,
        "aud": "authenticated",
        "iss": f"{settings.SUPABASE_URL}/auth/v1",
        "role": "authenticated",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, _JWT_SECRET, algorithm="HS256")


# ---------------------------------------------------------------------------
# Mock Supabase client
# ---------------------------------------------------------------------------


class MockQueryBuilder:
    """Chainable mock for Supabase query builder (table -> select -> eq -> execute)."""

    def __init__(self, data: Any = None, count: int | None = None) -> None:
        self._data = data
        self._count = count

    def select(self, *args: Any, **kwargs: Any) -> "MockQueryBuilder":
        return self

    def insert(self, data: Any, **kwargs: Any) -> "MockQueryBuilder":
        if isinstance(data, dict) and "id" not in data:
            data = {**data, "id": str(uuid4())}
        self._data = [data] if isinstance(data, dict) else data
        return self

    def update(self, data: Any, **kwargs: Any) -> "MockQueryBuilder":
        if self._data is None:
            self._data = [data]
        return self

    def upsert(self, data: Any, **kwargs: Any) -> "MockQueryBuilder":
        self._data = [data] if isinstance(data, dict) else data
        return self

    def delete(self) -> "MockQueryBuilder":
        return self

    def eq(self, *args: Any) -> "MockQueryBuilder":
        return self

    def neq(self, *args: Any) -> "MockQueryBuilder":
        return self

    def gt(self, *args: Any) -> "MockQueryBuilder":
        return self

    def lt(self, *args: Any) -> "MockQueryBuilder":
        return self

    def gte(self, *args: Any) -> "MockQueryBuilder":
        return self

    def in_(self, *args: Any) -> "MockQueryBuilder":
        return self

    def is_(self, *args: Any) -> "MockQueryBuilder":
        return self

    def order(self, *args: Any, **kwargs: Any) -> "MockQueryBuilder":
        return self

    def limit(self, *args: Any) -> "MockQueryBuilder":
        return self

    def single(self) -> "MockQueryBuilder":
        if isinstance(self._data, list) and self._data:
            self._data = self._data[0]
        return self

    def maybe_single(self) -> "MockQueryBuilder":
        if isinstance(self._data, list) and self._data:
            self._data = self._data[0]
        elif isinstance(self._data, list) and not self._data:
            self._data = None
        return self

    def execute(self) -> "MockExecuteResult":
        return MockExecuteResult(data=self._data, count=self._count)


class MockExecuteResult:
    def __init__(self, data: Any = None, count: int | None = None) -> None:
        self.data = data
        self.count = count


class MockRpcResult:
    def __init__(self, data: Any = None) -> None:
        self._data = data

    def execute(self) -> MockExecuteResult:
        return MockExecuteResult(data=self._data)


class MockSupabase:
    """Configurable mock Supabase client.

    Usage:
        sb = MockSupabase()
        sb.set_table_data("users", [{"id": "...", "username": "alice"}])
        sb.set_rpc_data("user_post_stats", [{"post_count": 5, "total_reactions": 10}])
    """

    def __init__(self) -> None:
        self._table_data: dict[str, Any] = {}
        self._rpc_data: dict[str, Any] = {}
        self.auth = MagicMock()
        self.storage = MagicMock()

    def set_table_data(self, table_name: str, data: Any) -> None:
        self._table_data[table_name] = data

    def set_rpc_data(self, rpc_name: str, data: Any) -> None:
        self._rpc_data[rpc_name] = data

    def table(self, name: str) -> MockQueryBuilder:
        data = self._table_data.get(name)
        return MockQueryBuilder(data=data)

    def rpc(self, name: str, params: dict | None = None) -> MockRpcResult:
        data = self._rpc_data.get(name)
        return MockRpcResult(data=data)


# ---------------------------------------------------------------------------
# Mock Redis
# ---------------------------------------------------------------------------


class MockRedis:
    """In-memory Redis mock for rate limiter tests."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    async def get(self, key: str) -> Any:
        return self._store.get(key)

    async def set(self, key: str, value: Any, ex: int | None = None) -> None:
        self._store[key] = value

    async def incr(self, key: str) -> int:
        val = int(self._store.get(key) or 0) + 1
        self._store[key] = val
        return val

    async def decr(self, key: str) -> int:
        val = int(self._store.get(key) or 0) - 1
        self._store[key] = val
        return val

    async def expire(self, key: str, seconds: int, nx: bool = False) -> None:
        pass

    def pipeline(self) -> "MockPipeline":
        return MockPipeline(self)


class MockPipeline:
    """Mock Redis pipeline that executes commands immediately."""

    def __init__(self, redis: MockRedis) -> None:
        self._redis = redis
        self._commands: list[tuple[str, tuple]] = []

    def incr(self, key: str) -> "MockPipeline":
        self._commands.append(("incr", (key,)))
        return self

    def expire(self, key: str, seconds: int, nx: bool = False) -> "MockPipeline":
        self._commands.append(("expire", (key, seconds)))
        return self

    async def execute(self) -> list:
        results = []
        for cmd, args in self._commands:
            if cmd == "incr":
                val = int(self._redis._store.get(args[0]) or 0) + 1
                self._redis._store[args[0]] = val
                results.append(val)
            elif cmd == "expire":
                results.append(True)
        return results


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_supabase() -> MockSupabase:
    """Return a fresh MockSupabase instance."""
    return MockSupabase()


@pytest.fixture
def mock_redis() -> MockRedis:
    """Return a fresh MockRedis instance."""
    return MockRedis()


@pytest.fixture
def user_id() -> str:
    """Return a stable test user UUID string."""
    return "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


@pytest.fixture
def auth_headers(user_id: str) -> dict[str, str]:
    """Return Authorization headers with a valid JWT for the test user."""
    token = make_jwt(user_id=user_id)
    return {"Authorization": f"Bearer {token}"}
