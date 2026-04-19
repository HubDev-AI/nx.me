"""Signup-grant fingerprint repository — guards the 300-milli signup credit.

Encapsulates reads and writes against ``signup_grants_issued`` (migration
0052). The table is service-role-only (RLS deny-all for anon +
authenticated) and persists a pair of hashes derived from the mobile
installation UUID — never the UUID itself. See
``app/entitlement/fingerprint.py`` + the 0052 migration header for the
rationale on why the table survives ``delete_account``.

Rotation protocol:

* ``SIGNUP_FINGERPRINT_SERVER_SECRET`` is comma-separated
  ``PRIMARY[,SECONDARY]``.
* ``exists(installation_uuid)`` derives a hash under each currently-active
  secret and probes the table in order (primary first). If we only probed
  primary during a rotation window, old rows (hashed under the previous
  primary) would be invisible and the anti-abuse check would silently
  fail open (security review HIGH).
* ``insert`` takes the already-derived hashes from the caller. Writes
  always use the primary secret — the caller derives the hash via
  ``compute_deterministic_hash(uuid, get_primary_secret())``.

Sync-Supabase repo shape mirrors ``app/repositories/subscription_repo.py``.
"""

from __future__ import annotations

import logging
from datetime import datetime

from supabase import Client

from app.entitlement.fingerprint import (
    compute_deterministic_hash,
    get_server_secrets,
)

logger = logging.getLogger(__name__)

# Name kept next to the repo so nightly-sweep workers and tests reference
# the same literal. Table itself is introduced by migration 0052.
TABLE_NAME = "signup_grants_issued"


class SignupGrantRepository:
    """Lookups + writes for the ``signup_grants_issued`` fingerprint table."""

    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def exists(self, installation_uuid: str) -> bool:
        """Return True if the installation UUID has been granted already.

        Rotation-aware: derives ``deterministic_hash`` once per configured
        server secret (primary first, secondary if present) and probes the
        table. The first hit wins. During a rotation window the table still
        holds rows hashed under the previous secret — if we only probed
        primary, those rows would be invisible and the anti-abuse check
        would silently fail open (security review HIGH).

        The spec signature in the plan reads ``(deterministic_hash: bytes)``
        but that is inconsistent with the "tries each server_secret in
        order" requirement on the same line (a precomputed hash cannot
        iterate secrets). The signature below reconciles the two by taking
        the raw ``installation_uuid`` and deriving per-secret inside the
        method — matching the caller-side tests and the rotation protocol.
        """
        for secret in get_server_secrets():
            hashed = compute_deterministic_hash(installation_uuid, secret)
            if self._probe_hash(hashed):
                return True
        return False

    def _probe_hash(self, deterministic_hash: bytes) -> bool:
        """Internal — single-PK lookup for an already-derived hash."""
        result = (
            self._sb.table(TABLE_NAME)
            .select("deterministic_hash")
            .eq("deterministic_hash", deterministic_hash)
            .limit(1)
            .execute()
        )
        return bool(result.data)

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def insert(
        self,
        deterministic_hash: bytes,
        protected_hash: bytes,
        salt: bytes,
    ) -> None:
        """Insert a freshly-issued grant row.

        ``deterministic_hash`` MUST be derived under the primary secret;
        ``salt`` is fresh per row. ``issued_at`` defaults to ``now()`` in
        the migration so we don't set it here.
        """
        self._sb.table(TABLE_NAME).insert(
            {
                "deterministic_hash": deterministic_hash,
                "protected_hash": protected_hash,
                "salt": salt,
            }
        ).execute()

    # ------------------------------------------------------------------
    # Nightly TTL sweep (used by Unit 9's fingerprint purge worker)
    # ------------------------------------------------------------------

    def purge_older_than(self, cutoff: datetime) -> int:
        """Delete rows with ``issued_at < cutoff``; return deleted count.

        The nightly ARQ worker picks a cutoff = ``now() - 12 months`` (per
        the 0052 header). Returning a count lets the worker emit metrics
        without re-counting.
        """
        result = (
            self._sb.table(TABLE_NAME)
            .delete()
            .lt("issued_at", cutoff.isoformat())
            .execute()
        )
        if not result.data:
            return 0
        return len(result.data)
