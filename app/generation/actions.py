"""GenerationAction descriptor registry.

Each action describes one generation surface (glow-up, makeup). The registry
maps source_type → descriptor.

When ``USE_REGISTRY_DISPATCH=false`` (default) the worker and router use the
duplicated wiring in ``worker.py`` / ``api/glowup.py`` / ``api/makeup.py``.
When ``USE_REGISTRY_DISPATCH=true`` the worker validates source_type via this
registry (fail-fast on unknown types) then dispatches identically.

Descriptor fields (§5 of plan):
  slug                      — URL segment: "glowup" / "makeup"
  display_name              — human label
  capability_flag           — string passed to require_tier_feature(); None = no tier gate
  source_type               — jobs.source_type value ("glowup_analysis" / "makeup_session")
  action_type_ledger        — credit RPC action_type string; must appear in migration 0049/0066 allowlist
  post_kind                 — posts.kind value
  card_web_segment          — URL segment on card-web ("glow-up" / "makeup")
  advisor_mcp_module        — tools_*.py module name for MCP discovery
  nudge_trigger             — ARQ nudge task name, or None
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GenerationAction:
    slug: str
    display_name: str
    capability_flag: str | None
    source_type: str
    action_type_ledger: str
    post_kind: str
    card_web_segment: str
    advisor_mcp_module: str
    nudge_trigger: str | None


_REGISTRY: dict[str, GenerationAction] = {}


def register(action: GenerationAction) -> GenerationAction:
    _REGISTRY[action.source_type] = action
    return action


def get_action(source_type: str) -> GenerationAction | None:
    return _REGISTRY.get(source_type)


def all_actions() -> list[GenerationAction]:
    return list(_REGISTRY.values())


# ---------------------------------------------------------------------------
# Registered actions
# ---------------------------------------------------------------------------

GLOWUP_ACTION = register(
    GenerationAction(
        slug="glowup",
        display_name="Glow-Up",
        capability_flag=None,
        source_type="glowup_analysis",
        action_type_ledger="glowup",
        post_kind="glowup",
        card_web_segment="glow-up",
        advisor_mcp_module="tools_glowup",
        nudge_trigger="post_glowup",
    )
)

MAKEUP_ACTION = register(
    GenerationAction(
        slug="makeup",
        display_name="Makeup",
        capability_flag="makeup",
        source_type="makeup_session",
        action_type_ledger="makeup",
        post_kind="makeup",
        card_web_segment="makeup",
        advisor_mcp_module="tools_makeup",
        nudge_trigger="post_makeup",
    )
)
