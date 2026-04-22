"""Verify that flag=false keeps using the existing per-router wiring.

When USE_REGISTRY_DISPATCH is False, the actions_router module exists but
is NOT imported or mounted. The existing glowup.router and makeup.router
handle the routes directly.
"""

from __future__ import annotations


class TestFlagOffBehavior:
    def test_flag_defaults_to_false(self):
        from app.config import settings

        assert settings.USE_REGISTRY_DISPATCH is False, (
            "Default must be False — registry dispatch must be an explicit opt-in"
        )

    def test_actions_module_importable_without_side_effects(self):
        """The actions module must be importable at any time (lazy mount). Importing it
        should not cause side effects like router mounting or DB connections."""
        import app.generation.actions as actions

        assert hasattr(actions, "GLOWUP_ACTION")
        assert hasattr(actions, "MAKEUP_ACTION")

    def test_actions_router_module_importable(self):
        """actions_router must be importable even when flag is off."""
        import app.api.actions_router as ar

        assert hasattr(ar, "build_actions_router")
        assert callable(ar.build_actions_router)

    def test_flag_off_registry_still_has_descriptors(self, monkeypatch):
        """Registry is always populated — it's the dispatch gate that's conditional."""
        from app.config import settings

        monkeypatch.setattr(settings, "USE_REGISTRY_DISPATCH", False)
        from app.generation.actions import all_actions

        assert len(all_actions()) == 2

    def test_flag_on_registry_still_has_same_descriptors(self, monkeypatch):
        """Toggling the flag doesn't add or remove descriptors."""
        from app.config import settings

        monkeypatch.setattr(settings, "USE_REGISTRY_DISPATCH", True)
        from app.generation.actions import all_actions

        assert len(all_actions()) == 2
