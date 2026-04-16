"""/v1/memories mutations must accept guest tokens.

GET /v1/memories has always used `get_user_or_guest`. POST and DELETE were
accidentally gated behind `get_current_user` (auth-only), so guests who
created goals or notes from the Memories tab hit 401.

This invariant pins the intended behavior: every handler under the
`/v1/memories` surface uses `get_user_or_guest` (not `get_current_user`).
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute

from app.api.deps import get_current_user, get_user_or_guest


def _collect_dependency_callables(route: APIRoute) -> set[object]:
    """Walk the dependency tree and return every Dependant.call we find.

    Mirrors the helper in tests/test_auth_invariants.py.
    """
    seen: set[object] = set()
    stack = list(route.dependant.dependencies)
    while stack:
        dep = stack.pop()
        if dep.call is not None:
            seen.add(dep.call)
        stack.extend(dep.dependencies)
    return seen


@pytest.fixture(scope="module")
def memory_routes():
    """Return all /v1/memories{,/{id}} APIRoutes from the live app."""
    from app.main import app

    return [
        r
        for r in app.routes
        if isinstance(r, APIRoute)
        and (r.path == "/v1/memories" or r.path.startswith("/v1/memories/"))
    ]


def test_memory_routes_exist(memory_routes):
    methods = {m for r in memory_routes for m in r.methods}
    # Sanity: at minimum we expect GET, POST, DELETE on /v1/memories*.
    assert {"GET", "POST", "DELETE"} <= methods, (
        f"Expected GET/POST/DELETE on /v1/memories*, saw {methods}"
    )


def test_every_memory_route_accepts_guests(memory_routes):
    """No /v1/memories handler may use get_current_user — they all must
    use get_user_or_guest so guest tokens work for all memory CRUD."""
    offenders: list[str] = []
    for route in memory_routes:
        deps = _collect_dependency_callables(route)
        if get_current_user in deps:
            offenders.append(f"{sorted(route.methods)} {route.path}")
        assert get_user_or_guest in deps, (
            f"{sorted(route.methods)} {route.path} missing get_user_or_guest "
            f"dep — guest users cannot reach it"
        )

    assert not offenders, (
        "Memory routes must not gate on get_current_user (rejects guests). "
        f"Offenders: {offenders}"
    )
