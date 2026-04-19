"""Fingerprint hashing helpers for the signup-grant anti-abuse registry (R6a).

The mobile app generates a stable installation UUID on first launch and
sends it on auth endpoints via the ``X-Install-UUID`` header. The backend
turns that UUID into two hashes before it ever touches the DB:

* ``deterministic_hash = HMAC-SHA256(server_secret, installation_uuid)``
  — the lookup key. Stable for a given ``(server_secret, uuid)`` pair so
  ``SignupGrantRepository.exists`` is a single PK probe.
* ``protected_hash = SHA256(salt || installation_uuid)`` with a fresh
  32-byte random salt per row — the at-rest defense against someone who
  dumps the table and tries to brute-force the UUID space.

Rotation protocol (per the plan's Key Technical Decisions section +
``docs/runbooks/payments.md``): ``SIGNUP_FINGERPRINT_SERVER_SECRET`` is a
comma-separated list ``PRIMARY[,SECONDARY]``. Lookups try primary first,
then the secondary (if present) so existing rows stay matchable while a
background job re-derives every row under the new primary. Once the
re-derive is complete, deploy with only the new primary. Writes always
use the primary — ``get_primary_secret`` is the single source of truth
for that direction. Planned rotations only; no emergency path.

Helpers are deliberately thin: stdlib ``hmac`` / ``hashlib`` / ``secrets``
do the heavy lifting, and ``get_server_secrets`` fails fast if the env
var is missing or blank (per ``feedback_no_env_fallbacks``).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from app.config import settings

# ``signup_grants_issued.salt`` is declared BYTEA and holds a fresh per-row
# random salt. 32 bytes / 256 bits matches the MIGRATION comment in
# ``0052_signup_grants_issued.sql`` and gives enough entropy to make
# precomputed rainbow tables infeasible.
SALT_BYTES = 32


def compute_deterministic_hash(installation_uuid: str, server_secret: bytes) -> bytes:
    """Return HMAC-SHA256 of the installation UUID keyed by ``server_secret``.

    Output is deterministic for a given ``(server_secret, installation_uuid)``
    pair so callers can probe ``signup_grants_issued`` in a single lookup.
    """
    return hmac.new(server_secret, installation_uuid.encode(), hashlib.sha256).digest()


def compute_protected_hash(installation_uuid: str, salt: bytes) -> bytes:
    """Return SHA-256 of ``salt || installation_uuid``.

    Unlike ``compute_deterministic_hash`` this is unique per row — each row
    stores its own random ``salt`` so two installations that share a UUID
    produce different protected hashes. Purely at-rest protection; never a
    lookup key.
    """
    return hashlib.sha256(salt + installation_uuid.encode()).digest()


def generate_salt() -> bytes:
    """Return a fresh cryptographically-random salt suitable for ``protected_hash``."""
    return secrets.token_bytes(SALT_BYTES)


def get_server_secrets() -> list[bytes]:
    """Parse ``SIGNUP_FINGERPRINT_SERVER_SECRET`` into an ordered secret list.

    The env var is comma-separated ``PRIMARY[,SECONDARY]`` — primary first,
    optional secondary second. Lookups should try each entry in order;
    writes always use the first entry (use ``get_primary_secret``).

    Raises ``ValueError`` when the env var is empty or only whitespace or
    only commas — callers MUST fail fast rather than silently disabling
    abuse prevention (``feedback_no_env_fallbacks``).
    """
    raw = settings.SIGNUP_FINGERPRINT_SERVER_SECRET
    if not raw:
        raise ValueError(
            "SIGNUP_FINGERPRINT_SERVER_SECRET is required "
            "(expected PRIMARY[,SECONDARY])."
        )
    parts = [chunk.strip().encode() for chunk in raw.split(",") if chunk.strip()]
    if not parts:
        raise ValueError(
            "SIGNUP_FINGERPRINT_SERVER_SECRET is required "
            "(expected PRIMARY[,SECONDARY])."
        )
    for s in parts:
        if len(s) < 32:
            raise ValueError(
                f"SIGNUP_FINGERPRINT_SERVER_SECRET entry is too short "
                f"({len(s)} bytes); minimum is 32 bytes for adequate HMAC entropy."
            )
    return parts


def get_primary_secret() -> bytes:
    """Return the primary server secret (first entry) for write-side hashing.

    Writes never use the secondary entry — only lookups do, during rotation.
    """
    return get_server_secrets()[0]
