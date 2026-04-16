# Prod guest-mode lockdown — requirements

**Date:** 2026-04-16
**Scope:** backend (`app/`) + mobile (`mobile/`)
**Size:** Standard (multi-surface hardening, no behavior change for the happy path)
**Related code:** `app/api/auth.py:148`, `app/api/deps.py:185-221`, `app/config/__init__.py:241`, `mobile/app/_layout.tsx:67-119`, `mobile/lib/api.ts:111-147`, `mobile/lib/capabilities.ts`, `mobile/constants/features.ts`

## Problem

Guest mode (X-Guest-Token, `users.is_guest=true` rows) exists today as a **local-dev convenience** so the app can boot without login. The user wants to keep the implementation intact for a future "real guest" feature but **guarantee that flipping `FEATURE_AUTH_REQUIRED=true` in production closes every guest entry point** — no leaked endpoint, no stale token usable, no UI affordance, no misconfiguration that silently boots prod with auth off.

The architecture already gates the obvious paths in 5+ places. The question is: **what's left that could leak when auth flips on**, and how do we make the lockdown self-enforcing rather than relying on a future engineer remembering the rule.

## Goals

1. Enumerate every guest entry point + its current gate (audit table).
2. Add the gates that are missing.
3. Make the lockdown **self-enforcing**: failing prod build / failing CI / failing startup if guest mode could leak through.
4. Preserve the ability to re-enable guest mode later by flipping a single flag — no code deletion.

## Non-goals

- Removing the guest implementation. It stays; only its prod activation is blocked.
- Replacing `FEATURE_AUTH_REQUIRED` with a different flag mechanism.
- Building a "real" guest-account product feature — out of scope.
- Auto-migrating existing `is_guest=true` rows into real users.

## Audit — existing gates (verified 2026-04-16)

| Surface | Gate | Location |
|---|---|---|
| Backend: issue new guest token | 403 when `FEATURE_AUTH_REQUIRED=true` | `app/api/auth.py:148` |
| Backend: validate guest token on protected routes | Ignores `X-Guest-Token` when `FEATURE_AUTH_REQUIRED=true`, falls through to JWT | `app/api/deps.py:202` |
| Mobile: bootstrap guest session | Skipped when `features.auth_required=true` | `mobile/app/_layout.tsx:69` |
| Mobile: provision new guest token | Returns null when `getAuthRequired()=true` | `mobile/lib/api.ts:114,135` |
| Mobile: capability gates (`canViewOwnProfile` etc.) | Guest branch requires `!features.auth_required` | `mobile/lib/capabilities.ts:67` |
| Mobile: dev escape hatches (`DEV_DISABLE_FEATURES`, `DEV_FEATURE_FOCUS`) | Both gated on `__DEV__` — stripped from prod bundle | `mobile/constants/features.ts`, `mobile/constants/config.ts` |
| Defaults | Backend `FEATURE_AUTH_REQUIRED: bool = True`; mobile `PROD_DEFAULT_FEATURES.auth_required: true` | Fail-closed on either side |

## Audit — gaps (to fix)

### G1 — No enforcement test

There is no test that asserts "with `FEATURE_AUTH_REQUIRED=true`, every guest entry point returns 401/403". Today's gates work because we eyeballed them. A future PR that adds a route accepting `X-Guest-Token` directly (bypassing `get_user_or_guest`) would slip through.

### G2 — No prod-boot invariant

Backend startup does not refuse to boot with `APP_ENV=production` AND `FEATURE_AUTH_REQUIRED=false`. A misconfigured deploy would silently land in production accepting guests.

### G3 — Stale stored guest token persists in mobile

`mobile/lib/api.ts:113` returns the SecureStore-stored guest token for every request even when `getAuthRequired()=true`. Backend ignores it (correct), but the token sits on the device indefinitely. If a build regression ever made the backend honour stale tokens, it would re-authenticate. **Mobile should purge the stored token the first time it sees `auth_required=true`** so the credential leaves the device.

### G4 — No route-level audit script

Adding a new route is an opportunity to forget the auth dep. Need a CI check that: (a) every authenticated route uses one of `get_current_user` / `get_user_or_guest` / `require_admin`, and (b) no route reads `X-Guest-Token` outside `get_user_or_guest`.

### G5 — Mobile UI sweep not done

Capability layer is correct, but no audit confirms there's no orphan "Continue as Guest" / "Skip login" button or copy that doesn't route through capabilities. Low-likelihood risk but worth one sweep.

### G6 — Stale `users.is_guest=true` rows in DB

Local dev databases accumulate guest rows. Once `auth_required` flips on (in any environment), these rows sit forever. They cannot authenticate (G2 backend gate). Cleanup is admin-script territory, not auto-migration — so production never auto-deletes user data.

## Solution

### Solution shape

Six small, independent changes — most under 50 LOC each. Each one is verifiable in isolation. None changes the happy path.

**Backend**

- **R1.** New test `tests/test_guest_lockdown.py` — for each route in `app.api`, assert that with `FEATURE_AUTH_REQUIRED=true`, sending `X-Guest-Token` (and no JWT) returns 401/403. Drives a per-route enumeration via FastAPI's route registry.
- **R2.** Pydantic settings validator (or `app/main.py` startup hook) that raises if `APP_ENV == "production" and FEATURE_AUTH_REQUIRED == False`. Hard fail at import time so a misconfigured container restarts loudly.
- **R3.** Test/lint: enumerate all `@router.*` handlers in `app/api/`. Assert each handler's dependency tree includes one of `get_current_user`, `get_user_or_guest`, `require_admin`, OR the handler is on an explicit allowlist of public routes (e.g., `/v1/features`, `/v1/auth/*`). Test fails with clear message if a new route doesn't fit.
- **R6 (deferred, scripted only).** Admin script `scripts/cleanup-guest-users.py` that lists / deletes `users.is_guest=true` rows older than N days. Manual invocation only, not migration.

**Mobile**

- **R4.** When mobile observes `features.auth_required=true` for the first time after boot, call `deleteItem(SECURE_STORE_KEYS.GUEST_TOKEN)` to clear the stale credential. Add to `AuthGuard` after the feature flags resolve.
- **R5.** Sweep mobile screens + components for any text/button mentioning "guest" / "without an account" / "skip" that's not gated by `caps.canSignIn` or equivalent. Document in a short `mobile/UI_MAP.md` patch if anything found.

### Acceptance criteria

- **AC1.** With `FEATURE_AUTH_REQUIRED=true`, the new test in R1 passes — every route either rejects or ignores `X-Guest-Token`.
- **AC2.** Setting `APP_ENV=production` + `FEATURE_AUTH_REQUIRED=false` and starting the backend raises `RuntimeError` (or pydantic `ValidationError`) before the first request lands.
- **AC3.** New PR that adds a route reading `X-Guest-Token` directly (without `get_user_or_guest`) makes the R3 test fail in CI.
- **AC4.** Toggling `auth_required` from false→true in mobile clears the stored guest token from SecureStore on next launch (verified by `getStoredGuestToken()` returning null after the transition).
- **AC5.** Manual sweep produces zero "as guest" affordances visible in production-mode UI (i.e., `auth_required=true`).
- **AC6.** Cleanup script lists guest rows correctly and deletes them on `--apply`. No production migration auto-deletes data.

### Re-enabling guest later

The architecture is preserved. Future "real guest" feature flips `FEATURE_AUTH_REQUIRED=false` (per environment) and:
- Backend gates open automatically (G2 in audit table).
- Mobile gates open automatically.
- Capability layer derives correctly.
- The R2 prod-boot check is the only friction — needs to be loosened to "warn but allow" or split into a separate `FEATURE_GUEST_MODE_ALLOWED_IN_PROD` flag at that time. Out of scope for this brainstorm.

## Risks

- **R3 test brittleness.** A test that walks FastAPI's route registry and inspects `Depends(...)` is fragile to dependency-tree changes. Mitigation: introspect `route.dependant.dependencies` recursively for the auth dep functions; allowlist the small set of public routes explicitly.
- **R4 transition race.** If a request is in flight when the auth_required transition fires, it could be retried with the stale guest token before the purge lands. Acceptable: backend ignores the token, request just fails normally (401), retry path takes over.
- **R6 deletion liability.** Even though dev-only, accidental run on prod-shaped data would delete users. Mitigation: script requires `--apply` (defaults to dry-run), plus a `--max-rows` safety cap.

## Sources & references

- Existing feature-flag plan: `docs/plans/2026-04-15-001-feat-feature-flags-redesign-plan.md`
- Existing capability-layer design: `docs/superpowers/specs/2026-04-15-feature-flags-redesign-design.md`
- Backend defaults: `app/config/__init__.py:241`
- Mobile defaults: `mobile/constants/features.ts`
