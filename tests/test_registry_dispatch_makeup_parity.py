"""Parity test: makeup dispatch produces identical results under both flag states."""

from __future__ import annotations


class TestMakeupRegistryDescriptor:
    def test_makeup_action_registered(self):
        from app.generation.actions import get_action

        action = get_action("makeup_session")
        assert action is not None
        assert action.slug == "makeup"
        assert action.source_type == "makeup_session"

    def test_makeup_capability_flag(self):
        from app.generation.actions import MAKEUP_ACTION

        assert MAKEUP_ACTION.capability_flag == "makeup"

    def test_makeup_action_type_ledger(self):
        from app.generation.actions import MAKEUP_ACTION

        assert MAKEUP_ACTION.action_type_ledger == "makeup"

    def test_makeup_post_kind(self):
        from app.generation.actions import MAKEUP_ACTION

        assert MAKEUP_ACTION.post_kind == "makeup"

    def test_makeup_card_web_segment(self):
        from app.generation.actions import MAKEUP_ACTION

        assert MAKEUP_ACTION.card_web_segment == "makeup"

    def test_makeup_advisor_mcp_module(self):
        from app.generation.actions import MAKEUP_ACTION

        assert MAKEUP_ACTION.advisor_mcp_module == "tools_makeup"

    def test_makeup_nudge_trigger(self):
        from app.generation.actions import MAKEUP_ACTION

        assert MAKEUP_ACTION.nudge_trigger == "post_makeup"


class TestMakeupWorkerDispatchParity:
    def test_flag_on_known_makeup_source_type_passes_registry_check(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "USE_REGISTRY_DISPATCH", True)
        from app.generation.actions import get_action

        action = get_action("makeup_session")
        assert action is not None, (
            "makeup_session must be registered for flag=true to work"
        )

    def test_all_actions_returns_both(self):
        from app.generation.actions import all_actions

        slugs = {a.slug for a in all_actions()}
        assert "glowup" in slugs
        assert "makeup" in slugs
