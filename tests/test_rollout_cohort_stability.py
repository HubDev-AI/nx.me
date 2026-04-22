"""Cohort stability tests for the makeup rollout hash-mod assignment.

Exercises app/entitlement/tier._in_rollout_cohort.
"""

from __future__ import annotations

import hashlib

from app.entitlement.tier import _in_rollout_cohort


def _expected_bucket(user_id: str) -> int:
    return (
        int(hashlib.md5(user_id.encode(), usedforsecurity=False).hexdigest(), 16) % 100
    )


class TestInRolloutCohort:
    def test_pct_0_always_false(self):
        for uid in [
            "user-1",
            "user-2",
            "user-abc",
            "00000000-0000-0000-0000-000000000001",
        ]:
            assert _in_rollout_cohort(uid, 0) is False

    def test_pct_100_always_true(self):
        for uid in [
            "user-1",
            "user-2",
            "user-abc",
            "00000000-0000-0000-0000-000000000001",
        ]:
            assert _in_rollout_cohort(uid, 100) is True

    def test_monotonically_inclusive(self):
        """A user in-cohort at pct=N stays in-cohort at pct=N+1 (never flips out)."""
        # Use a sample of known user IDs and verify monotonicity across all pct values.
        test_users = [f"user-{i:04d}" for i in range(200)]
        for uid in test_users:
            was_in = False
            for pct in range(0, 101):
                is_in = _in_rollout_cohort(uid, pct)
                if was_in:
                    assert is_in, (
                        f"{uid} was in-cohort at pct={pct - 1} but out at pct={pct} "
                        f"(bucket={_expected_bucket(uid)}) — monotonicity violation"
                    )
                was_in = is_in

    def test_bucket_boundary_exact(self):
        """A user with bucket=N is in-cohort at pct=N+1 but not at pct=N."""
        # Find a user whose bucket is exactly some known value.
        for i in range(1000):
            uid = f"synthetic-{i}"
            bucket = _expected_bucket(uid)
            assert _in_rollout_cohort(uid, bucket + 1) is True
            assert _in_rollout_cohort(uid, bucket) is False
            break  # one confirmed case is enough for the boundary assertion

    def test_approximately_uniform_distribution(self):
        """10 % PCT should put ~10 % of users in-cohort (±5 % tolerance)."""
        users = [f"user-{i:06d}" for i in range(2000)]
        in_cohort = sum(1 for u in users if _in_rollout_cohort(u, 10))
        pct = in_cohort / len(users) * 100
        assert 5.0 <= pct <= 15.0, (
            f"Expected ~10 % in cohort at pct=10, got {pct:.1f} % — hash may not be uniform"
        )

    def test_deterministic_across_calls(self):
        """Same user_id + pct always returns the same result."""
        uid = "stable-user-123"
        result = _in_rollout_cohort(uid, 42)
        for _ in range(10):
            assert _in_rollout_cohort(uid, 42) == result

    def test_pct_boundary_values(self):
        uid = "boundary-test-user"
        assert _in_rollout_cohort(uid, -1) is False
        assert _in_rollout_cohort(uid, 0) is False
        assert _in_rollout_cohort(uid, 100) is True
        assert _in_rollout_cohort(uid, 101) is True
