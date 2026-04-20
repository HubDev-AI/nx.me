"""Invariant test: every authenticated route uses an approved auth dep.

Auth is not a runtime-toggleable feature — every non-allowlisted route in
`app/api/` must carry an approved auth dep in its dependency tree. Adding a
new route without one fails this test.

The public-route allowlist enumerates every path intentionally reachable
without a JWT (login endpoints, health probes, Stripe webhook, card-web
public preview).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.routing import APIRoute

import pytest

from app.api.deps import (
    get_current_user,
    require_admin,
)


# ---------------------------------------------------------------------------
# Public-route allowlist — paths intentionally reachable without auth.
# The test skips these when verifying every route has an auth dep.
# Patterns use FastAPI path-template syntax with `{param}` placeholders.
# ---------------------------------------------------------------------------

PUBLIC_ROUTE_ALLOWLIST: frozenset[str] = frozenset(
    {
        # Health + readiness (load balancer + uptime probes).
        "/health",
        "/healthz",
        "/readiness",
        # Feature flag publication (used by the mobile app's bootstrap).
        "/v1/features",
        # Auth entry points — pre-login flows. Listed explicitly (NOT a
        # prefix) because /v1/auth/{me,logout,account,verify-email} DO
        # require a JWT and must keep their auth dep.
        "/v1/auth/register",
        "/v1/auth/email-login",
        "/v1/auth/login",
        "/v1/auth/tiktok-login",
        "/v1/auth/providers",
        "/v1/auth/refresh",
        # Public glowup card surfaces — share URLs, intentionally unauth.
        "__PREFIX__/v1/public/cards",
        "__PREFIX__/api/public/cards",
        # Provider webhooks (signed at HMAC layer, not FastAPI deps).
        "/webhooks/stripe",
    }
)


def _is_public(path: str) -> bool:
    """Return True if the route path matches the allowlist (exact or prefix)."""
    if path in PUBLIC_ROUTE_ALLOWLIST:
        return True
    for entry in PUBLIC_ROUTE_ALLOWLIST:
        if entry.startswith("__PREFIX__") and path.startswith(
            entry.removeprefix("__PREFIX__")
        ):
            return True
    return False


# ---------------------------------------------------------------------------
# Shared helpers — discover authenticated APIRoutes
# ---------------------------------------------------------------------------


def _api_routes(app: FastAPI) -> list[APIRoute]:
    """Return all FastAPI APIRoutes (skip mounts, websockets, internal docs)."""
    return [r for r in app.router.routes if isinstance(r, APIRoute)]


def _collect_dependency_callables(route: APIRoute) -> set[object]:
    """Walk the dependency tree and return every Dependant.call we find."""
    seen: set[object] = set()
    stack = list(route.dependant.dependencies)
    while stack:
        dep = stack.pop()
        if dep.call is not None:
            seen.add(dep.call)
        stack.extend(dep.dependencies)
    return seen


_APPROVED_AUTH_DEPS: frozenset[object] = frozenset({get_current_user, require_admin})


# ---------------------------------------------------------------------------
# Structural test: routes must use an approved auth dep
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def app_under_test() -> FastAPI:
    """Import the live FastAPI app once per module."""
    from app.main import app

    return app


class TestRoutesUseApprovedAuthDep:
    """Every authenticated route's dependency tree includes one of
    get_current_user / require_admin, OR its path is on the public allowlist.

    The test catches unguarded routes (the dangerous direction).
    """

    def test_at_least_one_protected_route_exists(self, app_under_test: FastAPI) -> None:
        # Defensive: catch the case where the test discovers zero routes
        # (e.g., import failure silently swallows them).
        protected = [r for r in _api_routes(app_under_test) if not _is_public(r.path)]
        assert len(protected) >= 10, (
            f"expected to find ≥10 protected routes, found {len(protected)} "
            "— app may have failed to import or routes were mistakenly added to "
            "PUBLIC_ROUTE_ALLOWLIST"
        )

    def test_every_route_is_either_auth_gated_or_explicitly_public(
        self, app_under_test: FastAPI
    ) -> None:
        failures: list[str] = []

        for route in _api_routes(app_under_test):
            deps = _collect_dependency_callables(route)
            has_auth_dep = bool(deps & _APPROVED_AUTH_DEPS)
            is_public = _is_public(route.path)

            if not has_auth_dep and not is_public:
                failures.append(
                    f"{route.path} ({sorted(route.methods or [])}) — "
                    "no approved auth dep and not on PUBLIC_ROUTE_ALLOWLIST. "
                    "Fix: add Depends(get_current_user), OR add the path to "
                    "PUBLIC_ROUTE_ALLOWLIST with a comment explaining why "
                    "it's public."
                )

        assert not failures, "Routes missing an approved auth dep:\n  " + "\n  ".join(
            failures
        )
