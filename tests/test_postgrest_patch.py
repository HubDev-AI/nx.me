"""Verify the postgrest-py 204 workaround in app/db/postgrest_patch.py.

postgrest-py 1.0.2 raises `APIError(code="204", message="Missing response")`
when a `.maybe_single()` call returns 204 No Content — this breaks every
`.maybe_single().execute()` site in the codebase against newer PostgREST.

The patch wraps sync + async `MaybeSingleRequestBuilder.execute`:
- code "204" → return None (matches original contract)
- any other code → re-raise
"""

from __future__ import annotations

import pytest
from postgrest._async.request_builder import AsyncMaybeSingleRequestBuilder
from postgrest._sync.request_builder import SyncMaybeSingleRequestBuilder
from postgrest.exceptions import APIError

# Importing applies the monkey-patch; call sites below invoke the patched
# `.execute` directly via the class method.
from app.db import postgrest_patch  # noqa: F401


_BOGUS_204 = {
    "message": "Missing response",
    "code": "204",
    "hint": "x",
    "details": "y",
}
_REAL_ERROR = {
    "message": "oops",
    "code": "42P01",
    "hint": "",
    "details": "relation does not exist",
}


def test_sync_returns_none_on_bogus_204(monkeypatch):
    def _raise(_self):
        raise APIError(_BOGUS_204)

    monkeypatch.setattr(postgrest_patch, "_original_sync_execute", _raise)

    assert SyncMaybeSingleRequestBuilder.execute(None) is None


def test_sync_reraises_other_errors(monkeypatch):
    def _raise(_self):
        raise APIError(_REAL_ERROR)

    monkeypatch.setattr(postgrest_patch, "_original_sync_execute", _raise)

    with pytest.raises(APIError) as exc_info:
        SyncMaybeSingleRequestBuilder.execute(None)
    assert exc_info.value.code == "42P01"


@pytest.mark.asyncio
async def test_async_returns_none_on_bogus_204(monkeypatch):
    async def _raise(_self):
        raise APIError(_BOGUS_204)

    monkeypatch.setattr(postgrest_patch, "_original_async_execute", _raise)

    assert await AsyncMaybeSingleRequestBuilder.execute(None) is None


@pytest.mark.asyncio
async def test_async_reraises_other_errors(monkeypatch):
    async def _raise(_self):
        raise APIError(_REAL_ERROR)

    monkeypatch.setattr(postgrest_patch, "_original_async_execute", _raise)

    with pytest.raises(APIError) as exc_info:
        await AsyncMaybeSingleRequestBuilder.execute(None)
    assert exc_info.value.code == "42P01"
