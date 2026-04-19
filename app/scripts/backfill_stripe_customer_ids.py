"""One-shot: backfill `users.stripe_customer_id` from existing Stripe customers.

Context (plan docs/plans/2026-04-19-002-feat-payments-credits-only-engine-plan.md,
Unit 1): migration 0048 adds `users.stripe_customer_id`. Existing Stripe
customers were previously discovered lazily on every call via
`stripe.Customer.search(query='metadata["user_id"]:"..."')` — see
`app/payment/adapters/stripe_adapter.py::_get_or_create_customer` (line 183).
This script pre-seeds the column so webhook `charge.dispute.*` lookups are
O(1) instead of falling back to the search round-trip on the 5s fast path
(adversarial review P1 fix).

Design:
  * Bulk-scan Stripe via `Customer.list().auto_paging_iter()` (pages of
    100). Stripe's search DSL has no documented wildcard for metadata
    keys — matching on "any customer with a `user_id` in metadata" is
    done client-side.
  * For every customer that has `metadata.user_id` set, look up our user
    row. Skip when the row is missing, our row already has
    `stripe_customer_id` set, or another user is already mapped to that
    customer (UNIQUE enforced by the DB).
  * Idempotent by design: re-running skips already-populated rows.
  * `--dry-run` prints what would be written without touching the DB.

Run:
    python -m app.scripts.backfill_stripe_customer_ids           # apply
    python -m app.scripts.backfill_stripe_customer_ids --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Iterator

from app.config import settings
from app.db.client import get_supabase_service

logger = logging.getLogger("backfill_stripe_customer_ids")


# ---------------------------------------------------------------------------
# Constants — no magic strings (per project conventions).
# ---------------------------------------------------------------------------

_USERS_TABLE = "users"
_USER_ID_KEY = "id"
_STRIPE_CUSTOMER_ID_KEY = "stripe_customer_id"

_STRIPE_LIST_PAGE_LIMIT = 100
_METADATA_USER_ID_KEY = "user_id"

_EXIT_OK = 0
_EXIT_CONFIG = 2


# ---------------------------------------------------------------------------
# Stripe iteration.
# ---------------------------------------------------------------------------


def _iter_stripe_customers() -> Iterator[dict]:
    """Yield every Stripe customer with a `user_id` metadata key.

    `Customer.list().auto_paging_iter()` fetches pages of 100 and keeps
    memory bounded irrespective of total customer count. We filter
    client-side on `metadata.user_id` because Stripe search has no
    documented wildcard-on-metadata-key syntax — a literal
    `metadata["user_id"]:"*"` query would match only customers whose
    metadata value equals the string `*`, which is no one.

    Raises on missing Stripe credentials rather than silently producing
    an empty sequence.
    """
    if not settings.STRIPE_API_KEY:
        raise RuntimeError(
            "STRIPE_API_KEY is not set — cannot backfill stripe_customer_id"
        )

    import stripe

    stripe.api_key = settings.STRIPE_API_KEY

    page = stripe.Customer.list(limit=_STRIPE_LIST_PAGE_LIMIT)
    for customer in page.auto_paging_iter():
        metadata = customer.get("metadata") or {}
        if metadata.get(_METADATA_USER_ID_KEY):
            yield customer


# ---------------------------------------------------------------------------
# Backfill driver.
# ---------------------------------------------------------------------------


def _backfill(dry_run: bool) -> tuple[int, int, int, int]:
    """Walk Stripe customers and write `stripe_customer_id` where missing.

    Returns a (scanned, updated, skipped_already_set, skipped_no_user)
    counters tuple. `updated` is always 0 in dry-run mode.
    """
    sb = get_supabase_service()

    scanned = 0
    updated = 0
    skipped_already_set = 0
    skipped_no_user = 0

    for customer in _iter_stripe_customers():
        scanned += 1
        metadata = customer.get("metadata") or {}
        user_id = metadata.get(_METADATA_USER_ID_KEY)
        customer_id = customer.get("id")
        # `_iter_stripe_customers` already filters to customers with
        # `metadata.user_id` set, but defend against a missing Stripe
        # customer id (shouldn't happen) before querying our DB.
        if not user_id or not customer_id:
            skipped_no_user += 1
            continue

        # Fetch the user row. If missing, the Stripe customer survives
        # a deleted NXME user — nothing to do on our side.
        resp = (
            sb.table(_USERS_TABLE)
            .select(f"{_USER_ID_KEY}, {_STRIPE_CUSTOMER_ID_KEY}")
            .eq(_USER_ID_KEY, user_id)
            .maybe_single()
            .execute()
        )
        row = resp.data
        if row is None:
            skipped_no_user += 1
            logger.debug(
                "stripe customer %s maps to unknown user_id=%s (skip)",
                customer_id,
                user_id,
            )
            continue

        if row.get(_STRIPE_CUSTOMER_ID_KEY):
            skipped_already_set += 1
            continue

        if dry_run:
            logger.info(
                "[dry-run] would set users.stripe_customer_id for user=%s -> %s",
                user_id,
                customer_id,
            )
            continue

        # Guard against a concurrent live-server write (the Stripe adapter
        # lazy-populates this same column via `_write_cached_customer_id`).
        # `.is_('stripe_customer_id', 'null')` adds `WHERE stripe_customer_id
        # IS NULL` so we only fill empty rows, never stomp a live write.
        (
            sb.table(_USERS_TABLE)
            .update({_STRIPE_CUSTOMER_ID_KEY: customer_id})
            .eq(_USER_ID_KEY, user_id)
            .is_(_STRIPE_CUSTOMER_ID_KEY, "null")
            .execute()
        )
        updated += 1
        logger.info(
            "backfilled users.stripe_customer_id for user=%s -> %s",
            user_id,
            customer_id,
        )

    return scanned, updated, skipped_already_set, skipped_no_user


# ---------------------------------------------------------------------------
# Entry-point.
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill users.stripe_customer_id from Stripe customers whose "
            "metadata.user_id points at a local user row. Idempotent."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the writes that would happen without touching the DB.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Emit DEBUG-level logs for every customer scanned.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        sys.stderr.write("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.\n")
        return _EXIT_CONFIG

    try:
        scanned, updated, skipped_already, skipped_no_user = _backfill(
            dry_run=args.dry_run
        )
    except RuntimeError as exc:
        sys.stderr.write(f"{exc}\n")
        return _EXIT_CONFIG

    mode = "dry-run" if args.dry_run else "apply"
    logger.info(
        "backfill complete (%s): scanned=%d updated=%d already_set=%d no_user=%d",
        mode,
        scanned,
        updated,
        skipped_already,
        skipped_no_user,
    )
    return _EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
