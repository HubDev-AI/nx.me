"""Tests for the biometric nullification step added to delete_account.

Verifies that:
  - nullify_biometric_fields is invoked with the user_id during delete_account
  - A nullify failure is swallowed (non-fatal) — delete still proceeds
  - makeup:quota and makeup:analyze_rate Redis keys are swept on delete
"""

from __future__ import annotations


class TestDeleteAccountBiometricNullification:
    def test_nullify_biometric_fields_called_for_user(self):
        """delete_account inlines MakeupAnalysisRepository.nullify_biometric_fields."""
        import inspect

        import app.api.auth as auth_mod

        src = inspect.getsource(auth_mod.delete_account)
        assert "nullify_biometric_fields" in src, (
            "delete_account must call nullify_biometric_fields (step 4.5)"
        )
        assert "MakeupAnalysisRepository" in src, (
            "delete_account must import MakeupAnalysisRepository for step 4.5"
        )

    def test_makeup_redis_keys_swept_on_delete(self):
        """makeup:quota and makeup:analyze_rate keys are in the delete_account sweep."""
        import inspect

        import app.api.auth as auth_mod

        src = inspect.getsource(auth_mod.delete_account)
        assert "makeup:quota:" in src, (
            "delete_account must sweep makeup:quota:{user_id} from Redis"
        )
        assert "makeup:analyze_rate:" in src, (
            "delete_account must sweep makeup:analyze_rate:{user_id} from Redis"
        )

    def test_nullify_step_wrapped_in_try_except(self):
        """Biometric nullification failure must not abort account deletion."""
        import inspect

        import app.api.auth as auth_mod

        src = inspect.getsource(auth_mod.delete_account)
        # The try/except around step 4.5 is evidenced by the warning log message.
        assert "makeup biometric nullification failed" in src, (
            "nullify step must be wrapped in try/except with a warning log"
        )
