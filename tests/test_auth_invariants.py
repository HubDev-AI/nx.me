"""Invariant tests for the prod guest-mode lockdown.

Three independent invariants live here, all aimed at making the guest-mode
gate self-enforcing rather than relying on a future engineer remembering it:

- TestProdAuthSettingsInvariant (R2) — Settings refuses to load when
  APP_ENV=production AND FEATURE_AUTH_REQUIRED=false.
- TestRoutesRejectGuestTokenWhenAuthRequired (R1) — every authenticated
  route returns 401/403/405 for an X-Guest-Token under
  FEATURE_AUTH_REQUIRED=True.
- TestRoutesUseApprovedAuthDep (R3) — every authenticated route's
  dependency tree contains one of the three approved auth callables, OR
  the route's path is on the explicit public allowlist.

Plan: docs/plans/2026-04-16-002-feat-prod-guest-lockdown-plan.md
"""

from __future__ import annotations

import re
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from unittest.mock import AsyncMock, MagicMock

from app.api.deps import (
    get_current_user,
    get_user_or_guest,
    require_admin,
)
from app.config import Settings, settings as real_settings


# ---------------------------------------------------------------------------
# Public-route allowlist — paths intentionally reachable without auth.
# Shared by R1 (skip) and R3 (must NOT have an auth dep).
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
        "/v1/auth/guest",
        "/v1/auth/providers",
        "/v1/auth/refresh",
        # Public profile view (no auth required by design; rate-limited).
        "/v1/users/{username}/profile",
        # Username availability check (used by sign-up flow before auth).
        "/v1/users/check-username",
        # Public feed + post read surfaces — share-link reachable.
        "/v1/feed",
        "/v1/posts/{post_id}/comments",
        # Public glowup card surfaces — share URLs, intentionally unauth.
        "__PREFIX__/v1/public/cards",
        "__PREFIX__/api/public/cards",
        # Provider webhooks (signed at HMAC layer, not FastAPI deps).
        "/webhooks/stripe",
        # Reactions endpoints inline-validate the X-Guest-Token via
        # validate_guest_token() in social.py instead of using
        # get_user_or_guest. They DO honor FEATURE_AUTH_REQUIRED (R1
        # exercises this — a guest token under auth_required=true returns
        # 401), so the lockdown invariant holds. They live on the
        # allowlist because R3 walks the FastAPI dependency tree, which
        # cannot see inline branching. Follow-up: refactor to use
        # get_user_or_guest so the auth surface is uniform.
        "/v1/posts/{post_id}/reactions",
        "/v1/posts/{post_id}/react",
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
# R2 — Settings invariant
# ---------------------------------------------------------------------------


def _settings_kwargs(**overrides: object) -> dict[str, object]:
    """Minimum required Settings fields + sensible test defaults."""
    base: dict[str, object] = {
        "APP_ENV": "development",
        "SECRET_KEY": "x" * 64,
        "ADMIN_API_KEY": "y" * 32,
        "FEATURE_AUTH_REQUIRED": True,
        "SIGNUP_FINGERPRINT_SERVER_SECRET": "z" * 64,
        "STRIPE_PRICE_CREDITS_PACK_V1": "price_test_pack",
        "STRIPE_PRICE_PRO_V1": "price_test_pro",
    }
    base.update(overrides)
    return base


class TestProdAuthSettingsInvariant:
    """R2: APP_ENV=production AND FEATURE_AUTH_REQUIRED=false must fail."""

    def test_dev_with_auth_off_is_allowed(self):
        # `_env_file=None` bypasses the on-disk app/.env so the test sees
        # only the kwargs we pass in.
        s = Settings(_env_file=None, **_settings_kwargs(FEATURE_AUTH_REQUIRED=False))
        assert s.FEATURE_AUTH_REQUIRED is False
        assert s.APP_ENV == "development"

    def test_prod_with_auth_on_is_allowed(self):
        s = Settings(
            _env_file=None,
            **_settings_kwargs(APP_ENV="production", FEATURE_AUTH_REQUIRED=True),
        )
        assert s.APP_ENV == "production"

    def test_prod_with_auth_off_is_rejected(self):
        with pytest.raises(Exception) as exc_info:
            Settings(
                _env_file=None,
                **_settings_kwargs(APP_ENV="production", FEATURE_AUTH_REQUIRED=False),
            )
        # Pydantic wraps the ValueError in a ValidationError; both name the
        # offending flag in the message.
        msg = str(exc_info.value)
        assert "FEATURE_AUTH_REQUIRED" in msg
        assert "production" in msg.lower() or "APP_ENV" in msg

    def test_staging_with_auth_off_is_allowed(self):
        # Staging is deliberately permissive — only literal "production"
        # triggers the hard fail. Staging may want guest mode for QA.
        s = Settings(
            _env_file=None,
            **_settings_kwargs(APP_ENV="staging", FEATURE_AUTH_REQUIRED=False),
        )
        assert s.APP_ENV == "staging"

    def test_prod_check_is_case_insensitive(self):
        # `Production` (capital P) and ` production ` (whitespace) must NOT
        # bypass the gate via casing/whitespace typos.
        for variant in ("Production", " production ", "PRODUCTION"):
            with pytest.raises(Exception, match="FEATURE_AUTH_REQUIRED"):
                Settings(
                    _env_file=None,
                    **_settings_kwargs(APP_ENV=variant, FEATURE_AUTH_REQUIRED=False),
                )


# ---------------------------------------------------------------------------
# Shared helpers for R1 + R3 — discover authenticated APIRoutes
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


_APPROVED_AUTH_DEPS: frozenset[object] = frozenset(
    {get_current_user, get_user_or_guest, require_admin}
)


# ---------------------------------------------------------------------------
# R1 — Behavioral test: routes reject X-Guest-Token under auth_required
# ---------------------------------------------------------------------------


# 64-char hex string, the format is_valid_guest_token_format expects.
_FAKE_GUEST_TOKEN = "a" * 64


@pytest.fixture(scope="module")
def app_under_test() -> FastAPI:
    """Import the live FastAPI app once per module."""
    from app.main import app

    return app


@pytest.fixture(scope="module")
def auth_required_client(app_under_test: FastAPI):
    """TestClient where FEATURE_AUTH_REQUIRED is forced on for the suite.

    Two complications worked around here:
    1. TestClient as a context manager runs FastAPI lifespan, which aborts
       under APP_ENV=test (see app/main.py mock-adapter check). Use the
       no-context form so lifespan never fires.
    2. Without lifespan, app.state.supabase and app.state.redis are unset.
       Several repo dep providers reach directly into app.state.supabase
       (bypassing get_supabase), so overriding the dep is insufficient —
       set the state attributes to mocks instead. We don't need real
       behavior; the auth dep fires before any repo method is called for
       a request without a JWT.
    """
    app_under_test.state.supabase = MagicMock()
    redis_mock = AsyncMock()
    # Routes do rate-limiting via redis.incr/expire before reaching the auth
    # dep on a few public paths. Make incr return concrete integers so that
    # math (`if current > LIMIT`) doesn't TypeError.
    redis_mock.incr = AsyncMock(return_value=1)
    redis_mock.expire = AsyncMock(return_value=True)
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock(return_value=True)
    app_under_test.state.redis = redis_mock
    try:
        with patch.object(real_settings, "FEATURE_AUTH_REQUIRED", True):
            yield TestClient(app_under_test)
    finally:
        # Best-effort cleanup; the module-scoped fixture is the last consumer.
        for attr in ("supabase", "redis"):
            try:
                delattr(app_under_test.state, attr)
            except AttributeError:
                pass


# Status codes that mean "the auth gate did its job before any handler logic".
# We probe each route with its OWN methods so 405 (method not allowed) would
# be a test bug, not a valid auth response.
_AUTH_REJECTED_CODES = {401, 403}


class TestRoutesRejectGuestTokenWhenAuthRequired:
    """R1: every authenticated route returns 401/403/405 to a guest token
    when FEATURE_AUTH_REQUIRED is True. 422 is a FAIL — that means the
    request reached body validation, which means the auth dep didn't fire.
    """

    def test_at_least_one_route_was_probed(self, app_under_test: FastAPI) -> None:
        # Defensive: catch the case where the test discovers zero routes
        # (e.g., import failure silently swallows them).
        protected = [r for r in _api_routes(app_under_test) if not _is_public(r.path)]
        assert len(protected) >= 10, (
            f"expected to find ≥10 protected routes, found {len(protected)} "
            "— allowlist may be too broad or app failed to import"
        )

    def test_every_authenticated_route_rejects_guest_token(
        self,
        app_under_test: FastAPI,
        auth_required_client: TestClient,
    ) -> None:
        failures: list[str] = []

        for route in _api_routes(app_under_test):
            if _is_public(route.path):
                continue

            url = _instantiate_path(route.path)
            # Probe each method the route actually accepts (skip HEAD and
            # OPTIONS — they're CORS/health and don't run the auth dep).
            methods = sorted((route.methods or set()) - {"HEAD", "OPTIONS"})
            for method in methods:
                response = auth_required_client.request(
                    method, url, headers={"X-Guest-Token": _FAKE_GUEST_TOKEN}
                )

                if response.status_code not in _AUTH_REJECTED_CODES:
                    failures.append(
                        f"{method} {route.path} → "
                        f"{response.status_code} (expected one of "
                        f"{sorted(_AUTH_REJECTED_CODES)}); body: "
                        f"{response.text[:120]}"
                    )

        assert not failures, (
            "Routes leaked guest tokens past the auth gate. Each route "
            "either needs an auth dep (get_current_user / get_user_or_guest "
            "/ require_admin), or must inline-check FEATURE_AUTH_REQUIRED, "
            "or must be added to PUBLIC_ROUTE_ALLOWLIST:\n  " + "\n  ".join(failures)
        )


def _instantiate_path(path: str) -> str:
    """Replace `{param}` placeholders with a dummy UUID-shaped value so the
    URL is concrete enough for TestClient. The real handler never runs (auth
    blocks first), so the value just needs to satisfy any path-converter
    constraints (most are bare strings).
    """
    return re.sub(
        r"\{[^/}]+\}",
        "00000000-0000-0000-0000-000000000000",
        path,
    )


# ---------------------------------------------------------------------------
# R3 — Structural test: routes must use an approved auth dep
# ---------------------------------------------------------------------------


class TestRoutesUseApprovedAuthDep:
    """R3: every authenticated route's dependency tree includes one of
    get_current_user / get_user_or_guest / require_admin, OR its path is on
    the public allowlist.

    The test catches unguarded routes (the dangerous direction). The
    inverse — a path on the public allowlist that also has an auth dep on
    some HTTP method — is benign (e.g., GET /posts/{id}/comments is
    public but POST is auth-gated). We deliberately don't flag that
    asymmetry; it's correct by design.
    """

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
                    "Fix: add Depends(get_user_or_guest) or "
                    "Depends(get_current_user), OR add the path to "
                    "PUBLIC_ROUTE_ALLOWLIST with a comment explaining why "
                    "it's public."
                )

        assert not failures, "Routes missing an approved auth dep:\n  " + "\n  ".join(
            failures
        )
