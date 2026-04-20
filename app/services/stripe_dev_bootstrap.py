"""One-shot: bootstrap Stripe Products + Prices for every paid plan_versions row.

Context (plan docs/plans/2026-04-19-002-feat-payments-credits-only-engine-plan.md,
Unit 13): after `make migrate` seeds `plan_versions` the operator runs
`make stripe-bootstrap` once per test-mode Stripe project to mint the
matching Products and Prices. Results are written back to
`plan_versions.stripe_price_id`.

Design:
  * Iterates all ``plan_versions`` rows where ``price_usd_cents > 0``
    (Free-default has price 0 — Stripe has no free-product concept that
    fits the internal divisor-bundle model).
  * For each row: if ``stripe_price_id`` is already populated → skip
    (log "skipped: already_seeded").  Pass ``--force`` to recreate.
  * Creates Product then recurring Price, writes the Price ID back via
    a conditional UPDATE (IS NULL guard, same pattern as
    backfill_stripe_customer_ids).
  * Idempotent by design: re-running without ``--force`` skips rows
    that already have a price.
  * ``--dry-run`` shows what would happen without touching Stripe or DB.

Run:
    python -m app.services.stripe_dev_bootstrap           # apply
    python -m app.services.stripe_dev_bootstrap --dry-run
    python -m app.services.stripe_dev_bootstrap --force   # recreate even if seeded
"""

from __future__ import annotations

import argparse
import logging
import sys

from app.config import settings
from app.db.client import get_supabase_service

logger = logging.getLogger("stripe_dev_bootstrap")

# ---------------------------------------------------------------------------
# Constants — no magic strings (per project conventions).
# ---------------------------------------------------------------------------

_PLAN_VERSIONS_TABLE = "plan_versions"
_PV_ID_KEY = "id"
_PV_VERSION_NUM_KEY = "version_num"
_PV_PRICE_CENTS_KEY = "price_usd_cents"
_PV_STRIPE_PRICE_ID_KEY = "stripe_price_id"

# Stripe currency for minted Products/Prices (plan_versions has no currency
# column; a single currency is sufficient pre-launch).
_STRIPE_CURRENCY = "usd"

# Stripe Product/Price metadata key used to recover existing objects.
_STRIPE_METADATA_VERSION_NUM = "nxme_version_num"

# Test cards for developer reference (Stripe test-mode numbers).
_TEST_CARD_SUCCESS = "4242 4242 4242 4242"  # Basic success
_TEST_CARD_INSUFFICIENT_FUNDS = "4000 0000 0000 9995"  # Decline: insufficient funds
_TEST_CARD_3DS = "4000 0025 0000 3155"  # 3D Secure required

_EXIT_OK = 0
_EXIT_CONFIG = 2
_EXIT_STRIPE_ERROR = 3


# ---------------------------------------------------------------------------
# Stripe helpers.
# ---------------------------------------------------------------------------


def _require_stripe():
    """Import and configure stripe; raise RuntimeError if key is missing."""
    if not settings.STRIPE_API_KEY:
        raise RuntimeError(
            "STRIPE_API_KEY is not set — cannot bootstrap Stripe objects. "
            "Set it in app/.env and re-run."
        )
    import stripe

    stripe.api_key = settings.STRIPE_API_KEY
    return stripe


def _create_product_and_price(
    stripe,
    *,
    product_name: str,
    version_num: str,
    price_cents: int,
    is_recurring: bool,
    dry_run: bool,
) -> str | None:
    """Create a Stripe Product + Price.  Returns the Price ID, or None on dry-run.

    ``is_recurring=True`` → monthly subscription (interval='month').
    ``is_recurring=False`` → one-time charge.

    Metadata tag ``nxme_version_num`` is set on both Product and Price so
    operators can identify objects in the Stripe dashboard.
    """
    if dry_run:
        price_dollars = price_cents / 100
        recur_label = "recurring/month" if is_recurring else "one-time"
        logger.info(
            "[dry-run] would create Product '%s' + Price $%.2f %s (version_num=%s)",
            product_name,
            price_dollars,
            recur_label,
            version_num,
        )
        return None

    product = stripe.Product.create(
        name=product_name,
        metadata={_STRIPE_METADATA_VERSION_NUM: version_num},
    )
    logger.debug("created Product id=%s name=%s", product["id"], product_name)

    price_kwargs: dict = {
        "product": product["id"],
        "unit_amount": price_cents,
        "currency": _STRIPE_CURRENCY,
        "metadata": {_STRIPE_METADATA_VERSION_NUM: version_num},
    }
    if is_recurring:
        price_kwargs["recurring"] = {"interval": "month"}

    price = stripe.Price.create(**price_kwargs)
    logger.debug("created Price id=%s unit_amount=%d", price["id"], price_cents)
    return price["id"]


# ---------------------------------------------------------------------------
# Bootstrap driver.
# ---------------------------------------------------------------------------


def _bootstrap(dry_run: bool, force: bool) -> tuple[int, int, int]:
    """Seed Stripe Products + Prices for all paid plan_versions rows.

    Returns (processed, seeded, skipped) counters.
    ``seeded`` is always 0 in dry-run mode.
    """
    stripe = _require_stripe()
    sb = get_supabase_service()

    resp = (
        sb.table(_PLAN_VERSIONS_TABLE)
        .select(
            f"{_PV_ID_KEY}, {_PV_VERSION_NUM_KEY}, {_PV_PRICE_CENTS_KEY}, {_PV_STRIPE_PRICE_ID_KEY}"
        )
        .execute()
    )
    rows = resp.data or []

    processed = 0
    seeded = 0
    skipped = 0

    for row in rows:
        version_num: str = row[_PV_VERSION_NUM_KEY]
        price_cents: int = row[_PV_PRICE_CENTS_KEY]
        existing_price_id: str | None = row.get(_PV_STRIPE_PRICE_ID_KEY)

        # Free-default row has price 0; no Stripe object needed.
        if price_cents == 0:
            logger.debug("skip free-tier row version_num=%s (price=0)", version_num)
            continue

        processed += 1

        if existing_price_id and not force:
            skipped += 1
            logger.info(
                "skipped: already_seeded version_num=%s stripe_price_id=%s",
                version_num,
                existing_price_id,
            )
            continue

        price_id = _create_product_and_price(
            stripe,
            product_name=f"NXME {version_num}",
            version_num=version_num,
            price_cents=price_cents,
            is_recurring=True,
            dry_run=dry_run,
        )

        if dry_run:
            continue

        # Write back to plan_versions (IS NULL guard unless --force).
        update_query = (
            sb.table(_PLAN_VERSIONS_TABLE)
            .update({_PV_STRIPE_PRICE_ID_KEY: price_id})
            .eq(_PV_ID_KEY, row[_PV_ID_KEY])
        )
        if not force:
            update_query = update_query.is_(_PV_STRIPE_PRICE_ID_KEY, "null")
        update_query.execute()

        seeded += 1
        logger.info(
            "seeded plan_versions version_num=%s stripe_price_id=%s",
            version_num,
            price_id,
        )

    return processed, seeded, skipped


# ---------------------------------------------------------------------------
# Entry-point.
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Bootstrap Stripe Products + Prices for paid plan_versions rows. "
            "Idempotent — skips rows whose stripe_price_id is already set. "
            "Pass --force to recreate."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without touching Stripe or the DB.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recreate Stripe objects even when stripe_price_id is already set.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Emit DEBUG-level logs.",
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
        processed, seeded, skipped = _bootstrap(dry_run=args.dry_run, force=args.force)
    except RuntimeError as exc:
        sys.stderr.write(f"{exc}\n")
        return _EXIT_CONFIG
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"Stripe error: {exc}\n")
        return _EXIT_STRIPE_ERROR

    mode = "dry-run" if args.dry_run else "apply"
    logger.info(
        "bootstrap complete (%s): processed=%d seeded=%d skipped=%d",
        mode,
        processed,
        seeded,
        skipped,
    )

    print("\nStripe test cards:")
    print(f"  {_TEST_CARD_SUCCESS}           — success")
    print(f"  {_TEST_CARD_INSUFFICIENT_FUNDS}           — insufficient funds")
    print(f"  {_TEST_CARD_3DS}           — 3D Secure required")

    return _EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
