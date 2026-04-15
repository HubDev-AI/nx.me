# Feature Flags — Redesign (Usage + Ergonomics)

**Date:** 2026-04-15
**Status:** Design approved (pending spec review)
**Scope:** Fix usage and ergonomics of the existing feature-flag infrastructure. No infrastructure changes.

---

## Problem

The current feature-flag system is technically complete but has three usage-level defects:

1. **Guest profile is broken when `auth_required=false`.** `profile.tsx` gates on `session.isUser` alone, ignoring the `auth_required` flag. A guest with a valid guest token sees the sign-in CTA instead of their own profile and glowups.
2. **No centralized rule for "feature X is available to session Y".** Every screen inlines its own boolean of `(flag × session)`. Drift and inconsistency are inevitable.
3. **Adding a new flag touches six files.** Pydantic model, `get_features()`, config, mobile interface, `PROD_DEFAULT_FEATURES`, `DEV_SHORT_NAME_TO_FLAG`. Drift between backend and mobile is uncaught.
4. **No mechanism to ensure every future feature is flag-gated.** Ungated routers and UI features go unnoticed.

## Goals

- Fix the profile bug so guests see their profile and glowups when `auth_required=false`.
- Introduce a single capability layer in the mobile app that derives semantic booleans from `(features × session)`.
- Keep backend-gating via `require_app_feature()` and enforce its coverage via a test.
- Prevent flag-registry drift between backend and mobile via a parity test.
- Document the 3-step process for adding a new flag.

## Non-Goals

- No codegen, no remote-config service, no per-user flag overrides.
- No capability layer for auth providers — `useEnabledProviders` stays separate.
- No changes to `FeatureFlags` pydantic model unless a new flag is added during the audit.
- No changes to guest-token semantics.

---

## Architecture

```
Backend config (.env)
      │
      ▼
[app/features/__init__.py]  ← source of truth: FeatureFlags pydantic model + get_features()
      │
      ├── GET /v1/features  ← public wire endpoint
      │        │
      │        ▼
      │   [mobile/constants/features.ts]  ← mirror: FeatureFlags TS interface
      │        │
      │        ▼
      │   [FeaturesProvider] ← cold-start fetch + dev overrides
      │        │
      │        ▼
      │   [useCapabilities()] ← derived semantic booleans (features × session)
      │        │
      │        ▼
      │   UI components consume capabilities, never raw flags
      │
      └── require_app_feature("name")  ← FastAPI router-level dep
             │
             ▼
             Flag-gated routers declare the dep in their router prefix
```

### Four invariants

1. **UI never reads raw flags for gating.** `useCapabilities()` only. Raw `useFeatures()` reads allowed only for loading state and inside `capabilities.ts` itself.
2. **Backend flag-gated routers use `require_app_feature` at the router level**, not per-route — so adding a new route to a gated router is automatic.
3. **Registries stay in lockstep** via `tests/test_feature_registry_parity.py`.
4. **Router coverage** is enforced via `tests/test_feature_flag_coverage.py` with an explicit `FLAG_GATED_ROUTERS` allowlist.

### Guest profile fix (the core bug)

New capability:

```
canViewOwnProfile = session.isUser || (session.isGuest && !features.auth_required)
```

`profile.tsx` replaces `if (!isAuthenticated)` with `if (!canViewOwnProfile)`. Guests with a valid guest token and `auth_required=false` render the full profile, backed by `useProfile()` hitting `/v1/users/{username}` with the guest token (already supported by `get_user_or_guest`).

---

## Components & Files

### New files

1. **`mobile/lib/capabilities.ts`** — single hook with all capability derivations. ~80 LOC.

    ```ts
    export interface Capabilities {
      canViewOwnProfile: boolean;
      canEditProfile: boolean;
      canSignOut: boolean;
      canSignIn: boolean;
      canSeeFeed: boolean;
      canUseAdvisor: boolean;
      canShareGlowup: boolean;
      canSeeOnboarding: boolean;
      canSubscribe: boolean;
      canReact: boolean;
      requiresAuth: boolean; // raw passthrough for flow-level gating
    }

    export function useCapabilities(): Capabilities;
    ```

2. **`mobile/lib/capabilities.test.ts`** — matrix test covering (session mode × features subset).

3. **`tests/test_feature_registry_parity.py`** — regex-extracts `FeatureFlags` interface fields from `mobile/constants/features.ts` and asserts equal set to `app.features.FeatureFlags.model_fields` keys.

4. **`tests/test_feature_flag_coverage.py`** — walks `app/api/*.py`, greps router declaration for `Depends(require_app_feature("<name>"))`. Allowlist `FLAG_GATED_ROUTERS` maps router file → required flag.

### Modified files (estimated)

**Mobile:**
- `mobile/app/(tabs)/profile.tsx` — replace `isAuthenticated` check with `canViewOwnProfile`. Extract `buildMenu()` helper driven by capabilities. Guest branch renders full profile.
- `mobile/app/(tabs)/_layout.tsx` — consume `canSeeFeed`, `canUseAdvisor` from capabilities.
- `mobile/app/_layout.tsx` — use `requiresAuth` in `AuthGuard` redirect logic.
- `mobile/components/advisor/ChatView.tsx` — swap `features.advisor_enabled` → `canUseAdvisor`.
- `mobile/app/(tabs)/create.tsx` — audit + swap if raw flags read.
- `mobile/lib/session.ts` — keep as-is; guest-token provisioning on `auth_required=false` is internal session logic, not a gating decision. Add clarifying comment.

**Backend:**
- `app/api/posts.py`, `app/api/social.py`, `app/api/blocks.py` — verify router-level `Depends(require_app_feature("social_enabled"))`. Add if missing.
- `app/api/advisor.py` — verify router-level `Depends(require_app_feature("advisor_enabled"))`.
- `app/advisor/nudge_scheduler.py` — verify advisor flag check at entry.
- `app/main.py` — no change; coverage test reads router mount points from here.

**Docs:**
- `app/features/README.md` — 3-step "how to add a flag" guide.
- `CLAUDE.md` — add a convention line under "Conventions".

### Files NOT touched

- `app/features/__init__.py`
- `app/api/features.py`
- `mobile/lib/features-context.tsx`
- `mobile/lib/features-state.ts`
- `mobile/constants/features.ts` (unless adding a new flag)

---

## Data Flow

### Cold-start

```
App mount
 ├─ FeaturesProvider mounts
 │    └─ fetch(GET /v1/features)
 │         └─ applyDevOverrides(data)
 │              └─ setFeatures(resolved) (context)
 │              └─ setAuthRequired(resolved.auth_required) (module cache)
 └─ AuthProvider mounts in parallel
      └─ hydrate session from storage (user JWT / guest token / anon)

App ready → screens mount → useCapabilities() reads (features, session)
```

### Profile screen, reshaped

Before:
```ts
const isAuthenticated = session.isUser;
if (!isAuthenticated) return <SignInCTA />;
```

After:
```ts
const caps = useCapabilities();
if (!caps.canViewOwnProfile) return <SignInCTA />;

return <FullProfile
  editable={caps.canEditProfile}
  menuItems={buildMenu(caps)}
/>;
```

### Menu derivation

```ts
function buildMenu(caps: Capabilities): RadialMenuItem[] {
  const items: RadialMenuItem[] = [];
  if (caps.canEditProfile) items.push(editProfileItem);
  if (caps.canSubscribe)   items.push(subscriptionItem);
  items.push(settingsItem);                    // always shown
  if (caps.canSignOut)     items.push(logOutItem);
  if (caps.canSignIn)      items.push(signInItem);
  return items;
}
```

### Result matrix

| Session \ auth_required | true | false |
|---|---|---|
| **anon** | Sign-in CTA | Sign-in CTA (guests only exist after guest-token issuance) |
| **guest** | N/A — guest tokens not issued when `auth_required=true` | Full profile, menu = [Edit*, Subscription, Settings] |
| **user** | Full profile, menu = [Edit, Subscription, Settings, Log Out] | Same |

\* `canEditProfile=false` for guests in this iteration; editing a guest account has no identity target. Can relax later.

---

## Error Handling

### Mobile

| Scenario | Behavior |
|---|---|
| `GET /v1/features` fails on cold start | Falls back to `PROD_DEFAULT_FEATURES` (already implemented). Capabilities derive from safe defaults → strictest gating. |
| Backend returns 403 `FEATURE_DISABLED` | UI shouldn't reach the call if capability logic matches backend. If it does, generic error toast surfaces — drift is a bug, not a UX concern. |
| Session changes mid-session | `useCapabilities()` recomputes on next render via context subscription. |
| `DEV_DISABLE_FEATURES=auth` with a real JWT in storage | Dev override affects features only. User stays logged in via `isUser` branch. No inconsistency. |

### Backend

| Scenario | Behavior |
|---|---|
| Gated route hit when flag off | 403 `FEATURE_DISABLED` (existing). |
| Guest hits a gated route that also needs real auth | Two deps stack: `require_app_feature` passes → `get_current_user` rejects. Clean separation. |
| Typo in `require_app_feature("sozial_enabled")` | `is_enabled()` raises `ValueError` on unknown name (existing). Caught at test time by coverage test if gating is on a watched router. |

---

## Testing

### New tests

1. **`tests/test_feature_registry_parity.py`**
    - Reads `mobile/constants/features.ts`.
    - Regex-extracts the `FeatureFlags` interface body.
    - Parses `<name>: boolean;` lines into a set.
    - Asserts `set == set(FeatureFlags.model_fields.keys())`.
    - Fails CI on drift in either direction.

2. **`tests/test_feature_flag_coverage.py`**
    - `FLAG_GATED_ROUTERS = {"posts": "social_enabled", "social": "social_enabled", "blocks": "social_enabled", "advisor": "advisor_enabled"}`.
    - For each router file in the allowlist, greps for `Depends(require_app_feature("<expected>"))` in the router declaration.
    - Asserts present; fails CI on missing gate.
    - Ungated routers (auth, health, features, users, uploads, generations, payments, subscription) stay off-list by design.

3. **`mobile/lib/capabilities.test.ts`**
    - Matrix: for each `(sessionMode, flagsSubset)` combo, assert derived capabilities.
    - Explicit row: `{ isGuest: true, auth_required: false }` → `canViewOwnProfile=true`.
    - Explicit row: `{ isUser: false, isGuest: true, auth_required: true }` → `canViewOwnProfile=false` (though this state shouldn't happen at runtime; capability layer is pure).

### Updated tests

- `tests/test_features.py` — add case for `auth_required=false` with guest token → profile/glowup endpoints accept `X-Guest-Token`.
- `mobile/app/(tabs)/__tests__/profile.test.tsx` (if exists, else new) — render profile with `{ features: { auth_required: false }, session: { mode: "guest" } }` → assert grid renders, menu lacks Log Out and Sign In.

### Manual verification

```
# Terminal 1 — backend with auth optional
echo "FEATURE_AUTH_REQUIRED=false" >> app/.env
make up

# Terminal 2 — mobile, land directly on profile as guest
echo "DEV_FEATURE_FOCUS=/(tabs)/profile" >> mobile/.env
cd mobile && npx expo run:ios
# Expected: profile loads with guest avatar + glowups grid; menu has no Log Out / Sign In.

# Cleanup
# Remove DEV_FEATURE_FOCUS and FEATURE_AUTH_REQUIRED overrides from .env files.
```

---

## Implementation Phasing

Five phases, each ≤5 files (per `CLAUDE.md` phased-execution rule). Each phase ends with verification + commit.

### Phase 1 — Capability hook + parity test (foundation)
- Create `mobile/lib/capabilities.ts` with full capability set.
- Create `mobile/lib/capabilities.test.ts` (matrix).
- Create `tests/test_feature_registry_parity.py`.
- Verify: `cd mobile && npx expo lint && npx tsc --noEmit` + `make test`.
- Commit.

### Phase 2 — Profile fix (user-reported bug)
- Rewrite `mobile/app/(tabs)/profile.tsx` to use capabilities.
- Extract `buildMenu()` helper (same file or `mobile/components/profile/menu.ts`).
- Add `mobile/app/(tabs)/__tests__/profile.test.tsx` guest-profile render case.
- Verify: lint + tsc + manual smoke with `FEATURE_AUTH_REQUIRED=false`, `DEV_FEATURE_FOCUS=/(tabs)/profile`.
- Commit.

### Phase 3 — UI audit sweep
- Grep every `features\.(social_enabled|advisor_enabled|share_enabled|onboarding_enabled|auth_required)` outside the allowlist (`capabilities.ts`, `features-context.tsx`, `features-state.ts`, `session.ts`).
- Replace with `useCapabilities()` reads in `_layout.tsx` (tabs), `_layout.tsx` (root + AuthGuard), `ChatView.tsx`, `create.tsx`, others.
- Verify: lint + tsc + `npx expo lint`.
- Commit.

### Phase 4 — Backend router audit + coverage test
- Create `tests/test_feature_flag_coverage.py` with `FLAG_GATED_ROUTERS` allowlist.
- Run it; fix any router missing a gate.
- Verify: `make lint && make test`.
- Commit.

### Phase 5 — Docs
- `app/features/README.md` — 3-step add-a-flag guide.
- `CLAUDE.md` — "Feature gating: use `useCapabilities()` in UI, `require_app_feature()` on backend routers. Never read raw flags for gating."
- Commit.

---

## Success Criteria

- [ ] `FEATURE_AUTH_REQUIRED=false` + guest session → profile screen renders full profile + glowups grid (manual verification passes).
- [ ] Every UI file outside the capabilities module and the features infrastructure uses `useCapabilities()` (grep check in CI).
- [ ] `tests/test_feature_registry_parity.py` passes; adding a flag to either side without the other fails CI.
- [ ] `tests/test_feature_flag_coverage.py` passes; every router in `FLAG_GATED_ROUTERS` has the required `require_app_feature` dep.
- [ ] `capabilities.test.ts` matrix covers every `(session, features)` combination exercised in production.
- [ ] `app/features/README.md` documents the 3-step add-a-flag process.
- [ ] `CLAUDE.md` records the "never read raw flags" convention.

## Open Questions

None. All clarifying questions resolved during brainstorming.

## Appendix — Flag → Capability Mapping

| Raw flag | Capabilities that depend on it |
|---|---|
| `auth_required` | `canViewOwnProfile` (with `session.isGuest`), `canSignIn` (forced when true), `requiresAuth` |
| `social_enabled` | `canSeeFeed`, `canReact` |
| `advisor_enabled` | `canUseAdvisor` |
| `share_enabled` | `canShareGlowup` |
| `onboarding_enabled` | `canSeeOnboarding` |
| (session only) | `canEditProfile`, `canSignOut` |
| (stub, always true) | `canSubscribe` (until premium tiering is added) |
