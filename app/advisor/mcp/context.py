"""Request-scoped MCP context — immutable carrier for user-scoped data access.

Plan 2026-04-17-003 Unit 9 — cross-user isolation layer 1.

The context is constructed once per chat turn from the JWT claims at the
API boundary (``app/api/advisor.py``). Its ``user_id`` must NOT change
mid-turn — any handler that writes to it bypasses every downstream filter
and trivially leaks another user's data. ``frozen=True`` makes reassignment
of any field raise ``dataclasses.FrozenInstanceError`` so the invariant is
enforced by the interpreter, not by convention.

Handlers should treat the context as read-only and pass ``ctx.user_id``
into every repository call — that is the second layer of the 4-layer
lockdown (layer 1 = frozen context; layer 2 = always filter by this uid;
layer 3 = registry strips unknown/hostile LLM args before handler runs;
layer 4 = Supabase RLS on every queried table).
"""

from __future__ import annotations

from dataclasses import dataclass
from logging import Logger
from typing import Any
from uuid import UUID

from app.repositories.advisor_repo import AdvisorRepository


@dataclass(frozen=True)
class McpContext:
    """Immutable per-turn context passed to every tool handler.

    ``frozen=True`` guarantees that neither Ada's code path nor a compromised
    tool handler can reassign ``user_id`` to promote itself into another
    user's scope. Attempts to mutate a field raise
    ``dataclasses.FrozenInstanceError``.

    Fields:
        user_id: Authenticated user's UUID from JWT ``claims["sub"]``.
        supabase: Supabase client with service-role credentials — never
            passed through to the LLM.
        advisor_repo: Preconfigured ``AdvisorRepository`` for the request.
        logger: Structured logger for per-tool invocation records.
    """

    user_id: UUID
    supabase: Any
    advisor_repo: AdvisorRepository
    logger: Logger
