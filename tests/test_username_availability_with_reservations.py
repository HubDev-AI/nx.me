"""Tests for NFKC + ASCII-fold username normalization and reservation-aware availability.

Covers:
- ``normalize_username`` — Unicode homographs collapse to ASCII lowercase.
- ``UserRepository.check_username_availability`` — new shape
  ``{available, reason?}`` that checks the ``users`` table first, then the
  ``username_reservations`` table.
- ``UserRepository.check_username_available_ci`` — thin alias of
  ``check_username_availability`` (post-normalization they're identical).
- ``UserRepository.insert_username_reservation`` — normalizes before
  UPSERT so the DB CHECK ``(username = lower(username))`` constraint
  always accepts the row.

Mock pattern follows ``tests/test_upload_repo_touch_access.py`` — a
MagicMock Supabase client with a ``table(name)`` router returning
different chains for ``users`` vs ``username_reservations``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.utils.username import normalize_username
from app.repositories.user_repo import UserRepository


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _build_sb_serving_tables(
    users_rows: list[dict] | None = None,
    reservations_rows: list[dict] | None = None,
) -> MagicMock:
    """Build a MagicMock Supabase routing ``table("users")`` vs ``table("username_reservations")``.

    Both tables terminate at ``.execute()`` with ``MagicMock(data=<rows>)``.
    The chain methods (``select``, ``ilike``, ``eq``, ``gt``) return self so
    repo code that builds up any filter combination still works.
    """
    sb = MagicMock()

    users_chain = MagicMock()
    users_chain.select.return_value = users_chain
    users_chain.ilike.return_value = users_chain
    users_chain.eq.return_value = users_chain
    users_chain.gt.return_value = users_chain
    users_chain.execute.return_value = MagicMock(data=users_rows or [])

    reservations_chain = MagicMock()
    reservations_chain.select.return_value = reservations_chain
    reservations_chain.ilike.return_value = reservations_chain
    reservations_chain.eq.return_value = reservations_chain
    reservations_chain.gt.return_value = reservations_chain
    reservations_chain.execute.return_value = MagicMock(data=reservations_rows or [])

    def route(name: str) -> MagicMock:
        if name == "users":
            return users_chain
        if name == "username_reservations":
            return reservations_chain
        raise AssertionError(f"Unexpected table: {name}")

    sb.table.side_effect = route
    return sb


def _build_sb_capturing_reservation_upsert() -> tuple[MagicMock, list[dict]]:
    """Supabase mock that captures payloads passed to
    ``table('username_reservations').upsert(<payload>)``.

    Returns the mock client and the captured-payloads list.
    """
    sb = MagicMock()
    captured: list[dict] = []

    reservations_chain = MagicMock()

    def fake_upsert(payload: dict, on_conflict: str = "username") -> MagicMock:
        captured.append(payload)
        terminator = MagicMock()
        terminator.execute.return_value = MagicMock(data=[payload])
        return terminator

    reservations_chain.upsert.side_effect = fake_upsert

    def route(name: str) -> MagicMock:
        if name == "username_reservations":
            return reservations_chain
        raise AssertionError(f"Unexpected table: {name}")

    sb.table.side_effect = route
    return sb, captured


# ----------------------------------------------------------------------
# normalize_username
# ----------------------------------------------------------------------


class TestNormalizeUsername:
    def test_accented_latin_folds_to_ascii(self):
        assert normalize_username("Álicé") == "alice"

    def test_fullwidth_ascii_folds_to_ascii(self):
        # U+FF41 (fullwidth 'a') + lice
        assert normalize_username("\uff41lice") == "alice"

    def test_cyrillic_a_folds_to_latin_a(self):
        # U+0430 Cyrillic 'а' looks identical to ASCII 'a'
        assert normalize_username("\u0430") == "a"

    def test_uppercase_folds_to_lowercase(self):
        assert normalize_username("ALICE") == "alice"

    def test_combining_diacritic_folds(self):
        assert normalize_username("café") == "cafe"


# ----------------------------------------------------------------------
# check_username_availability
# ----------------------------------------------------------------------


class TestCheckUsernameAvailability:
    def test_taken_by_active_user(self):
        sb = _build_sb_serving_tables(
            users_rows=[{"id": "u-1", "username": "alice"}],
            reservations_rows=[],
        )
        repo = UserRepository(sb)

        result = repo.check_username_availability("alice")

        assert result == {"available": False, "reason": "taken"}

    def test_active_reservation_blocks(self):
        future = (datetime.now(tz=timezone.utc) + timedelta(days=30)).isoformat()
        sb = _build_sb_serving_tables(
            users_rows=[],
            reservations_rows=[
                {"username": "alice", "reserved_until": future},
            ],
        )
        repo = UserRepository(sb)

        result = repo.check_username_availability("alice")

        assert result == {"available": False, "reason": "reserved"}

    def test_expired_reservation_treated_as_available(self):
        # Simulated by the DB-side filter returning zero rows (gt("reserved_until", now)).
        sb = _build_sb_serving_tables(users_rows=[], reservations_rows=[])
        repo = UserRepository(sb)

        result = repo.check_username_availability("alice")

        assert result == {"available": True}

    def test_not_in_users_not_in_reservations(self):
        sb = _build_sb_serving_tables(users_rows=[], reservations_rows=[])
        repo = UserRepository(sb)

        assert repo.check_username_availability("brandnew") == {"available": True}

    def test_exclude_user_id_skips_self_owned_row(self):
        sb = _build_sb_serving_tables(
            users_rows=[{"id": "u-1", "username": "alice"}],
            reservations_rows=[],
        )
        repo = UserRepository(sb)

        result = repo.check_username_availability("alice", exclude_user_id="u-1")

        assert result == {"available": True}

    def test_homograph_normalizes_and_hits_reservation(self):
        # 'Álicé' must normalize to 'alice' and find an existing reservation.
        future = (datetime.now(tz=timezone.utc) + timedelta(days=30)).isoformat()
        sb = _build_sb_serving_tables(
            users_rows=[],
            reservations_rows=[
                {"username": "alice", "reserved_until": future},
            ],
        )
        repo = UserRepository(sb)

        result = repo.check_username_availability("Álicé")

        assert result == {"available": False, "reason": "reserved"}


# ----------------------------------------------------------------------
# insert_username_reservation
# ----------------------------------------------------------------------


class TestInsertUsernameReservation:
    def test_normalizes_payload_before_upsert(self):
        sb, captured = _build_sb_capturing_reservation_upsert()
        repo = UserRepository(sb)
        reserved_until = datetime(2026, 10, 18, tzinfo=timezone.utc)

        repo.insert_username_reservation("Álicé", reserved_until)

        assert len(captured) == 1
        payload = captured[0]
        assert payload == {
            "username": "alice",
            "reserved_until": reserved_until.isoformat(),
        }


# ----------------------------------------------------------------------
# check_username_available_ci alias
# ----------------------------------------------------------------------


class TestCheckUsernameAvailableCIAlias:
    def test_is_same_callable_as_check_username_availability(self):
        # Post-normalization, the CI method is redundant — repo exposes it
        # as a thin alias so existing call sites (mobile /username-availability)
        # keep working without a churn.
        assert (
            UserRepository.check_username_available_ci
            is UserRepository.check_username_availability
        )
