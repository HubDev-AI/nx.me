"""Shared PostgreSQL error helpers.

Centralises the unique-violation detection that was previously
reimplemented at three call sites (``app/api/posts.py``,
``app/advisor/memory_manager.py``, ``app/entitlement/trial_grantor.py``).
Keeping one source of truth removes drift risk when the Supabase/psycopg
client surface rotates between wrapper versions.

Detection strategy is the union of the three historic heuristics:

1. ``exc.code == "23505"`` — Supabase / PostgREST ``APIError`` exposes the
   PostgreSQL SQLSTATE here.
2. ``exc.pgcode == "23505"`` — psycopg2 (and psycopg3) ``IntegrityError``
   uses ``pgcode`` instead of ``code``.
3. Message fallback — for clients whose wrapper drops both structured
   attributes, match any of ``"23505"``, ``"unique_violation"``, or
   ``"unique" + ("violat" | "duplicat")`` in the lowercased message.

The code is kept literal (no imports of moving psycopg/postgrest error
modules) so the check survives version drift across the clients we call.
"""

from __future__ import annotations

_PG_UNIQUE_VIOLATION_SQLSTATE = "23505"


def is_unique_violation(exc: Exception) -> bool:
    """Return True iff ``exc`` is a PostgreSQL ``unique_violation`` (SQLSTATE 23505).

    Matches both the Supabase/PostgREST ``APIError.code`` and the
    psycopg2/psycopg3 ``IntegrityError.pgcode`` paths, plus a string
    fallback for clients that surface neither attribute.
    """
    if getattr(exc, "code", None) == _PG_UNIQUE_VIOLATION_SQLSTATE:
        return True
    if getattr(exc, "pgcode", None) == _PG_UNIQUE_VIOLATION_SQLSTATE:
        return True
    message = str(exc).lower()
    if _PG_UNIQUE_VIOLATION_SQLSTATE in message:
        return True
    if "unique_violation" in message:
        return True
    if "unique" in message and ("violat" in message or "duplicat" in message):
        return True
    return False


__all__ = ["is_unique_violation"]
