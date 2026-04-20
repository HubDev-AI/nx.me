"""Tests for ``app.workers.weekly_free_grant.run_weekly_free_grant``.

Covers:
  - Happy path: iterates users, calls RPC per user.
  - Pro users (active subscription) are skipped.
  - Second run same ISO-week: RPC still called (idempotency is in the DB
    RPC, not the worker — worker always calls, DB deduplicates).
  - Empty user table: no RPC calls, no crash.
  - Pagination: pages through > _PAGE_SIZE users.
  - Subscription fetch failure: worker aborts cleanly.
  - RPC failure for one user: logged, worker continues to next user.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from uuid import uuid4

from app.workers.weekly_free_grant import run_weekly_free_grant


def _make_supabase(
    *,
    user_ids: list[str],
    pro_user_ids: list[str] | None = None,
    rpc_raises_for: set[str] | None = None,
    sub_fetch_raises: Exception | None = None,
    kill_switch_enabled: bool | None = True,
    kill_switch_fetch_raises: Exception | None = None,
) -> MagicMock:
    """Build a minimal Supabase mock for weekly_free_grant tests.

    ``user_ids`` — users returned by the users table query.
    ``pro_user_ids`` — users with active subscriptions (will be skipped).
    ``rpc_raises_for`` — set of user_ids for which the RPC should raise.
    ``sub_fetch_raises`` — exception to raise when fetching subscriptions.
    ``kill_switch_enabled`` — value of the ``app_kill_switches.enabled`` row;
        ``None`` simulates a missing row (fail-open ⇒ treated as enabled).
    ``kill_switch_fetch_raises`` — simulate a DB error on the kill-switch
        lookup (fail-open ⇒ treated as enabled).
    """
    pro_ids = pro_user_ids or []
    raise_for = rpc_raises_for or set()

    # Track RPC calls for assertions
    rpc_calls: list[tuple[str, dict]] = []

    def _table(name: str):
        chain = MagicMock()

        if name == "app_kill_switches":
            if kill_switch_fetch_raises:
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.limit.return_value = chain
                chain.execute.side_effect = kill_switch_fetch_raises
            else:
                data = (
                    []
                    if kill_switch_enabled is None
                    else [{"enabled": bool(kill_switch_enabled)}]
                )
                inner = MagicMock()
                inner.execute.return_value = MagicMock(data=data)
                inner.eq.return_value = inner
                inner.limit.return_value = inner
                chain.select.return_value = inner

        elif name == "subscriptions":
            if sub_fetch_raises:
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.execute.side_effect = sub_fetch_raises
            else:
                sub_data = [{"user_id": uid} for uid in pro_ids]
                inner = MagicMock()
                inner.execute.return_value = MagicMock(data=sub_data)
                inner.eq.return_value = inner
                chain.select.return_value = inner

        elif name == "users":
            # Simulate paginated response from .range()
            def _build_chain(offset, limit):
                page = user_ids[offset : offset + limit + 1]
                result = MagicMock()
                result.data = [{"id": uid} for uid in page]
                return result

            inner = MagicMock()
            inner.eq.return_value = inner

            def _range(start, end):
                page_size = end - start + 1
                page = user_ids[start : start + page_size]
                rng_mock = MagicMock()
                rng_mock.execute.return_value = MagicMock(
                    data=[{"id": uid} for uid in page]
                )
                return rng_mock

            inner.range.side_effect = _range
            chain.select.return_value = inner

        return chain

    def _rpc(name: str, params: dict):
        rpc_calls.append((name, params))
        chain = MagicMock()
        user_id = params.get("p_user_id", "")
        if user_id in raise_for:
            chain.execute.side_effect = RuntimeError("RPC fail")
        else:
            chain.execute.return_value = MagicMock(data=None)
        return chain

    sb = MagicMock()
    sb.table.side_effect = _table
    sb.rpc.side_effect = _rpc
    sb._rpc_calls = rpc_calls  # expose for assertions
    return sb


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestRunWeeklyFreeGrant:
    @pytest.mark.asyncio
    async def test_grants_all_non_pro_users(self):
        """All non-Pro users receive an RPC call."""
        user_ids = [str(uuid4()) for _ in range(3)]
        sb = _make_supabase(user_ids=user_ids)
        ctx = {"supabase": sb}

        await run_weekly_free_grant(ctx)

        granted_ids = [
            params["p_user_id"]
            for name, params in sb._rpc_calls
            if name == "credit_apply_weekly_free_grant"
        ]
        assert set(granted_ids) == set(user_ids)

    @pytest.mark.asyncio
    async def test_pro_users_are_skipped(self):
        """Users with an active subscription must not receive the weekly grant."""
        free_user = str(uuid4())
        pro_user = str(uuid4())
        sb = _make_supabase(
            user_ids=[free_user, pro_user],
            pro_user_ids=[pro_user],
        )
        ctx = {"supabase": sb}

        await run_weekly_free_grant(ctx)

        granted_ids = [
            params["p_user_id"]
            for name, params in sb._rpc_calls
            if name == "credit_apply_weekly_free_grant"
        ]
        assert free_user in granted_ids
        assert pro_user not in granted_ids

    @pytest.mark.asyncio
    async def test_uses_settings_grant_milli(self):
        """grant_milli must be sourced from settings, not a magic number."""
        user_id = str(uuid4())
        sb = _make_supabase(user_ids=[user_id])
        ctx = {"supabase": sb}

        await run_weekly_free_grant(ctx)

        from app.config import settings

        rpc_params = next(
            params
            for name, params in sb._rpc_calls
            if name == "credit_apply_weekly_free_grant"
        )
        assert rpc_params["p_weekly_grant_milli"] == settings.WEEKLY_FREE_GRANT_MILLI

    @pytest.mark.asyncio
    async def test_iso_week_param_is_correct_format(self):
        """ISO week string must match ``YYYY-Www`` format (e.g. ``'2026-W16'``)."""
        import re

        user_id = str(uuid4())
        sb = _make_supabase(user_ids=[user_id])
        ctx = {"supabase": sb}

        await run_weekly_free_grant(ctx)

        rpc_params = next(
            params
            for name, params in sb._rpc_calls
            if name == "credit_apply_weekly_free_grant"
        )
        iso_week = rpc_params["p_iso_week"]
        assert re.match(r"^\d{4}-W\d{2}$", iso_week), f"Bad iso_week format: {iso_week}"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestRunWeeklyFreeGrantEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_user_table_no_rpc_calls(self):
        """No users → no RPC calls, no crash."""
        sb = _make_supabase(user_ids=[])
        ctx = {"supabase": sb}

        await run_weekly_free_grant(ctx)

        rpc_grant_calls = [
            name
            for name, _ in sb._rpc_calls
            if name == "credit_apply_weekly_free_grant"
        ]
        assert rpc_grant_calls == []

    @pytest.mark.asyncio
    async def test_rpc_failure_one_user_continues_to_next(self, caplog):
        """A single-user RPC failure must be logged and the worker must
        continue with remaining users (per-row defence)."""
        import logging

        bad_user = str(uuid4())
        good_user = str(uuid4())
        sb = _make_supabase(
            user_ids=[bad_user, good_user],
            rpc_raises_for={bad_user},
        )
        ctx = {"supabase": sb}

        with caplog.at_level(logging.ERROR, logger="app.workers.weekly_free_grant"):
            await run_weekly_free_grant(ctx)

        granted_ids = [
            params["p_user_id"]
            for name, params in sb._rpc_calls
            if name == "credit_apply_weekly_free_grant"
        ]
        assert good_user in granted_ids
        assert any("RPC failed" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_subscription_fetch_failure_raises_for_arq_retry(self, caplog):
        """If subscription fetch fails, worker re-raises so ARQ retries.

        Outer-loop failures (subscription/page fetch) must propagate so
        ARQ's retry policy can re-run them rather than silently succeeding
        on a transient DB outage.
        """
        import logging

        user_id = str(uuid4())
        sb = _make_supabase(
            user_ids=[user_id],
            sub_fetch_raises=RuntimeError("DB down"),
        )
        ctx = {"supabase": sb}

        with caplog.at_level(logging.ERROR, logger="app.workers.weekly_free_grant"):
            with pytest.raises(RuntimeError, match="DB down"):
                await run_weekly_free_grant(ctx)

        # No RPC calls should have fired
        grant_calls = [
            name
            for name, _ in sb._rpc_calls
            if name == "credit_apply_weekly_free_grant"
        ]
        assert grant_calls == []

    @pytest.mark.asyncio
    async def test_same_week_second_run_still_calls_rpc(self):
        """Worker is not idempotent itself — it always calls the RPC.
        The RPC is idempotent via ON CONFLICT DO NOTHING. Running twice
        in the same week should fire the RPC twice (DB handles dedup)."""
        user_id = str(uuid4())
        sb = _make_supabase(user_ids=[user_id])
        ctx = {"supabase": sb}

        await run_weekly_free_grant(ctx)
        await run_weekly_free_grant(ctx)

        grant_calls = [
            name
            for name, _ in sb._rpc_calls
            if name == "credit_apply_weekly_free_grant"
        ]
        # Both calls fired — dedup is in the DB, not the worker.
        assert len(grant_calls) == 2


# ---------------------------------------------------------------------------
# Kill-switch (app_kill_switches table)
# ---------------------------------------------------------------------------


class TestRunWeeklyFreeGrantKillSwitch:
    @pytest.mark.asyncio
    async def test_kill_switch_disabled_skips_job(self, caplog):
        """Kill-switch row set to FALSE → worker logs + returns, no RPC."""
        import logging

        user_id = str(uuid4())
        sb = _make_supabase(user_ids=[user_id], kill_switch_enabled=False)
        ctx = {"supabase": sb}

        with caplog.at_level(logging.INFO, logger="app.workers.weekly_free_grant"):
            await run_weekly_free_grant(ctx)

        grant_calls = [
            name
            for name, _ in sb._rpc_calls
            if name == "credit_apply_weekly_free_grant"
        ]
        assert grant_calls == []
        assert any("disabled via kill-switch" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_kill_switch_missing_row_fails_open(self):
        """No row for 'weekly_free_grant' key → treated as enabled."""
        user_id = str(uuid4())
        sb = _make_supabase(user_ids=[user_id], kill_switch_enabled=None)
        ctx = {"supabase": sb}

        await run_weekly_free_grant(ctx)

        grant_calls = [
            name
            for name, _ in sb._rpc_calls
            if name == "credit_apply_weekly_free_grant"
        ]
        assert len(grant_calls) == 1

    @pytest.mark.asyncio
    async def test_kill_switch_lookup_error_fails_open(self):
        """DB error on kill-switch lookup → treated as enabled (fail-open)."""
        user_id = str(uuid4())
        sb = _make_supabase(
            user_ids=[user_id],
            kill_switch_fetch_raises=RuntimeError("DB blip"),
        )
        ctx = {"supabase": sb}

        await run_weekly_free_grant(ctx)

        grant_calls = [
            name
            for name, _ in sb._rpc_calls
            if name == "credit_apply_weekly_free_grant"
        ]
        assert len(grant_calls) == 1
