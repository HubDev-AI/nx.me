---
title: "feat: Prod guest-mode lockdown (audit + self-enforcing gates)"
type: feat
status: active
date: 2026-04-16
origin: docs/brainstorms/2026-04-16-prod-guest-mode-lockdown-requirements.md
---

# feat: Prod guest-mode lockdown

## Overview

Guest mode (X-Guest-Token + `users.is_guest=true`) is a local-dev
convenience today. The architecture already gates the obvious paths
in 7 places (see audit table in origin), but there is no automated
test that proves the lockdown holds when `FEATURE_AUTH_REQUIRED=true`,
no startup invariant against a misconfigured prod deploy, and a stale
guest token can linger on a device after auth is enabled. This plan
adds 6 small, independent guards that make the lockdown
self-enforcing without removing the guest implementation (which the
user wants to keep for a future feature).

## Problem Frame

See origin: `docs/brainstorms/2026-04-16-prod-guest-mode-lockdown-requirements.md`.

Short form: every existing guest gate works today, but each relies on
a future engineer remembering the rule. We want CI / startup / device
state to enforce it.

## Requirements Trace

- **R1.** End-to-end test: with `FEATURE_AUTH_REQUIRED=true`, every
  authenticated route either rejects or ignores `X-Guest-Token`.
  (origin §G1, §AC1)
- **R2.** Startup invariant: backend refuses to boot when
  `APP_ENV=production` AND `FEATURE_AUTH_REQUIRED=false`.
  (origin §G2, §AC2)
- **R3.** Route-level CI audit: every authenticated route uses one
  of `get_current_user` / `get_user_or_guest` / `require_admin`, OR
  is on an explicit public-route allowlist. New rogue routes fail in
  CI. (origin §G4, §AC3)
- **R4.** Mobile clears the SecureStore guest token the first time
  it observes `auth_required=true`, so the credential leaves the
  device. (origin §G3, §AC4)
- **R5.** Mobile UI sweep — no orphan "Continue as Guest" /
  "Skip login" affordances visible in production-mode UI.
  (origin §G5, §AC5)
- **R6.** Admin cleanup script for stale `users.is_guest=true` rows;
  dry-run by default, never auto-runs in a migration.
  (origin §G6, §AC6)

## Scope Boundaries

- No removal of any guest-mode code path. Re-enabling guest later is
  a single flag flip; this work must not break that.
- No replacement of the `FEATURE_AUTH_REQUIRED` mechanism with a
  different flag.
- No data-migration that auto-deletes guest rows. R6 ships as a
  manually-invoked script only.
- No changes to mobile session-mode semantics (`isUser` / `isGuest` /
  `isAnon`). Capability layer already correct per origin §Audit.
- No changes to dev escape hatches (`DEV_DISABLE_FEATURES`,
  `DEV_FEATURE_FOCUS`); they're already gated on `__DEV__`.

### Deferred to Separate Tasks

- A future "real guest" feature (when guest mode comes back online):
  R2's prod-boot check will need to be loosened or split into a
  separate `FEATURE_GUEST_MODE_ALLOWED_IN_PROD` flag at that time.
  Out of scope here. (origin §Re-enabling guest later.)

## Context & Research

### Relevant Code and Patterns

- `app/api/auth.py` (line 148) — existing 403 on `POST /v1/auth/guest` when auth required. Pattern to follow for "feature off ⇒ refuse" responses (uses `FEATURE_DISABLED` error code + `detail.feature` payload).
- `app/api/deps.py` (line 185-221) — `get_user_or_guest` already checks `not settings.FEATURE_AUTH_REQUIRED` before honoring `X-Guest-Token`. R1 + R3 build their assertions around the three known auth deps in this file: `get_current_user`, `get_user_or_guest`, `require_admin`.
- `app/config/__init__.py` (Settings class) — pydantic-settings v2 model. R2's invariant lives here as a `@model_validator(mode="after")`.
- `app/main.py` — FastAPI app construction; `app.routes` is the source for R1 + R3 enumeration via `app.routes` / `app.router.routes`.
- `mobile/app/_layout.tsx` (line 67-119) — `AuthGuard` runs the existing `auth_required` branch logic. R4 attaches a sibling effect that fires the purge once on the `auth_required=true` transition.
- `mobile/lib/guest-session.ts` (`getStoredGuestToken`, `getOrCreateGuestToken`) + `mobile/constants/config.ts` (`SECURE_STORE_KEYS.GUEST_TOKEN`) — R4 uses these helpers to read/clear.
- `mobile/lib/secure-storage.ts` (`deleteItem`) — clear function R4 calls.
- `tests/test_users.py`, `tests/test_features.py`, `tests/test_advisor*.py` — existing patterns for FastAPI route tests with TestClient + monkeypatched settings (use as templates for R1 + R3 tests).
- `scripts/nuke-data.py` — pattern for a destructive admin script; argparse, `--keep-demo` flag style. R6 mirrors this shape.

### Institutional Learnings

- No `docs/solutions/` entries on guest-mode hardening; this is the first.
- Per origin §Audit, both backend and mobile defaults are fail-closed (`FEATURE_AUTH_REQUIRED=true`, `PROD_DEFAULT_FEATURES.auth_required=true`). Any new code must preserve those defaults.

### External References

- None required — pydantic-settings `model_validator`, FastAPI route introspection (`app.routes` + `route.dependant.dependencies`), and React Native SecureStore are all standard, well-documented APIs. Local patterns above cover everything.

## Key Technical Decisions

- **R1 mechanism: behavioral test against the live FastAPI app.** Use `TestClient` to enumerate every route in `app.routes`. For each route that is not on the public allowlist, send a request with `X-Guest-Token=<format-valid 64-hex>` and no `Authorization` header, with `FEATURE_AUTH_REQUIRED=True`. Assert response status is 401 or 403. Rationale: testing actual request handling catches both gating bugs (route accepted token) and silent regressions (gate moves but test still passes against it). Skip routes that need request-body shape (POST/PUT) by sending `{}` and accepting 422 as "the auth gate fired before validation" — actually no, 422 means request reached the validator past auth, so 422 is a fail. Send without body and accept 401/403/405 (method not allowed if route only accepts GET).

- **R2 mechanism: pydantic `model_validator(mode="after")` on Settings.** Fires at first `from app.config import settings` import, which is the earliest point any caller can hit. Raises `ValueError` with a clear message. Pydantic wraps in `ValidationError`, FastAPI startup propagates → process exits non-zero. Alternatives rejected: (a) FastAPI lifespan event — too late, settings already read by then; (b) explicit check in `app/main.py` — easy to bypass if a worker imports settings directly.

- **R3 mechanism: introspect `route.dependant.dependencies` recursively.** FastAPI exposes the dependency tree per route as a `Dependant` object. Walk it; assert one of the three known auth callables appears in the chain, OR the route's path is on the public allowlist. Public allowlist starts as: `/v1/features`, `/v1/auth/*`, `/v1/health`, `/healthz`, `/v1/cards/{username}` (public glowup card view), `/v1/posts/{post_id}` (public post share — verify during implementation). Test failure prints the offending route + path so the contributor knows what to fix.

- **R4 mechanism: sentinel-keyed effect in AuthGuard.** Add a separate `useEffect` in `AuthGuard` that runs when `features.auth_required` becomes true. Use a SecureStore key (`nxme_guest_purged_at`) as a flag so we delete once and don't bash SecureStore on every render or app launch. On the rare auth_required→false transition (dev mode toggling), the flag stays set; new guest provisioning is unaffected (it writes a fresh token). Rationale: idempotent, observable via SecureStore inspection.

- **R5 mechanism: grep sweep + manual screen audit.** Run `grep -rin "as guest|continue.*guest|skip.*login|sign in later" mobile/`. Cross-check any matches against capability gates. If anything orphaned, add a capability gate. Document findings in commit message; if zero findings, that's the deliverable.

- **R6 mechanism: standalone script under `scripts/`.** Argparse interface: `--apply` (defaults to dry-run), `--max-rows=100` (safety cap), `--older-than-days=30` (default). Lists matching rows; with `--apply` and confirmation prompt, deletes. Imports from `app.config.settings`, uses Supabase service role. Documented in `scripts/dev-setup.sh` or a new `scripts/README.md` entry.

- **Test file layout: one combined file `tests/test_auth_invariants.py`.** Houses both R1 (behavioral) and R3 (structural) test classes. Sibling location to existing `tests/test_features.py`. Single file because they share the public-route allowlist constant and most of the same imports.

## Open Questions

### Resolved During Planning

- *Does R3's allowlist need to include `/v1/cards/{username}`?* **Yes — verified during planning context scan.** Public glowup card view; intentionally unauthenticated. Add to allowlist with comment.

- *Should R2 also forbid `auth_required=false` outside production (e.g., staging)?* **No.** Staging deliberately mirrors prod when needed and dev when convenient. Hard-fail only on `APP_ENV=production`.

- *Does mobile need a parallel R2-style invariant (refuse build if guest mode could be enabled in prod)?* **No.** Mobile dev escape hatches (`DEV_DISABLE_FEATURES`, `DEV_FEATURE_FOCUS`) are already gated on `__DEV__`, which gets stripped from production bundles by Metro. Defaults are fail-closed. The R2 backend gate is sufficient — mobile is downstream.

- *Should R6 also clear orphaned advisor memories / uploads owned by deleted guest users?* **No, deferred.** ON DELETE CASCADE on `users.id` foreign keys takes care of the major child rows (advisor_messages, user_memories, etc., per migration 0007). Object-storage orphans are tracked separately in migration 0036. Out of scope.

### Deferred to Implementation

- Exact list of FastAPI route paths that need to be on the public allowlist — confirm during R3 implementation by running the test once and adding any false positives that are genuinely public.
- Pydantic v1 vs v2 model_validator syntax detail — settled by reading the existing `app/config/__init__.py` Settings class on touch.
- Whether `route.dependant` is the right attribute to introspect on the FastAPI version pinned in `requirements.txt` (0.115.12) — verify in implementation; fallback is to walk `route.endpoint` signature.

## Implementation Units

- [ ] **Unit 1: Backend startup invariant — refuse prod boot with auth off (R2)**

**Goal:** Pydantic settings validator hard-fails at first import when `APP_ENV=production` AND `FEATURE_AUTH_REQUIRED=false`. Must run before any route handler can execute.

**Requirements:** R2.

**Dependencies:** None.

**Files:**
- Modify: `app/config/__init__.py`
- Test: `tests/test_auth_invariants.py` (new)

**Approach:**
- Add a `@model_validator(mode="after")` method on the existing Settings class. Raise `ValueError` with a message that names both flags and how to fix them.
- Validator only fires the assertion when `APP_ENV == "production"`. Other env values (development, staging, test) are unaffected.
- Test by instantiating Settings directly with the bad combination and asserting the error.

**Patterns to follow:**
- Existing pydantic v2 settings pattern in `app/config/__init__.py`.
- Existing `ValueError` style in `app/advisor/adapters/embeddings/openai.py` for "fail closed with actionable message".

**Test scenarios:**
- Happy path: `APP_ENV=development` + `FEATURE_AUTH_REQUIRED=False` → Settings instantiates fine.
- Happy path: `APP_ENV=production` + `FEATURE_AUTH_REQUIRED=True` → Settings instantiates fine.
- Error path: `APP_ENV=production` + `FEATURE_AUTH_REQUIRED=False` → raises `ValidationError` (or `ValueError` wrapped) whose message names both flags.
- Edge case: `APP_ENV=staging` + `FEATURE_AUTH_REQUIRED=False` → no error (staging deliberately permissive).

**Verification:**
- New test passes; no other tests break (550+ existing).
- Boot the backend with `APP_ENV=production FEATURE_AUTH_REQUIRED=false uvicorn app.main:app` → process exits non-zero with the actionable message.

- [ ] **Unit 2: Behavioral test — every route blocks guest tokens when auth required (R1)**

**Goal:** Enumerate every authenticated route and prove that with `FEATURE_AUTH_REQUIRED=True`, sending `X-Guest-Token` returns 401/403. Catches the case where a future PR adds a route that bypasses `get_user_or_guest`.

**Requirements:** R1.

**Dependencies:** None (Unit 1 is independent; R1 just tests the existing gate).

**Files:**
- Modify: `tests/test_auth_invariants.py` (created in Unit 1)

**Approach:**
- Build a `TestClient(app)` with `FEATURE_AUTH_REQUIRED=True` patched on settings.
- Iterate `app.router.routes` filtered to APIRoutes (skip mounts, static, internal docs).
- For each route, pick the first method (GET preferred) and request it with `X-Guest-Token=<64-hex placeholder>` and no Authorization header.
- Skip routes whose path is on the public allowlist (defined as a module-level constant shared with Unit 3).
- Assert response status in `{401, 403, 405}`. 405 is acceptable when the path doesn't accept GET — call meant the auth check would have fired before method routing on a real call. Document this in the test comment.
- 422 is a FAIL — that means the route accepted the token, validated the body, and only then complained about the body shape.

**Execution note:** Test-first — write the assertion first, run it, expect mostly green; allowlist any false positives by checking they're genuinely public, not accidentally unauthenticated.

**Patterns to follow:**
- TestClient + monkeypatched settings shape from `tests/test_features.py`, `tests/test_users.py`.

**Test scenarios:**
- Happy path (the test itself): every authenticated route returns 401/403 (or 405) when called with X-Guest-Token under FEATURE_AUTH_REQUIRED=True.
- Edge case: public allowlist matches expected routes (`/v1/features`, `/v1/auth/*`, `/v1/cards/{username}`, etc.) — assert these specific routes are hit by the iteration so the allowlist isn't accidentally over-broad.
- Negative test (future-regression catch): introduce a temporary stub route in a fixture that accepts `X-Guest-Token` directly (no `get_user_or_guest`), assert the test FAILS for it. Then remove the stub. (Inline subtest, not a permanent test.)

**Verification:**
- Test enumerates ≥ 30 routes and either gates or allowlists each.
- Test fails clearly when a contributor adds a rogue route, naming the offending path + method.

- [ ] **Unit 3: Structural test — every authenticated route uses an approved auth dep (R3)**

**Goal:** Walk each route's dependency tree; assert one of `get_current_user` / `get_user_or_guest` / `require_admin` appears, OR the route is on the public allowlist. Catches bypasses that wouldn't show up behaviorally (e.g., a route that reads `request.headers["X-Guest-Token"]` directly without using the canonical dep).

**Requirements:** R3.

**Dependencies:** Unit 2 (shares the public allowlist constant).

**Files:**
- Modify: `tests/test_auth_invariants.py`

**Approach:**
- Iterate `app.router.routes` filtered to APIRoutes.
- For each, walk `route.dependant.dependencies` recursively, collecting the underlying `call` attribute of each `Dependant`.
- Assert one of the three approved auth callables is in the collected set, OR `route.path` matches the public allowlist.
- For a route on the allowlist, additionally assert that NONE of the three approved auth callables appear (so the allowlist doesn't shadow a real gate).
- On failure: print `route.path`, `route.methods`, and the dependency callables found, plus a one-line "fix: add Depends(get_user_or_guest) or add to PUBLIC_ROUTE_ALLOWLIST".

**Patterns to follow:**
- FastAPI internal `Dependant` is documented in their source; no external library needed.

**Test scenarios:**
- Happy path: all current routes pass.
- Edge case: route with multiple `Depends(...)` (e.g., one auth + one db) — auth dep is found.
- Edge case: route with a sub-router that injects auth at the router level — recursion picks it up.
- Error path: synthetic route that uses neither approved dep nor allowlist → test fails with the route path in the message. (Inline subtest, then removed.)

**Verification:**
- Test passes. Adding a new route to `app/api/` without an auth dep makes the test fail in CI with a clear pointer.

- [ ] **Unit 4: Mobile — purge stale guest token on auth_required transition (R4)**

**Goal:** When mobile observes `features.auth_required=true`, delete `SECURE_STORE_KEYS.GUEST_TOKEN` from SecureStore exactly once. Sentinel key prevents repeated deletions.

**Requirements:** R4.

**Dependencies:** None.

**Files:**
- Modify: `mobile/app/_layout.tsx` (extend AuthGuard)
- Modify: `mobile/constants/config.ts` (add `SECURE_STORE_KEYS.GUEST_PURGED_SENTINEL` constant)
- Modify: `mobile/lib/guest-session.ts` (add `purgeGuestSession()` helper)
- Test: existing mobile test infra has near-zero coverage; out-of-scope for unit tests (per project policy in feature-flags-redesign-plan.md). Manual verification.

**Approach:**
- Add `purgeGuestSession()` in `mobile/lib/guest-session.ts`: deletes the GUEST_TOKEN key, sets the sentinel key to current ISO timestamp.
- Add a sibling `useEffect` in `AuthGuard` that depends on `features.auth_required` and `featuresLoading`. When auth becomes required AND the sentinel key is not yet set, call `purgeGuestSession()`.
- Idempotent: re-running has no effect because the sentinel is set.
- If the user later toggles auth back off (dev mode), the sentinel persists — but `getOrCreateGuestToken()` will provision a fresh token regardless. No state collision.

**Patterns to follow:**
- Existing `getOrCreateGuestToken()` / `getStoredGuestToken()` shape in `mobile/lib/guest-session.ts`.
- Existing `useEffect` style in `mobile/app/_layout.tsx:67-119`.

**Test scenarios:**
- Manual happy path: start app with `auth_required=false`, exercise enough to populate GUEST_TOKEN; then flip to `auth_required=true` (override via DEV_DISABLE_FEATURES temporarily, or simulate the response). Confirm via `getStoredGuestToken()` returning null after AuthGuard re-runs.
- Manual idempotency: kill + restart app with `auth_required=true` already set. Confirm the purge effect doesn't keep firing (sentinel check).
- Manual no-op: start fresh on `auth_required=true` (no prior token). Purge is a no-op; sentinel still gets set. No errors.

**Verification:**
- Manual sweep with iOS simulator + react-native-async-storage / SecureStore inspector.
- `cd mobile && npx tsc --noEmit && npx expo lint` clean.

- [ ] **Unit 5: Mobile UI sweep for orphan "as guest" affordances (R5)**

**Goal:** Confirm no UI element shows guest-related copy or actions outside the capability layer's gating.

**Requirements:** R5.

**Dependencies:** None.

**Files:**
- No expected modifications; document findings in the PR description.
- If any orphan is found, modify the offending screen to wrap the affordance in a capability check.

**Approach:**
- Run grep across `mobile/` for: `guest`, `as guest`, `continue.*guest`, `skip.*login`, `try.*without`, `sign in later`. Case-insensitive.
- For each match, classify as: (a) capability-gated already, (b) dev-only / __DEV__-guarded, (c) orphan needing a gate.
- For (c): wrap with `caps.canSignIn` or appropriate predicate. (Likely zero hits — capability layer was audited recently — but sweep proves it.)

**Test scenarios:**
- Zero false positives reported in the PR description, OR a one-line list of fixed orphans with file:line.

**Verification:**
- Grep output documented in PR. Capability gates added if needed.

- [ ] **Unit 6: Admin script — list/delete stale guest user rows (R6)**

**Goal:** Standalone script under `scripts/` that lists `users.is_guest=true` rows older than N days and optionally deletes them. Dry-run by default; never auto-runs.

**Requirements:** R6.

**Dependencies:** None.

**Files:**
- Create: `scripts/cleanup-guest-users.py`
- Modify: `scripts/dev-setup.sh` or add `scripts/README.md` to document usage.

**Approach:**
- Argparse interface:
  - `--older-than-days=30` (default; only consider rows whose `created_at` is older than this)
  - `--max-rows=100` (safety cap; refuse to run if matches exceed this without `--force`)
  - `--apply` (without it: print + exit; with it: prompt for confirmation, then delete)
  - `--quiet` (suppress per-row output)
- Connect via `app.config.settings.SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`.
- ON DELETE CASCADE handles child rows in advisor_messages, user_memories, uploads, etc. (per existing schema).
- Print summary at end: rows considered, rows deleted (or "would delete").

**Patterns to follow:**
- `scripts/nuke-data.py` argparse + Supabase service role pattern.

**Test scenarios:**
- Manual happy path (against local Supabase): seed 3 guest rows, run script in dry-run, verify list. Run with `--apply`, verify rows gone + cascade cleared.
- Edge case: zero matches → script reports "no rows matched" and exits 0.
- Error path: invalid `--older-than-days=-5` → argparse validation fails with clear message.
- Safety: `--max-rows=10` with 100 matches → refuses with "exceeds cap; pass --force or narrow window".

**Verification:**
- Script runs cleanly in dev. Documentation entry exists.
- No automatic cron / migration invokes it.

## System-Wide Impact

- **Interaction graph:** Backend Settings now has a startup-time validator; any code path that imports `app.config.settings` (i.e., everything) inherits the check. FastAPI's app.routes is read by the test suite; no runtime change. Mobile AuthGuard gains one effect; no other component touched.
- **Error propagation:** R2 error surfaces at process startup (clear stderr, non-zero exit). R1/R3 errors surface in CI. R4 failure is silent (best-effort purge); manual verification only.
- **State lifecycle risks:** R4 sentinel key in SecureStore persists across uninstall on iOS Keychain (default behavior). If the user re-installs the app and auth is back off, the sentinel will read as set → purge skipped. Acceptable: a re-install with no GUEST_TOKEN means there's nothing to purge anyway.
- **API surface parity:** R3 allowlist must stay in sync with the actual public routes. Adding a public route requires updating the constant — caught by R3's "allowlist matches a real route" assertion.
- **Integration coverage:** R1 + R3 together cover both behavior (does the gate fire?) and structure (is the gate even there?). Either alone misses a class of regression.
- **Unchanged invariants:** All 7 existing gates from origin §Audit stay exactly as they are. `FEATURE_AUTH_REQUIRED` semantics, capability layer derivations, and dev-escape-hatch behavior — all preserved.

## Risks & Dependencies

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| FastAPI's `route.dependant.dependencies` shape differs across versions | Med | Med (R3 false-passes) | Pin assertion to the exact API in 0.115.12; if introspection differs in a future bump, the test breaks loudly rather than silently passing. |
| R1 false negatives on POST routes (422 after auth) | Med | Med | Send no body; expect 401/403 BEFORE 422. Document in test that 422 is a real failure. |
| R2 fires in unintended environments (e.g., a script that imports settings outside production but reads a `.env.production`) | Low | Low | Validator only checks `APP_ENV == "production"` literal. Scripts in `scripts/` typically run with development APP_ENV; explicit override required. |
| R4 transition race: in-flight request uses stale token before purge lands | Low | Low | Backend ignores stale tokens (origin §Audit gate G2 backend-side). Request 401s, mobile retries via existing 401 path. |
| R6 accidentally deletes a row that became real (e.g., guest got promoted to user) | Low | High | Promotion path doesn't exist in current code; if added later, the script's `is_guest=true` filter still excludes promoted rows. Plus dry-run default + `--max-rows` cap. |
| Public allowlist drifts from reality and a sensitive route gets accidentally added | Med | High | R3 unit test runs in CI on every PR. Adding a path to the allowlist is a code-review-visible change. |

## Documentation / Operational Notes

- `app/.env.example` already documents `FEATURE_AUTH_REQUIRED=false` as dev-only. After R2 lands, also note that `APP_ENV=production` will refuse to boot with this flag false.
- `scripts/README.md` (or `scripts/dev-setup.sh` comment block) documents the `cleanup-guest-users.py` invocation.
- `app/features/README.md` may want a one-line note about the guest-mode lockdown invariants. Optional, not blocking.
- No migration runs as part of this work. R6's script is manual-only.

## Sources & References

- **Origin document:** [docs/brainstorms/2026-04-16-prod-guest-mode-lockdown-requirements.md](../brainstorms/2026-04-16-prod-guest-mode-lockdown-requirements.md)
- Related code:
  - `app/api/auth.py` (existing FEATURE_DISABLED 403 pattern)
  - `app/api/deps.py` (existing auth deps)
  - `app/config/__init__.py` (Settings class)
  - `mobile/app/_layout.tsx` (AuthGuard)
  - `mobile/lib/guest-session.ts` (helpers)
  - `scripts/nuke-data.py` (admin-script pattern)
- Related plans:
  - `docs/plans/2026-04-15-001-feat-feature-flags-redesign-plan.md` (capability layer + auth_required semantics)
- External docs: none required.
