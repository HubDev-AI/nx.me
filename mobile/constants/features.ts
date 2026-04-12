/**
 * Feature flag registry — mirrors the backend `GET /v1/features` wire format.
 *
 * Mobile fetches flags once per cold start; on failure falls back to
 * PROD_DEFAULT_FEATURES so the app still boots with sane production defaults.
 * Dev builds can force-disable flags via `DEV_DISABLE_FEATURES=auth,social,...`
 * in `mobile/.env` — the list is merged on top of the backend response.
 */
import Constants from "expo-constants";

const extra = Constants.expoConfig?.extra ?? {};

export interface FeatureFlags {
  auth_required: boolean;
  social_enabled: boolean;
  share_enabled: boolean;
  onboarding_enabled: boolean;
  advisor_enabled: boolean;
}

export const PROD_DEFAULT_FEATURES: FeatureFlags = {
  auth_required: true,
  social_enabled: false,
  share_enabled: true,
  onboarding_enabled: true,
  advisor_enabled: true,
};

export const FEATURES_ENDPOINT = "/v1/features";

/**
 * Short-name overrides applied in dev. `auth` → `auth_required=false`, etc.
 * Unknown names are ignored (noop) so typos don't break the app.
 */
const DEV_SHORT_NAME_OVERRIDES: Record<
  string,
  (f: FeatureFlags) => FeatureFlags
> = {
  auth: (f) => ({ ...f, auth_required: false }),
  social: (f) => ({ ...f, social_enabled: false }),
  share: (f) => ({ ...f, share_enabled: false }),
  onboarding: (f) => ({ ...f, onboarding_enabled: false }),
  advisor: (f) => ({ ...f, advisor_enabled: false }),
};

function parseDevDisableList(raw: string): string[] {
  return raw
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
}

export const DEV_DISABLE_FEATURES: readonly string[] = __DEV__
  ? parseDevDisableList((extra.devDisableFeatures as string) ?? "")
  : [];

/** Apply dev-only overrides on top of the backend-returned registry. */
export function applyDevOverrides(features: FeatureFlags): FeatureFlags {
  if (!__DEV__ || DEV_DISABLE_FEATURES.length === 0) return features;
  let next = features;
  for (const name of DEV_DISABLE_FEATURES) {
    const fn = DEV_SHORT_NAME_OVERRIDES[name];
    if (fn) next = fn(next);
  }
  return next;
}
