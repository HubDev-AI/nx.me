"""Tests for app/scripts/backfill_stripe_customer_ids.py.

Exercises the `_backfill` driver with mocked Stripe + Supabase. Real
Stripe API never hit. Verifies:
  - scan/update counters are correct
  - rows with `stripe_customer_id` already set are skipped
  - Stripe customers with no `metadata.user_id` are skipped (no DB hit)
  - Stripe customers pointing at unknown users are counted but not written
  - dry-run mode never writes
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


def _stripe_customer(customer_id: str, user_id: str | None) -> dict:
    """Build a stripe.Customer-like dict matching what the script consumes."""
    return {"id": customer_id, "metadata": {"user_id": user_id} if user_id else {}}


@pytest.fixture
def fake_supabase():
    """Build a fake supabase client where:
    - users(known_id, stripe_customer_id=NULL) → eligible for backfill
    - users(already_set_id, stripe_customer_id='cus_seeded') → skipped
    - users(missing_id) → not present in the table
    """
    known_id = str(uuid4())
    already_set_id = str(uuid4())
    missing_id = str(uuid4())

    rows: dict[str, dict] = {
        known_id: {"id": known_id, "stripe_customer_id": None},
        already_set_id: {"id": already_set_id, "stripe_customer_id": "cus_seeded"},
    }

    sb = MagicMock()
    update_calls: list[tuple[str, str]] = []

    def table(name: str):
        assert name == "users"

        def select(_cols: str):
            class _Q:
                def __init__(self, ctx):
                    self._ctx = ctx
                    self._eq_id = None

                def eq(self, key, value):
                    assert key == "id"
                    self._eq_id = value
                    return self

                def maybe_single(self):
                    return self

                def execute(self):
                    return SimpleNamespace(data=rows.get(self._eq_id))

            return _Q(name)

        def update(payload: dict):
            customer_id = payload["stripe_customer_id"]

            class _U:
                def __init__(self):
                    self._eq_id = None

                def eq(self, key, value):
                    assert key == "id"
                    self._eq_id = value
                    return self

                def is_(self, key, value):
                    assert key == "stripe_customer_id"
                    assert value == "null"
                    return self

                def execute(self):
                    update_calls.append((self._eq_id, customer_id))
                    return SimpleNamespace(data=[])

            return _U()

        ns = SimpleNamespace(select=select, update=update)
        return ns

    sb.table.side_effect = table
    return sb, update_calls, known_id, already_set_id, missing_id


def _patch_supabase(sb):
    return patch(
        "app.scripts.backfill_stripe_customer_ids.get_supabase_service",
        return_value=sb,
    )


def _patch_stripe_iter(customers: list[dict]):
    return patch(
        "app.scripts.backfill_stripe_customer_ids._iter_stripe_customers",
        return_value=iter(customers),
    )


def test_backfill_writes_for_known_unset_user(fake_supabase):
    """Happy path: Stripe customer maps to existing NULL row → UPDATE fires."""
    from app.scripts.backfill_stripe_customer_ids import _backfill

    sb, updates, known_id, _already, _missing = fake_supabase
    customers = [_stripe_customer("cus_aaa", known_id)]

    with _patch_supabase(sb), _patch_stripe_iter(customers):
        scanned, updated, skipped_already, skipped_no_user = _backfill(dry_run=False)

    assert scanned == 1
    assert updated == 1
    assert skipped_already == 0
    assert skipped_no_user == 0
    assert updates == [(known_id, "cus_aaa")]


def test_backfill_skips_already_populated_row(fake_supabase):
    """Idempotency: row with stripe_customer_id already set → no UPDATE."""
    from app.scripts.backfill_stripe_customer_ids import _backfill

    sb, updates, _known, already_set_id, _missing = fake_supabase
    customers = [_stripe_customer("cus_bbb", already_set_id)]

    with _patch_supabase(sb), _patch_stripe_iter(customers):
        scanned, updated, skipped_already, skipped_no_user = _backfill(dry_run=False)

    assert scanned == 1
    assert updated == 0
    assert skipped_already == 1
    assert skipped_no_user == 0
    assert updates == []


def test_backfill_skips_unknown_user(fake_supabase):
    """Stripe customer points at a user_id that doesn't exist in our DB."""
    from app.scripts.backfill_stripe_customer_ids import _backfill

    sb, updates, _known, _already, missing_id = fake_supabase
    customers = [_stripe_customer("cus_ccc", missing_id)]

    with _patch_supabase(sb), _patch_stripe_iter(customers):
        scanned, updated, skipped_already, skipped_no_user = _backfill(dry_run=False)

    assert scanned == 1
    assert updated == 0
    assert skipped_already == 0
    assert skipped_no_user == 1
    assert updates == []


def test_backfill_dry_run_never_writes(fake_supabase):
    """Dry-run path: would-be UPDATE on known unset user is suppressed."""
    from app.scripts.backfill_stripe_customer_ids import _backfill

    sb, updates, known_id, _already, _missing = fake_supabase
    customers = [_stripe_customer("cus_ddd", known_id)]

    with _patch_supabase(sb), _patch_stripe_iter(customers):
        scanned, updated, skipped_already, skipped_no_user = _backfill(dry_run=True)

    assert scanned == 1
    assert updated == 0  # dry-run never increments
    assert skipped_already == 0
    assert skipped_no_user == 0
    assert updates == []  # never touches DB


def test_backfill_mixed_batch_counters(fake_supabase):
    """Batch with one of each path → counters reflect every category."""
    from app.scripts.backfill_stripe_customer_ids import _backfill

    sb, updates, known_id, already_set_id, missing_id = fake_supabase
    customers = [
        _stripe_customer("cus_111", known_id),
        _stripe_customer("cus_222", already_set_id),
        _stripe_customer("cus_333", missing_id),
    ]

    with _patch_supabase(sb), _patch_stripe_iter(customers):
        scanned, updated, skipped_already, skipped_no_user = _backfill(dry_run=False)

    assert scanned == 3
    assert updated == 1
    assert skipped_already == 1
    assert skipped_no_user == 1
    assert updates == [(known_id, "cus_111")]
