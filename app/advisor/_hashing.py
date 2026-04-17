"""Shared user-id hashing helper for advisor log records.

Plan 2026-04-17 review fix: raw ``user_id`` strings must never reach a
log record that could ship to an aggregator. ``payload_logger`` already
hashed them on the chat path; this module lifts the helper so other
modules (``nudge_scheduler`` in particular) can use the same contract
without pulling the full payload-logger dependency.

Invariants:

* SHA-256 truncated to :data:`USER_ID_HASH_LENGTH` hex chars — long
  enough to grep across a session (~48 bits of entropy), short enough
  that it stays out of user-identifying territory.
* ``user_id`` may be a UUID, str, or any object with a meaningful
  ``str()``. The hash is deterministic across a session so operators can
  correlate records, but is not reversible.
"""

from __future__ import annotations

import hashlib
from typing import Any

# Extracted for ops: search logs by the first 12 hex chars of the
# user_id's sha256 to correlate records without surfacing the raw id.
USER_ID_HASH_LENGTH = 12


def hash_user_id(user_id: Any) -> str:
    """Return SHA-256 hex of ``user_id`` truncated to ``USER_ID_HASH_LENGTH``."""
    return hashlib.sha256(str(user_id).encode()).hexdigest()[:USER_ID_HASH_LENGTH]
