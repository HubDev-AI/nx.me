"""Tests for ``app.entitlement.fingerprint`` + ``SignupGrantRepository``.

Covers the Unit 6 scenarios from the payments plan:

* Deterministic hash is actually deterministic (same inputs → same bytes).
* Protected hash varies with the salt.
* ``generate_salt`` returns 32 bytes, isn't the zero vector, and differs
  across calls.
* ``get_server_secrets`` parses single-entry and comma-separated envs, and
  raises ``ValueError`` (no silent fallback) when the env is blank.
* ``SignupGrantRepository.exists_for_install_uuid`` tries the primary
  secret first and falls back to the secondary during a rotation.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.config import settings
from app.entitlement.fingerprint import (
    SALT_BYTES,
    compute_deterministic_hash,
    compute_protected_hash,
    generate_salt,
    get_primary_secret,
    get_server_secrets,
)
from app.repositories.signup_grant_repo import SignupGrantRepository

INSTALL_UUID = "11111111-2222-3333-4444-555555555555"


# ---------------------------------------------------------------------------
# Hash helpers
# ---------------------------------------------------------------------------


class TestComputeDeterministicHash:
    def test_same_inputs_produce_same_output(self):
        secret = b"super-secret"
        a = compute_deterministic_hash(INSTALL_UUID, secret)
        b = compute_deterministic_hash(INSTALL_UUID, secret)
        assert a == b
        assert isinstance(a, bytes)
        # SHA-256 → 32 bytes.
        assert len(a) == 32

    def test_different_secrets_produce_different_hashes(self):
        a = compute_deterministic_hash(INSTALL_UUID, b"primary")
        b = compute_deterministic_hash(INSTALL_UUID, b"secondary")
        assert a != b

    def test_different_uuids_produce_different_hashes(self):
        secret = b"same-secret"
        a = compute_deterministic_hash(INSTALL_UUID, secret)
        b = compute_deterministic_hash("99999999-0000-0000-0000-000000000000", secret)
        assert a != b


class TestComputeProtectedHash:
    def test_same_salt_and_uuid_produce_same_hash(self):
        salt = b"\x00" * SALT_BYTES
        a = compute_protected_hash(INSTALL_UUID, salt)
        b = compute_protected_hash(INSTALL_UUID, salt)
        assert a == b
        assert len(a) == 32

    def test_different_salts_produce_different_hashes(self):
        salt_a = b"\x01" * SALT_BYTES
        salt_b = b"\x02" * SALT_BYTES
        assert compute_protected_hash(INSTALL_UUID, salt_a) != compute_protected_hash(
            INSTALL_UUID, salt_b
        )


class TestGenerateSalt:
    def test_returns_32_bytes(self):
        salt = generate_salt()
        assert len(salt) == SALT_BYTES
        assert isinstance(salt, bytes)

    def test_not_all_zeros(self):
        # ``secrets.token_bytes`` can theoretically return all-zero bytes;
        # the probability at 32 bytes is 2**-256. Still, sampling a few
        # times keeps the test honest.
        for _ in range(4):
            assert generate_salt() != b"\x00" * SALT_BYTES

    def test_differs_across_calls(self):
        a = generate_salt()
        b = generate_salt()
        assert a != b


# ---------------------------------------------------------------------------
# get_server_secrets — rotation-aware parsing
# ---------------------------------------------------------------------------


class TestGetServerSecrets:
    def test_single_secret_parses_as_single_element_list(self, monkeypatch):
        monkeypatch.setattr(
            settings, "SIGNUP_FINGERPRINT_SERVER_SECRET", "primary-only-secret"
        )
        assert get_server_secrets() == [b"primary-only-secret"]
        assert get_primary_secret() == b"primary-only-secret"

    def test_primary_then_secondary_parses_in_order(self, monkeypatch):
        monkeypatch.setattr(
            settings,
            "SIGNUP_FINGERPRINT_SERVER_SECRET",
            "primary-secret,secondary-secret",
        )
        secrets = get_server_secrets()
        assert secrets == [b"primary-secret", b"secondary-secret"]
        # Writes always use primary; secondary is lookup-only.
        assert get_primary_secret() == b"primary-secret"

    def test_whitespace_around_entries_is_stripped(self, monkeypatch):
        monkeypatch.setattr(
            settings,
            "SIGNUP_FINGERPRINT_SERVER_SECRET",
            "  primary  ,  secondary  ",
        )
        assert get_server_secrets() == [b"primary", b"secondary"]

    def test_empty_env_raises_valueerror(self, monkeypatch):
        # feedback_no_env_fallbacks — missing secret MUST fail loudly rather
        # than silently disabling abuse prevention.
        monkeypatch.setattr(settings, "SIGNUP_FINGERPRINT_SERVER_SECRET", "")
        with pytest.raises(ValueError, match="SIGNUP_FINGERPRINT_SERVER_SECRET"):
            get_server_secrets()

    def test_only_commas_and_whitespace_raises_valueerror(self, monkeypatch):
        monkeypatch.setattr(settings, "SIGNUP_FINGERPRINT_SERVER_SECRET", "  ,  ,  ")
        with pytest.raises(ValueError, match="SIGNUP_FINGERPRINT_SERVER_SECRET"):
            get_server_secrets()


# ---------------------------------------------------------------------------
# SignupGrantRepository rotation semantics
# ---------------------------------------------------------------------------
#
# ``exists_for_install_uuid`` MUST probe primary first and secondary only if
# primary misses. We verify that by driving a branching Supabase mock keyed
# off the ``.eq("deterministic_hash", ...)`` value.


def _build_dispatch_supabase(known_hashes: set[bytes]) -> MagicMock:
    """Return a mock whose ``.exists`` returns True only for the given hashes."""
    sb = MagicMock()
    probes: list[bytes] = []

    def _execute(chain_state):
        hashed = chain_state.get("deterministic_hash")
        probes.append(hashed)
        data = [{"deterministic_hash": hashed}] if hashed in known_hashes else []
        return MagicMock(data=data)

    def _table(name):
        assert name == "signup_grants_issued"
        chain = MagicMock()
        state: dict = {}

        def _select(*_, **__):
            return chain

        def _eq(col, val):
            state[col] = val
            return chain

        def _limit(_):
            return chain

        def _exec():
            return _execute(state)

        chain.select.side_effect = _select
        chain.eq.side_effect = _eq
        chain.limit.side_effect = _limit
        chain.execute.side_effect = _exec
        return chain

    sb.table.side_effect = _table
    sb.probes = probes  # expose for assertions
    return sb


class TestExistsRotationAware:
    def test_primary_hit_skips_secondary_probe(self, monkeypatch):
        monkeypatch.setattr(
            settings,
            "SIGNUP_FINGERPRINT_SERVER_SECRET",
            "primary-secret,secondary-secret",
        )
        primary_hash = compute_deterministic_hash(INSTALL_UUID, b"primary-secret")
        secondary_hash = compute_deterministic_hash(INSTALL_UUID, b"secondary-secret")

        sb = _build_dispatch_supabase({primary_hash})
        repo = SignupGrantRepository(sb)

        assert repo.exists(INSTALL_UUID) is True
        # Only the primary should have been probed — short-circuit on hit.
        assert sb.probes == [primary_hash]
        assert secondary_hash not in sb.probes

    def test_primary_miss_falls_back_to_secondary(self, monkeypatch):
        monkeypatch.setattr(
            settings,
            "SIGNUP_FINGERPRINT_SERVER_SECRET",
            "primary-secret,secondary-secret",
        )
        primary_hash = compute_deterministic_hash(INSTALL_UUID, b"primary-secret")
        secondary_hash = compute_deterministic_hash(INSTALL_UUID, b"secondary-secret")

        # Row was issued under the OLD primary (now secondary) before rotation;
        # the repo must still find it, otherwise abuse prevention is broken.
        sb = _build_dispatch_supabase({secondary_hash})
        repo = SignupGrantRepository(sb)

        assert repo.exists(INSTALL_UUID) is True
        # Both hashes were probed, in order.
        assert sb.probes == [primary_hash, secondary_hash]

    def test_unknown_uuid_returns_false(self, monkeypatch):
        monkeypatch.setattr(
            settings,
            "SIGNUP_FINGERPRINT_SERVER_SECRET",
            "primary-secret,secondary-secret",
        )
        sb = _build_dispatch_supabase(set())  # nothing matches
        repo = SignupGrantRepository(sb)

        assert repo.exists(INSTALL_UUID) is False
        # Both secrets probed before giving up.
        assert len(sb.probes) == 2

    def test_single_secret_config_probes_once(self, monkeypatch):
        monkeypatch.setattr(settings, "SIGNUP_FINGERPRINT_SERVER_SECRET", "only-secret")
        sb = _build_dispatch_supabase(set())
        repo = SignupGrantRepository(sb)

        assert repo.exists(INSTALL_UUID) is False
        assert len(sb.probes) == 1
