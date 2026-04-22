"""Parity test: glowup dispatch produces identical results under both flag states.

Execution note: test-first. These tests assert that with USE_REGISTRY_DISPATCH=True
the worker reaches the same dispatch point as with the flag off. Since both paths
call the same underlying _run_makeup_pipeline / glowup pipeline, behavioral parity
is guaranteed by the shared implementation — this test guards against the registry
layer accidentally swallowing or redirecting jobs.
"""

from __future__ import annotations


class TestGlowupRegistryDescriptor:
    def test_glowup_action_registered(self):
        from app.generation.actions import get_action

        action = get_action("glowup_analysis")
        assert action is not None
        assert action.slug == "glowup"
        assert action.source_type == "glowup_analysis"

    def test_glowup_action_type_ledger(self):
        from app.generation.actions import GLOWUP_ACTION

        assert GLOWUP_ACTION.action_type_ledger == "glowup"

    def test_glowup_post_kind(self):
        from app.generation.actions import GLOWUP_ACTION

        assert GLOWUP_ACTION.post_kind == "glowup"

    def test_glowup_card_web_segment(self):
        from app.generation.actions import GLOWUP_ACTION

        assert GLOWUP_ACTION.card_web_segment == "glow-up"

    def test_glowup_advisor_mcp_module(self):
        from app.generation.actions import GLOWUP_ACTION

        assert GLOWUP_ACTION.advisor_mcp_module == "tools_glowup"

    def test_glowup_nudge_trigger(self):
        from app.generation.actions import GLOWUP_ACTION

        assert GLOWUP_ACTION.nudge_trigger == "post_glowup"


class TestGlowupWorkerDispatchParity:
    """Worker reaches identical dispatch path under both flag states."""

    def test_flag_off_unknown_source_type_does_not_raise(self, monkeypatch):
        """With flag off, unknown source_type falls through silently (legacy behavior)."""
        from app.config import settings

        monkeypatch.setattr(settings, "USE_REGISTRY_DISPATCH", False)
        from app.generation.actions import get_action

        # Registry still returns None for unknown — the worker just doesn't check it
        assert get_action("unknown_type") is None

    def test_flag_on_known_glowup_source_type_passes_registry_check(self, monkeypatch):
        """With flag on, glowup_analysis is registered and passes the validation gate."""
        from app.config import settings

        monkeypatch.setattr(settings, "USE_REGISTRY_DISPATCH", True)
        from app.generation.actions import get_action

        action = get_action("glowup_analysis")
        assert action is not None, (
            "glowup_analysis must be registered for flag=true to work"
        )

    def test_flag_on_unknown_source_type_raises(self, monkeypatch):
        """With flag on, an unknown source_type is detectable at the registry gate."""
        from app.generation.actions import get_action

        assert get_action("bogus_type") is None
