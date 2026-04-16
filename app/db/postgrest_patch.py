"""Workaround for postgrest-py 1.0.2 bug with 204 responses.

When a `.maybe_single()` query hits a row that isn't there, newer PostgREST
versions reply with `204 No Content` (empty body). postgrest-py 1.0.2 doesn't
recognize this as "no row"; it parses the empty body as a ValidationError and
re-raises an `APIError` with code `"204"` and message "Missing response".

The intended contract of `.maybe_single()` is "row or None". This module
monkey-patches both the sync and async variants so the 204 APIError is
swallowed and `None` is returned, matching the original contract and what
every call site already checks for (`if not result or not result.data`).

Remove once we upgrade to a version of postgrest-py that handles 204 natively
(fixed upstream after 1.0.2).
"""

from __future__ import annotations

from postgrest._async.request_builder import AsyncMaybeSingleRequestBuilder
from postgrest._sync.request_builder import SyncMaybeSingleRequestBuilder
from postgrest.exceptions import APIError

_MISSING_RESPONSE_CODE = "204"

_original_sync_execute = SyncMaybeSingleRequestBuilder.execute
_original_async_execute = AsyncMaybeSingleRequestBuilder.execute


def _sync_execute(self):  # type: ignore[no-untyped-def]
    try:
        return _original_sync_execute(self)
    except APIError as exc:
        if exc.code == _MISSING_RESPONSE_CODE:
            return None
        raise


async def _async_execute(self):  # type: ignore[no-untyped-def]
    try:
        return await _original_async_execute(self)
    except APIError as exc:
        if exc.code == _MISSING_RESPONSE_CODE:
            return None
        raise


SyncMaybeSingleRequestBuilder.execute = _sync_execute  # type: ignore[method-assign]
AsyncMaybeSingleRequestBuilder.execute = _async_execute  # type: ignore[method-assign]
