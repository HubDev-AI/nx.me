---
title: "feat: Feature flags redesign — usage + ergonomics"
type: feat
status: active
date: 2026-04-15
origin: docs/superpowers/specs/2026-04-15-feature-flags-redesign-design.md
---

# feat: Feature flags redesign — usage + ergonomics

## Overview

The feature-flag infrastructure is technically complete but has usage-level defects: the profile screen is broken for guests when `auth_required=false`, every screen inlines its own `(flag × session)` booleans, adding a new flag touches six files with no drift detection, and no test guarantees new routers stay gated.

This plan introduces a single **capability layer** (`useCapabilities()`) in the mobile app, adds **two backend parity/coverage tests**, fixes the **guest profile bug**, and documents the **3-step add-a-flag process**. No infrastructure changes — `FeatureFlags` pydantic model, `GET /v1/features`, dev overrides, and `require_app_feature()` all stay as-is.

## Problem Frame

NXME now ships `auth_required`, `social_enabled`, `advisor_enabled`, `share_enabled`, `onboarding_enabled` flags end-to-end (backend → wire → mobile). Four usage issues surfaced in PR2 handoff:

1. **Guest profile broken.** `mobile/app/(tabs)/profile.tsx:40,170` gates on `session.isUser` alone. A guest with a valid guest token in `auth_required=false` mode sees a sign-in CTA instead of their own profile and glowups.
2. **No centralized `(flag × session)` rule.** Each screen reconstructs its own boolean — drift inevitable.
3. **Adding a flag touches six files** with no CI detection if backend and mobile registries drift.
4. **No router-coverage enforcement.** Ungated `social`/`advisor` routers can slip in.

Origin doc: `docs/superpowers/specs/2026-04-15-feature-flags-redesign-design.md` (design approved).

## Requirements Trace

- **R1.** Guests with a valid guest token and `auth_required=false` render the full profile screen (header + glowup grid + menu without Log Out / Sign In). *(origin: Goals §1, Success Criteria §1)*
- **R2.** UI code outside the capabilities module and feature infrastructure never reads raw `features.X` for gating. *(origin: Invariant 1, Success Criteria §2)*
- **R3.** Backend flag-gated routers declare `Depends(require_app_feature("<flag>"))` at the router level, enforced by a CI test. *(origin: Invariants 2 & 4, Success Criteria §4)*
- **R4.** Mobile `FeatureFlags` interface and backend `FeatureFlags.model_fields` are asserted equal by a CI test. *(origin: Invariant 3, Success Criteria §3)*
- **R5.** `capabilities.test.ts` matrix covers every `(sessionMode × features subset)` combination used in production. *(origin: Success Criteria §5)*
- **R6.** `app/features/README.md` documents the 3-step add-a-flag flow; `CLAUDE.md` records the "never read raw flags" convention. *(origin: Success Criteria §6 & §7)*

## Scope Boundaries

- No codegen, no remote-config service, no per-user overrides.
- No changes to `FeatureFlags` pydantic model (unless a new flag is surfaced during Unit 4 audit).
- No changes to `FeaturesProvider`, `features-state.ts`, dev-override mechanism, or `GET /v1/features` wire format.
- No capability for auth-provider selection — `useEnabledProviders` stays separate.
- No changes to guest-token semantics or `get_user_or_guest`.
- `canEditProfile=false` for guests in this iteration (may relax later).

## Context & Research

### Relevant Code and Patterns

- **Backend flag source:** `app/features/__init__.py` — `FeatureFlags` model, `get_features()`, `is_enabled()`.
- **Backend dependency:** `app/api/deps.py:477-503` — `require_app_feature(feature)` raises `403 FEATURE_DISABLED`.
- **Existing router-level gates (verified):** `app/api/posts.py:46`, `app/api/social.py:47`, `app/api/blocks.py:19`, `app/api/advisor.py:52` — all use `Depends(require_app_feature(...))` in router prefix.
- **Mobile flag mirror:** `mobile/constants/features.ts` — `FeatureFlags` interface, `PROD_DEFAULT_FEATURES`, `DEV_SHORT_NAME_TO_FLAG`, `applyDevOverrides()`.
- **Mobile context:** `mobile/lib/features-context.tsx` — cold-start fetch, dev overrides, `useFeatures()`.
- **Session primitive:** `mobile/lib/session.ts` — `SessionMode = "user" | "guest" | "anon"` + `isUser`/`isGuest`/`isAnon` booleans (ready to compose into capabilities).
- **Raw-flag call sites (4 files, verified):** `mobile/app/_layout.tsx:55,91,103,113,114`, `mobile/app/(tabs)/_layout.tsx:218,219`, `mobile/components/advisor/ChatView.tsx:97,98`, `mobile/lib/session.ts:4` (comment only).
- **Profile data flow:** `mobile/components/profile/useProfile.ts` hits `GET /v1/users/{username}/profile`, `GET /v1/users/{username}/history`, `PATCH /v1/users/{username}`.

### Institutional Learnings

- **PR2 handoff** (Memoria `feature_flags_pr2_handoff.md`): PR1 backend merged; this plan *is* PR2 scope.
- **No env fallbacks** (CLAUDE.md): already honored — `FeatureFlags` fields are all required booleans.
- **No magic strings** (CLAUDE.md): flag names already centralized in `FeatureFlags`; capability names will live in the `Capabilities` interface.
- **Phased execution** (CLAUDE.md): five phases, ≤5 files each, commit after each.

### External References

None needed. Pattern is idiomatic React (derived state via hook) + pytest file-scan tests.

## Key Technical Decisions

- **Capability layer lives in `mobile/lib/capabilities.ts`, not a context.** Derivation is pure `(features, session) → booleans`; no subscription surface beyond the existing `useFeatures()` + `useAuth()` contexts it reads. Keeps renders cheap and testable as a pure function.
- **Raw `useFeatures()` is still allowed inside `capabilities.ts` itself, for loading-state checks (e.g., splash screen on `isLoading`), and for session-bootstrap logic that runs before `useAuth()` is ready** (`AuthGuard` in `mobile/app/_layout.tsx`, lines 55-74 — the guest-token-issuance effect). Migrating those to `useCapabilities()` would introduce a circular init dependency. All other UI gating must go through `useCapabilities()`. Manual grep enforcement in Unit 3 verification; no CI gate this iteration.
- **Registry-parity test uses regex extraction, not runtime import.** `mobile/constants/features.ts` is TypeScript — Python tests cannot import it. Regex-extract the `FeatureFlags` interface body, parse `<name>: boolean;` lines, assert set equality against `FeatureFlags.model_fields.keys()`. Fails CI on any asymmetric change.
- **Router-coverage test uses explicit allowlist, not auto-discovery.** `FLAG_GATED_ROUTERS` in `tests/test_feature_flag_coverage.py` is the single declaration of "which routers must be gated on which flag". Adding a new gated router requires a one-line allowlist edit, which is visible in review.
- **Fix mis-gated `/users/{username}/profile` route** (see Open Questions). Remove the `social_enabled` dep from this route: viewing a profile is identity lookup, not a social feature. Without this fix, R1 is unreachable when `social_enabled=false`.
- **Guest menu omits `Edit Profile` and `Log Out`.** `canEditProfile` and `canSignOut` derive from `session.isUser` only, per the result matrix in the origin doc.

## Open Questions

### Resolved During Planning

- **Q: Does `/v1/users/{username}/profile` work for a guest when `auth_required=false`?**
  **A:** Not currently. `app/api/users.py:167-170` gates the route on `Depends(require_app_feature("social_enabled"))`. When `social_enabled=false` (likely concurrent with `auth_required=false` for the "solo glowup app" deployment), guests get `403 FEATURE_DISABLED`. Unit 4 must remove this dep: identity lookup is not a social feature. `get_user_or_guest` already accepts guest tokens on non-gated routes, so post-fix this Just Works. *(discovered during planning; not mentioned in origin doc)*
- **Q: Does `canSubscribe` need flag support today?**
  **A:** No — stub to `true` until premium tiering adds a flag. Origin doc appendix agrees.
- **Q: Should `buildMenu()` live in `profile.tsx` or its own file?**
  **A:** Own file — `mobile/components/profile/menu.ts`. Keeps `profile.tsx` focused on screen wiring; menu derivation is pure and trivially unit-testable.

### Deferred to Implementation

- Exact regex for the parity test's TypeScript-interface extraction — will be tuned against the current file in Unit 1.
- Whether any non-allowlisted router reveals a missing gate during Unit 4's audit (and thus needs a new entry or a bug fix). Coverage test output drives this.
- **Guest-username resolution for Unit 2.** `authUsername` is currently hydrated from `SecureStore` key `nxme_username`, populated only during real-user login flows (`mobile/lib/auth-context.tsx:44-69`). Guests may not have a stored username, in which case `useProfile().loadProfile(authUsername)` has no argument. Unit 2 will either (a) extend guest-token issuance to return/cache a username, (b) read it from a `/v1/guest/me`-style endpoint, or (c) fall through to the existing "complete your profile" fallback screen and log a known-gap warning. Decision deferred until the implementer sees what `getOrCreateGuestToken()` actually returns at runtime.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

```
┌──────────────────────────────────────────────────────────────┐
│  mobile/lib/capabilities.ts                                  │
│                                                              │
│  const { features } = useFeatures();                         │
│  const { session }  = useAuth();                             │
│                                                              │
│  return {                                                    │
│    canViewOwnProfile: session.isUser                         │
│                    || (session.isGuest && !auth_required),   │
│    canEditProfile  : session.isUser,                         │
│    canSignOut      : session.isUser,                         │
│    canSignIn       : !session.isUser,                        │
│    canSeeFeed      : social_enabled,                         │
│    canUseAdvisor   : advisor_enabled,                        │
│    canShareGlowup  : share_enabled,                          │
│    canSeeOnboarding: onboarding_enabled,                     │
│    canSubscribe    : true,    // stub until premium tiering  │
│    canReact        : social_enabled,                         │
│    requiresAuth    : auth_required,                          │
│  };                                                          │
└──────────────────────────────────────────────────────────────┘
```

Result matrix (verbatim from origin §Guest profile fix):

| Session ＼ auth_required | true | false |
|---|---|---|
| **anon** | Sign-in CTA | Sign-in CTA (guests only exist after guest-token issuance) |
| **guest** | N/A — guest tokens not issued | Full profile, menu = [Subscription, Settings] |
| **user** | Full profile, menu = [Edit, Subscription, Settings, Log Out] | Same |

## Implementation Units

- [x] **Unit 1: Capability hook + registry-parity test (foundation)**

**Goal:** Introduce `useCapabilities()` and the backend↔mobile registry parity test. No consumers yet.

**Requirements:** R2, R4, R5.

**Dependencies:** None.

**Files:**
- Create: `mobile/lib/capabilities.ts`
- Create: `mobile/lib/capabilities.test.ts`
- Create: `tests/test_feature_registry_parity.py`

**Approach:**
- `capabilities.ts` exports `Capabilities` interface + `useCapabilities()` hook composing `useFeatures()` + `useAuth()`. Pure derivation; memo via `useMemo` on `(features, session.mode)`.
- `capabilities.test.ts` uses matrix-driven cases mocking `useFeatures` and `useAuth`.
- `test_feature_registry_parity.py` reads `mobile/constants/features.ts` from repo root, regex-extracts the `FeatureFlags` interface body, parses `<name>: boolean;` lines into a set, asserts set-equality with `FeatureFlags.model_fields.keys()`.

**Execution note:** Test-first for the capability derivation — matrix test should be written alongside the hook, not after.

**Patterns to follow:**
- `mobile/lib/features-state.ts` for module-style exports from `mobile/lib/`.
- `tests/test_features.py` for backend-test scaffolding (pytest fixtures, import of `FeatureFlags`).
- `mobile/lib/api.test.ts` for Jest mock patterns for React hooks.

**Test scenarios:**
- *Happy path:* `user + auth_required=true` → `canViewOwnProfile=true, canEditProfile=true, canSignOut=true, canSignIn=false, requiresAuth=true`.
- *Happy path:* `guest + auth_required=false + social_enabled=false` → `canViewOwnProfile=true, canEditProfile=false, canSignOut=false, canSignIn=true, canSeeFeed=false`.
- *Edge case:* `user + auth_required=false` → `canViewOwnProfile=true, canSignOut=true, canSignIn=false` (user branch dominates regardless of flag).
- *Edge case:* `anon + auth_required=true` → `canViewOwnProfile=false, canSignIn=true, canSignOut=false`.
- *Edge case (impossible-at-runtime, kept for purity):* `guest + auth_required=true` → `canViewOwnProfile=false` (capability layer stays pure regardless of runtime invariants).
- *Social matrix:* `social_enabled ∈ {true, false}` × `advisor_enabled ∈ {true, false}` × `share_enabled ∈ {true, false}` × `onboarding_enabled ∈ {true, false}` covering `canSeeFeed`, `canUseAdvisor`, `canShareGlowup`, `canSeeOnboarding`, `canReact`. Parametrized table; does not need to enumerate all 16 combos — 4 representative rows suffice.
- *Parity test happy path:* both registries contain `{auth_required, social_enabled, share_enabled, onboarding_enabled, advisor_enabled}` → passes.
- *Parity test drift:* add a phantom field to the regex's source string under test (injected via a tmp file or monkeypatched reader) → fails with a clear "mobile has X, backend doesn't" message. Inverse drift direction also asserted.

**Verification:**
- `cd mobile && npx tsc --noEmit && npx expo lint && npx jest lib/capabilities.test.ts` → green.
- `make test -- tests/test_feature_registry_parity.py` → green.
- Grep confirms no consumer of `useCapabilities()` yet (added in later units).

---

- [ ] **Unit 2: Guest profile fix (user-reported bug)**

**Goal:** Guest users with `auth_required=false` see their full profile + glowups grid, not a sign-in CTA. Menu omits Log Out / Sign In.

**Requirements:** R1, R2.

**Dependencies:** Unit 1.

**Files:**
- Modify: `mobile/app/(tabs)/profile.tsx`
- Create: `mobile/components/profile/menu.ts`
- Create: `mobile/app/(tabs)/__tests__/profile.test.tsx`

**Approach:**
- Replace the `const isAuthenticated = session.isUser;` + `if (!isAuthenticated)` branch with `const caps = useCapabilities();` + `if (!caps.canViewOwnProfile)`.
- **Rewrite the profile-load effect** (`profile.tsx:63-67`): swap the `isAuthenticated` guard for `caps.canViewOwnProfile`. Current code gates on `session.isUser`, so guests never trigger `loadProfile(authUsername)` and would render the spinner forever. New guard: `if (caps.canViewOwnProfile && authUsername && profile === null) loadProfile(authUsername);`.
- Extract the inline `menuItems` ternary (`profile.tsx:129-141`) into `buildMenu(caps, handlers): RadialMenuItem[]` in `mobile/components/profile/menu.ts`.
- Guest username sourcing: if `authUsername` is null for a guest, fall through to the existing `!authUsername` fallback screen (already renders a "complete your profile" message with a log-out button). Implementer resolves the path to a real guest username per the Deferred question above.
- Keep loading, error, and `!authUsername` fallback branches unchanged.

**Patterns to follow:**
- Existing `mobile/components/profile/useProfile.ts` (data hook) — no changes.
- `mobile/components/profile/ProfileHeader.tsx` for typing conventions.

**Test scenarios:**
- *Happy path (bug fix):* render `<ProfileScreen>` with mocked `useFeatures({auth_required: false})` + `useAuth({session: {mode: "guest"}, username: "guest-abc"})` + mocked `useProfile()` stub → asserts `<GlowUpGrid>` renders, menu lacks "Log Out" and "Sign In" labels.
- *Happy path (load-effect fires for guests):* same harness, spy on `useProfile().loadProfile` → asserts it was called with `"guest-abc"` on first render. (Regression guard for the `isAuthenticated`-gated effect.)
- *Happy path (user unchanged):* same harness with `{mode: "user"}` → asserts full menu including "Edit Profile" and "Log Out"; `loadProfile` still called.
- *Edge case:* `{auth_required: true, mode: "guest"}` (impossible at runtime but capability layer should gate) → asserts sign-in CTA rendered, `loadProfile` *not* called.
- *Edge case:* `{mode: "anon"}` → asserts sign-in CTA rendered, menu shows only "Sign In".
- *Edge case (no guest username yet):* `{mode: "guest", username: null}` → asserts the existing `!authUsername` fallback screen renders (not the spinner, not an infinite load).
- *Integration (smoke, manual):* run backend with `FEATURE_AUTH_REQUIRED=false`, mobile with `DEV_FEATURE_FOCUS=/(tabs)/profile`, confirm profile + glowups render with guest token.

**Verification:**
- `cd mobile && npx jest app/(tabs)/__tests__/profile.test.tsx && npx tsc --noEmit && npx expo lint` → green.
- Manual smoke per origin §Manual verification:
  ```
  echo "FEATURE_AUTH_REQUIRED=false" >> app/.env
  make up
  echo "DEV_FEATURE_FOCUS=/(tabs)/profile" >> mobile/.env
  cd mobile && npx expo run:ios
  ```
  Expected: profile renders for guest; menu = [Subscription, Settings]. Reverts env changes.

---

- [ ] **Unit 3: UI audit sweep — migrate remaining raw-flag reads to capabilities**

**Goal:** Every UI file outside the capabilities module and the features infrastructure consumes `useCapabilities()`, never raw `features.X`, for gating decisions. (Non-gating reads — e.g., `isLoading` — remain fine.)

**Requirements:** R2.

**Dependencies:** Unit 1.

**Files:**
- Modify: `mobile/app/_layout.tsx` — migrate the **gating/redirect** reads at lines 92, 104 (and their dep-array entries at 114-115) to `caps.requiresAuth` + `caps.canSeeOnboarding`. **Do NOT migrate** the session-bootstrap reads at lines 55-56, 74: that effect runs *before* session is ready, and `useCapabilities()` composes `useAuth()`, which would create a circular timing dependency. Keep `features.auth_required` raw there.
- Modify: `mobile/app/(tabs)/_layout.tsx` (2 raw reads at lines 218, 219; use `caps.canSeeFeed` + `caps.canUseAdvisor`)
- Modify: `mobile/components/advisor/ChatView.tsx` (2 raw reads at lines 97, 98; use `caps.canSeeFeed` + `caps.canUseAdvisor`)

**Approach:**
- Grep-verified allowlist of files that *may* read raw flags: `mobile/lib/capabilities.ts`, `mobile/lib/features-context.tsx`, `mobile/lib/features-state.ts`, `mobile/constants/features.ts`, `mobile/lib/session.ts` (comment-only; no code change), and **the `AuthGuard` session-bootstrap effect in `mobile/app/_layout.tsx`** (session initialization runs before `useAuth()` is ready; treated as infrastructure, not gating). Document this exception inline near lines 55-74 with a short comment explaining why.
- `session.ts:4` references `features.auth_required` in a comment explaining why `SessionMode` exists — leave comment as-is; the comment's point is still valid.
- For each modified file: swap `const { features } = useFeatures();` for `const caps = useCapabilities();` + replace each `features.X` gating read with the matching capability. Keep `useFeatures().isLoading` where needed for splash/loading state. In `_layout.tsx`, both `useFeatures()` *and* `useCapabilities()` will be consumed — the former for session bootstrap, the latter for the redirect effect.

**Patterns to follow:**
- Pattern established in Unit 2's `profile.tsx` rewrite.

**Test scenarios:**
- *Integration:* run `cd mobile && npx tsc --noEmit && npx expo lint` → green after all three files migrated.
- *Coverage grep (manual gate):* `rg 'features\.(auth_required|social_enabled|advisor_enabled|share_enabled|onboarding_enabled)' mobile --type ts --type tsx` outside the allowlist → 0 matches. Allowlist for this grep: `mobile/lib/capabilities.ts`, `mobile/lib/features-context.tsx`, `mobile/lib/features-state.ts`, `mobile/constants/features.ts`, `mobile/lib/session.ts` (comment only), and the `AuthGuard` session-bootstrap block in `mobile/app/_layout.tsx` (see Approach). (CI enforcement is not added this iteration — see Risks.)
- *No behavioral regression:* existing tab bar / advisor / auth-guard integration tests (if present) continue to pass. If no tests cover these paths, rely on `tsc` + manual smoke of the app running end-to-end (cold start with default flags).

**Verification:**
- `cd mobile && npx tsc --noEmit && npx expo lint` → green.
- Manual grep (above) → empty.
- Boot app with default `auth_required=true, social_enabled=false, advisor_enabled=true` → tab bar shows expected tabs; AuthGuard routes correctly.

---

- [ ] **Unit 4: Backend router audit + coverage test + mis-gated route fix**

**Goal:** Every router expected to be flag-gated carries `Depends(require_app_feature("<flag>"))` at the router level, enforced by a CI test. Mis-gated `/users/{username}/profile` route corrected.

**Requirements:** R1 (via mis-gated fix), R3.

**Dependencies:** None (independent of mobile units).

**Files:**
- Modify: `app/api/users.py` (remove `Depends(require_app_feature("social_enabled"))` from the `GET /users/{username}/profile` route at line 170; profile lookup is identity, not social)
- Create: `tests/test_feature_flag_coverage.py`
- Verify (read-only, expected no changes): `app/api/posts.py`, `app/api/social.py`, `app/api/blocks.py`, `app/api/advisor.py`, `app/api/main.py`
- Verify (read-only): `app/advisor/nudge_scheduler.py` — confirm entry-point `advisor_enabled` check exists

**Approach:**
- **Coverage test design:** `FLAG_GATED_ROUTERS = {"app/api/posts.py": "social_enabled", "app/api/social.py": "social_enabled", "app/api/blocks.py": "social_enabled", "app/api/advisor.py": "advisor_enabled"}`. For each file, read source, regex-find the `APIRouter(` constructor, assert `Depends(require_app_feature("<expected_flag>"))` appears in its `dependencies=` list.
- Ungated routers (`auth`, `health`, `features`, `users`, `uploads`, `glowup`, `webhooks`, `admin`, `user_consent`, `refund`, `entitlement`, `jobs`, `public`) stay off-list by design.
- **`users.py` fix:** remove line 170's `Depends(require_app_feature("social_enabled"))` from `GET /users/{username}/profile`. Rationale: the route returns public identity info (username, avatar, stats). `get_user_or_guest` already governs auth context; tying this to the social feature breaks R1's guest-profile path when `social_enabled=false`.
- Audit pass during implementation: grep `@router.` in `FLAG_GATED_ROUTERS` files for any per-route dependency that would mask a missing router-level dep. Consolidate if found.
- `nudge_scheduler` check: confirm `app/advisor/nudge_scheduler.py` short-circuits when `advisor_enabled=false`. If not, add guard at scheduler entry.

**Patterns to follow:**
- `tests/test_features.py` for pytest scaffolding (fixtures, test client).
- Existing router-level `Depends(...)` declarations in `app/api/posts.py:46` and `app/api/social.py:47` as reference shape.

**Test scenarios:**
- *Happy path:* coverage test passes on the unmodified `FLAG_GATED_ROUTERS` — all four routers carry the expected dep.
- *Regression:* temporarily rename `"social_enabled"` to `"SOCIAL"` in `app/api/posts.py` inside a test monkeypatch → coverage test fails with file + expected-flag + found-shape in message. Revert after assertion.
- *Happy path (users.py fix):* with `auth_required=false, social_enabled=false`, a guest-token request to `GET /v1/users/{username}/profile` → 200 + body. (Regression test in `tests/test_features.py` or `tests/test_users.py`.)
- *Regression:* with `social_enabled=false`, `GET /v1/posts/feed` → still 403 `FEATURE_DISABLED` (other social routes unaffected).
- *Typo guard:* `require_app_feature("sozial_enabled")` inside any monitored router → coverage test fails (mismatch), and in prod `is_enabled()` raises `ValueError`.

**Verification:**
- `make test -- tests/test_feature_flag_coverage.py tests/test_features.py` → green.
- `make lint` → green.
- Manual: `curl -H "X-Guest-Token: ..." http://localhost:8000/v1/users/<guest-username>/profile` with `FEATURE_SOCIAL_ENABLED=false, FEATURE_AUTH_REQUIRED=false` → 200 JSON.

---

- [ ] **Unit 5: Docs — add-a-flag playbook + convention**

**Goal:** Onboard future contributors to the "capability + gate + parity test" workflow.

**Requirements:** R6.

**Dependencies:** Units 1-4 (docs describe the landed shape).

**Files:**
- Create: `app/features/README.md`
- Modify: `CLAUDE.md`

**Approach:**
- `app/features/README.md`: 3-step guide.
  1. Add the field to `FeatureFlags` in `app/features/__init__.py` + config default in `app/config/__init__.py` + `app/.env.example`.
  2. Add the same field to `FeatureFlags` interface in `mobile/constants/features.ts`, update `PROD_DEFAULT_FEATURES`, optionally add `DEV_SHORT_NAME_TO_FLAG` entry.
  3. If the flag gates UI, add a capability in `mobile/lib/capabilities.ts` + matrix row in `capabilities.test.ts`. If it gates a backend router, add `Depends(require_app_feature("<name>"))` + one line in `FLAG_GATED_ROUTERS`. Commit atomically — the parity test will fail CI on asymmetric drift.
- `CLAUDE.md`: add one line under §Conventions — *"Feature gating: use `useCapabilities()` in UI, `require_app_feature()` on backend routers. Never read raw flags for gating."*

**Test scenarios:**
- *Test expectation: none — docs only. Verified by reviewer reading the file.*

**Verification:**
- README renders cleanly in GitHub markdown preview.
- `CLAUDE.md` line is alphabetical/topical fit with sibling conventions.

## System-Wide Impact

- **Interaction graph:**
  - `FeaturesProvider` → `useFeatures()` → `useCapabilities()` → UI.
  - `AuthProvider` → `useAuth()` → `useCapabilities()`.
  - Both providers must mount before any screen renders (already true via `mobile/app/_layout.tsx` provider composition).
- **Error propagation:**
  - `GET /v1/features` failure → `PROD_DEFAULT_FEATURES` fallback (existing). Capabilities then derive against strictest defaults — users see the most-gated UI, which is safe.
  - Backend `FEATURE_DISABLED` (403) should not be reached if capability logic matches the backend. Drift surfaces as a generic error toast — treated as a bug, not a UX concern (per origin §Error Handling).
- **State lifecycle risks:**
  - Capability memoization keyed on `(features, session.mode)` — a session-mode transition (e.g., `anon → guest` after guest-token issuance) must re-render capability consumers. React context already handles this.
  - Dev overrides via `DEV_DISABLE_FEATURES` apply before capabilities derive — behavior is consistent with backend-flag-off.
- **API surface parity:**
  - `/v1/features` wire format unchanged.
  - `/v1/users/{username}/profile` loses its `social_enabled` gate — public/semi-public endpoint is now accessible to guests (and anon) when `auth_required=false`. No PII exposure: response already contained only public profile fields. Rate limiting remains as-is.
- **Integration coverage:**
  - Coverage test (`test_feature_flag_coverage.py`) is the cross-layer integration gate for "new router must be gated if social/advisor-adjacent".
  - Parity test (`test_feature_registry_parity.py`) is the cross-language integration gate for flag registry symmetry.
  - `capabilities.test.ts` is the cross-module integration gate for "correct capability for every `(session, features)` combo".
- **Unchanged invariants:**
  - `FeatureFlags` pydantic model fields and ordering.
  - `GET /v1/features` wire format and cache semantics.
  - `require_app_feature()` signature and 403 payload shape.
  - Dev-override mechanism (`DEV_DISABLE_FEATURES`, `DEV_SHORT_NAME_TO_FLAG`).
  - Guest-token issuance flow (`POST /v1/guest/token`) and `get_user_or_guest` dep.
  - Per-tier `require_feature` (entitlement gating) — separate system, unchanged.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Parity test's regex-based TypeScript parsing is brittle; refactoring `FeatureFlags` interface formatting (e.g., switching to `type FeatureFlags = {...}`) silently breaks it | Unit 1 test must cover both the happy-path regex *and* a negative "malformed interface body" case; document the expected source shape in a comment above the regex; if formatting freezes become a source of churn, upgrade to a tiny TS-to-JSON shim under `scripts/`. |
| `canEditProfile=false` for guests surprises them after their first edit attempt | Menu already omits `Edit Profile` for guests, so there's no UI entry point. No mitigation needed unless the design shifts — explicitly called out as Scope Boundary. |
| Removing `social_enabled` dep from `/users/{username}/profile` could be seen as scope creep | Surfaced explicitly in Key Technical Decisions + Open Questions + Unit 4 approach. Without it, R1 is unreachable when `social_enabled=false`. Reviewer can verify via manual curl in Unit 4 verification. |
| Grep-based "no raw flags" enforcement is out-of-band (not CI-enforced this iteration) | Documented in Unit 3 verification as a manual grep; if drift recurs, a follow-up plan can wire a CI step. Reviewers also catch via `useFeatures()` appearances in PR diffs. |
| Coverage-test allowlist gets out of date when a new router arrives | The allowlist itself is the declaration — new gated routers require an allowlist update, which is visible in review. Undocumented ungated routers remain a known blind spot (same as today); accepted. |
| `FLAG_GATED_ROUTERS` test reads the router-declaration string statically; a future refactor to programmatic router building breaks the regex | Test message explicitly cites the expected source shape. Refactors to router construction must update the coverage test or drop the file from the allowlist with justification. |
| Guest-profile path stresses `useProfile()` with a guest token in a way that may not have been exercised | Unit 2 manual smoke covers the cold path end-to-end. If `useProfile()` assumes a user JWT anywhere internally, Unit 2 surfaces it before merge. |

## Documentation / Operational Notes

- **Rollout:** No migration needed. Mobile ships capability layer + fixed profile; backend ships coverage test + mis-gate fix. Parity test is CI-only.
- **Monitoring:** No new metrics. Existing `FEATURE_DISABLED` 403 rate is the drift signal — should drop toward zero after Unit 3.
- **Dev setup:** `DEV_FEATURE_FOCUS` + `DEV_DISABLE_FEATURES` remain the dev toggles. No new env vars.
- **Env-example sync:** No new env vars this plan. If Unit 4 audit surfaces a missing flag, follow origin doc's 3-step add-a-flag process before proceeding.

## Sources & References

- **Origin document:** [docs/superpowers/specs/2026-04-15-feature-flags-redesign-design.md](../superpowers/specs/2026-04-15-feature-flags-redesign-design.md)
- **Backend source of truth:** `app/features/__init__.py`, `app/api/deps.py:477-503`
- **Mobile source of truth:** `mobile/constants/features.ts`, `mobile/lib/features-context.tsx`, `mobile/lib/session.ts`
- **PR2 handoff context:** Memoria `feature_flags_pr2_handoff.md`
- **Related routes (gated today):** `app/api/posts.py:46`, `app/api/social.py:47`, `app/api/blocks.py:19`, `app/api/advisor.py:52`
- **Mis-gated route to fix:** `app/api/users.py:167-170`
- **Raw-flag call sites to migrate:** `mobile/app/_layout.tsx:55,91,103`, `mobile/app/(tabs)/_layout.tsx:218,219`, `mobile/components/advisor/ChatView.tsx:97,98`
