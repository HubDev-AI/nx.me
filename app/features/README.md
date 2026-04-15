# Feature Flags

App-wide on/off toggles backed by env vars, exposed to the mobile app via
`GET /v1/features`, and enforced on both ends of the wire.

## Architecture

```
app/.env  →  app/config/__init__.py  →  app/features/__init__.py
                                              │
                                              ├── GET /v1/features  →  mobile/constants/features.ts
                                              │                            │
                                              │                            ▼
                                              │                       useCapabilities()  →  UI
                                              │
                                              └── require_app_feature("name")  →  router-level dep
```

**Source of truth:** `FeatureFlags` pydantic model in this package. Every
flag is a required `bool` field — there are no defaults at the model
layer; defaults live in `app/config/__init__.py` and `app/.env.example`.

**Two enforcement gates:**
- **Backend:** `require_app_feature("name")` returns 403 `FEATURE_DISABLED`
  when the flag is off. Apply at the `APIRouter(...)` level, not per-route,
  so adding a route to a gated router automatically inherits the gate.
- **Mobile:** UI never reads raw `features.X` for gating — call
  `useCapabilities()` from `mobile/lib/capabilities.ts` and consume the
  derived semantic boolean (e.g. `caps.canSeeFeed`).

**Two CI gates** keep the system honest:
- `tests/test_feature_registry_parity.py` — backend `FeatureFlags` and
  mobile `FeatureFlags` interfaces must declare the same field set.
- `tests/test_feature_flag_coverage.py` — every router in
  `FLAG_GATED_ROUTERS` must carry the right `require_app_feature` dep, and
  every file in `app/api/` must be in either `FLAG_GATED_ROUTERS` or the
  ungated allowlist.

## Adding a new flag

Three steps. Each step has a CI gate that fails if you skip the next step,
so you can land them as one atomic commit.

### 1. Backend

- Add the field to `FeatureFlags` in `app/features/__init__.py`.
- Add the matching `FEATURE_<NAME>` setting in `app/config/__init__.py`.
- Plumb the read into `get_features()`.
- Add the env entry to `app/.env.example`.

If the flag gates a router:

- Add `Depends(require_app_feature("<name>"))` to the
  `APIRouter(prefix=..., dependencies=[...])` constructor.
- Add the file → flag mapping to `FLAG_GATED_ROUTERS` in
  `tests/test_feature_flag_coverage.py`.

### 2. Mobile

- Mirror the field in the `FeatureFlags` interface in
  `mobile/constants/features.ts`.
- Update `PROD_DEFAULT_FEATURES` with the production default.
- Optionally add a `DEV_DISABLE_FEATURES` short-name in
  `DEV_SHORT_NAME_TO_FLAG`.

### 3. Capability (only if the flag gates UI)

- Add the derived capability to the `Capabilities` interface in
  `mobile/lib/capabilities.ts` and to the `useCapabilities()` hook body.
- Add a row to `mobile/lib/capabilities.test.ts` covering the new
  capability across the relevant `(session × flag)` combinations.
- Consume `caps.<newCapability>` in UI — never `features.<flag>` directly.

### Verification

```bash
make test            # registry parity + coverage tests must pass
make lint            # ruff
cd mobile && npx jest && npx tsc --noEmit && npx expo lint
```

If `tests/test_feature_registry_parity.py` fails, the backend and mobile
registries are out of sync — finish step 2. If
`tests/test_feature_flag_coverage.py` fails, you added a router but
forgot the dep or the allowlist entry — finish step 1.

## Dev overrides

`mobile/.env`:

```
DEV_DISABLE_FEATURES=auth,social
```

Comma-separated short names from `DEV_SHORT_NAME_TO_FLAG`. Applied in
`applyDevOverrides()` after the backend response, before capabilities
derive. Production builds ignore the env var (guarded by `__DEV__`).

Backend overrides are environment-driven — set `FEATURE_<NAME>=false` in
`app/.env`.

## Existing flags

| Flag                  | Off-state behavior                                |
| --------------------- | ------------------------------------------------- |
| `auth_required`       | Mobile provisions guest tokens; UI accepts them.  |
| `social_enabled`      | Hides feed/reactions/blocks; gates social routes. |
| `share_enabled`       | Hides share-glowup CTA.                           |
| `onboarding_enabled`  | Skips onboarding flow on first sign-in.           |
| `advisor_enabled`     | Hides advisor tab; nudge worker no-ops.           |

## Why this shape

- **No codegen** — both registries are hand-maintained, parity guaranteed
  by a CI test instead of generated code. Keeps the wire format readable.
- **No remote-config service** — flags are env-driven, so deploys flip
  them. Removes a runtime dependency.
- **No per-user overrides** — entitlement gating (premium/free) is a
  separate system in `app/api/deps.py:require_feature` and
  `app/entitlement/`. App-wide flags are deployment-wide on/off only.
