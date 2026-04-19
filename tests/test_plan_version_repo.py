"""Tests for ``app.repositories.plan_version_repo.PlanVersionRepository``.

Covers the scenarios called out in Unit 6 of the payments plan:

* ``get_by_version_num`` returns the seeded ``v1_free_default`` row.
* ``get_active_version_for_user`` resolves to ``v1_pro`` when the user has
  an active subscription pointing at it.
* Same method resolves to ``v1_free_default`` when the user has no
  active subscription.
* ``get_default_free_id`` hits the table once and reuses the cached id
  on the second call.

Uses a handcrafted Supabase mock that actually branches on the fetched
table / ``.eq`` arguments — the shared ``MockSupabase`` in ``conftest.py``
returns the same data regardless of filter arguments and can't express
the "sub join then follow plan_version_id" shape tested here.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from app.repositories.plan_version_repo import (
    FREE_DEFAULT_VERSION_NUM,
    PRO_VERSION_NUM,
    PlanVersionRepository,
)


# ---------------------------------------------------------------------------
# Plan-version row fixtures (shape mirrors the 0048 schema)
# ---------------------------------------------------------------------------

FREE_ID = str(uuid4())
PRO_ID = str(uuid4())


def _free_row() -> dict:
    return {
        "id": FREE_ID,
        "version_num": FREE_DEFAULT_VERSION_NUM,
        "price_usd_cents": 0,
        "monthly_allotment_milli": 0,
        "glowup_cost_milli": 100,
        "ada_cost_milli": 5,
        "stripe_price_id": None,
    }


def _pro_row() -> dict:
    return {
        "id": PRO_ID,
        "version_num": PRO_VERSION_NUM,
        "price_usd_cents": 999,
        "monthly_allotment_milli": 3000,
        "glowup_cost_milli": 100,
        "ada_cost_milli": 5,
        "stripe_price_id": "price_test_pro",
    }


# ---------------------------------------------------------------------------
# Branching Supabase mock
# ---------------------------------------------------------------------------
#
# Supabase's builder is chainable with side-effects only on ``.execute()``.
# We record the ``(table, eq_args)`` tuple as the chain is built and, on
# ``execute``, consult a dispatch function registered by the test. That
# keeps tests declarative — each test defines exactly which table probes
# yield which rows.


class _FakeQuery:
    def __init__(self, dispatch, table_name, counter):
        self._dispatch = dispatch
        self._table = table_name
        self._eqs: list[tuple[str, object]] = []
        self._is_maybe_single = False
        self._counter = counter  # {"plan_versions": int}

    def select(self, *_, **__):
        return self

    def eq(self, col, val):
        self._eqs.append((col, val))
        return self

    def limit(self, *_):
        return self

    def maybe_single(self):
        self._is_maybe_single = True
        return self

    def execute(self):
        if self._table == "plan_versions":
            self._counter["plan_versions"] = self._counter.get("plan_versions", 0) + 1
        rows = self._dispatch(self._table, dict(self._eqs))
        if self._is_maybe_single:
            data = rows[0] if rows else None
        else:
            data = rows
        return MagicMock(data=data)


class _FakeSupabase:
    def __init__(self, dispatch):
        self._dispatch = dispatch
        self.counter: dict[str, int] = {}

    def table(self, name):
        return _FakeQuery(self._dispatch, name, self.counter)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetByVersionNum:
    def test_returns_free_default_row(self):
        def dispatch(table, filters):
            assert table == "plan_versions"
            if filters.get("version_num") == FREE_DEFAULT_VERSION_NUM:
                return [_free_row()]
            return []

        sb = _FakeSupabase(dispatch)
        repo = PlanVersionRepository(sb)

        row = repo.get_by_version_num(FREE_DEFAULT_VERSION_NUM)

        assert row is not None
        assert row["version_num"] == FREE_DEFAULT_VERSION_NUM
        assert row["glowup_cost_milli"] == 100
        assert row["ada_cost_milli"] == 5

    def test_unknown_version_num_returns_none(self):
        def dispatch(table, filters):
            return []

        sb = _FakeSupabase(dispatch)
        repo = PlanVersionRepository(sb)

        assert repo.get_by_version_num("v99_missing") is None


class TestGetActiveVersionForUser:
    def test_pro_user_follows_subscription_plan_version_id(self):
        user_id = uuid4()

        def dispatch(table, filters):
            if table == "subscriptions":
                assert filters.get("user_id") == str(user_id)
                assert filters.get("status") == "active"
                return [{"plan_version_id": PRO_ID}]
            if table == "plan_versions":
                if filters.get("id") == PRO_ID:
                    return [_pro_row()]
            return []

        sb = _FakeSupabase(dispatch)
        repo = PlanVersionRepository(sb)

        row = repo.get_active_version_for_user(user_id)

        assert row["version_num"] == PRO_VERSION_NUM
        assert row["monthly_allotment_milli"] == 3000

    def test_free_user_falls_back_to_free_default(self):
        user_id = uuid4()

        def dispatch(table, filters):
            if table == "subscriptions":
                return []  # no active subscription
            if table == "plan_versions":
                if filters.get("version_num") == FREE_DEFAULT_VERSION_NUM:
                    return [_free_row()]
            return []

        sb = _FakeSupabase(dispatch)
        repo = PlanVersionRepository(sb)

        row = repo.get_active_version_for_user(user_id)

        assert row["version_num"] == FREE_DEFAULT_VERSION_NUM
        assert row["price_usd_cents"] == 0


class TestGetDefaultFreeIdCache:
    def test_second_call_hits_cache(self):
        def dispatch(table, filters):
            if (
                table == "plan_versions"
                and filters.get("version_num") == FREE_DEFAULT_VERSION_NUM
            ):
                return [_free_row()]
            return []

        sb = _FakeSupabase(dispatch)
        repo = PlanVersionRepository(sb)

        first = repo.get_default_free_id()
        second = repo.get_default_free_id()

        assert isinstance(first, UUID)
        assert first == second == UUID(FREE_ID)
        # Cache hit — only the first call should have reached Supabase.
        assert sb.counter["plan_versions"] == 1

    def test_missing_seed_raises(self):
        def dispatch(table, filters):
            return []

        sb = _FakeSupabase(dispatch)
        repo = PlanVersionRepository(sb)

        with pytest.raises(RuntimeError, match="plan_versions seed row"):
            repo.get_default_free_id()
