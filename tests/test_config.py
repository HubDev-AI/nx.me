"""Tests for application configuration.

Exercises production code in:
  - app/config/__init__.py (Settings class, settings singleton)
"""

from __future__ import annotations


from app.config import settings, Settings


class TestSettings:
    """Tests for the Settings configuration — exercises app/config/__init__.py."""

    def test_settings_is_singleton_instance(self):
        assert isinstance(settings, Settings)

    def test_free_trial_analyses_default(self):
        assert settings.FREE_TRIAL_ANALYSES == 2

    def test_identity_similarity_threshold_default(self):
        assert settings.IDENTITY_SIMILARITY_THRESHOLD == 0.80

    def test_max_concurrent_generations_default(self):
        assert settings.MAX_CONCURRENT_GENERATIONS_PER_USER == 3

    def test_registration_fingerprint_limit(self):
        assert settings.REGISTRATION_FINGERPRINT_LIMIT == 3

    def test_registration_fingerprint_window_24h(self):
        assert settings.REGISTRATION_FINGERPRINT_WINDOW_SECONDS == 86_400

    def test_registration_ip_limit(self):
        assert (
            settings.REGISTRATION_IP_LIMIT >= 1
        )  # env-configurable; just verify it's positive

    def test_registration_ip_window_1h(self):
        assert settings.REGISTRATION_IP_WINDOW_SECONDS == 3_600

    def test_username_reservation_days(self):
        assert settings.USERNAME_RESERVATION_DAYS == 180

    def test_max_upload_size(self):
        assert settings.MAX_UPLOAD_SIZE_MB == 20

    def test_signed_url_expiry(self):
        assert settings.SIGNED_URL_EXPIRY_SECONDS == 3600

    def test_generation_timeout(self):
        assert settings.GENERATION_TIMEOUT_SECONDS == 180

    def test_image_gen_cost_ceiling_above_default_model_cost(self):
        """Ceiling must sit ABOVE the per-gen model cost.

        If it sits below, the rolling 24h average crosses it on the
        first generation and every subsequent free-tier request is
        503'd — which is the bug that triggered this threshold bump.
        Uses NANO_BANANA_2 (the current default) as the floor; the
        upper bound (2x PRO) keeps the guard from going permissively
        high.
        """
        assert settings.IMAGE_GEN_COST_CEILING_USD > settings.FAL_COST_NANO_BANANA_2, (
            f"Ceiling {settings.IMAGE_GEN_COST_CEILING_USD} must be > "
            f"default model cost {settings.FAL_COST_NANO_BANANA_2}"
        )
        assert (
            settings.IMAGE_GEN_COST_CEILING_USD <= 2 * settings.FAL_COST_NANO_BANANA_PRO
        ), "Ceiling should remain a meaningful runaway guard, not effectively disabled"

    def test_credit_cost_alert_below_ceiling(self):
        """Alert must trip before the hard gate so creep is visible first."""
        assert settings.CREDIT_COST_ALERT_USD < settings.IMAGE_GEN_COST_CEILING_USD
        assert settings.CREDIT_COST_ALERT_USD >= settings.FAL_COST_NANO_BANANA_2, (
            "Alert below normal per-gen cost would fire constantly"
        )

    def test_min_age_constant_not_in_settings(self):
        """Age gate is a code constant, not a settings value (intentional)."""
        assert not hasattr(settings, "MIN_AGE_YEARS")

    def test_adapter_defaults_are_mock(self):
        """Source-code defaults for adapters are safe (mock) so a fresh
        clone without an app/.env file cannot accidentally call a paid
        external API. Per-environment `.env` files are free to opt into
        real adapters (`anthropic`, `falai`, `mediapipe`, `stripe`) —
        this test pins the fallback, not the runtime value."""
        # Inspect the class-level field defaults directly so developer
        # env overrides in app/.env don't mask regressions where someone
        # flipped the default to a real adapter.
        defaults = {
            name: field.default
            for name, field in Settings.model_fields.items()
            if name.startswith("ADAPTER__")
        }

        # Adapters that would hit external / paid APIs — must default to mock.
        assert defaults["ADAPTER__NSFW_ADAPTER"] == "mock"
        assert defaults["ADAPTER__LLM_ADAPTER"] == "mock"
        assert defaults["ADAPTER__PAYMENT_ADAPTER"] == "mock"
        assert defaults["ADAPTER__IMAGE_GENERATION_ADAPTER"] == "mock"
        assert defaults["ADAPTER__FACE_ANALYSIS_ADAPTER"] == "mock"
        assert defaults["ADAPTER__EMBEDDING_ADAPTER"] == "mock"

        # Storage default is infra, not a paid API; stays on supabase.
        assert defaults["ADAPTER__STORAGE_ADAPTER"] == "supabase"
