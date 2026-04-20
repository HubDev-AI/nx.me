/**
 * Feature flag registry — mirrors the backend `GET /v1/features` wire format.
 *
 * Mobile fetches flags once per cold start; on failure falls back to
 * PROD_DEFAULT_FEATURES so the app still boots with sane production defaults.
 * Dev builds can force-disable flags via `DEV_DISABLE_FEATURES=social,share,...`
 * in `mobile/.env` — the list is merged on top of the backend response.
 */
import Constants from "expo-constants";

const extra = Constants.expoConfig?.extra ?? {};

export interface FeatureFlags {
  social_enabled: boolean;
  share_enabled: boolean;
  onboarding_enabled: boolean;
  advisor_enabled: boolean;
}

export const PROD_DEFAULT_FEATURES: FeatureFlags = {
  social_enabled: false,
  share_enabled: true,
  onboarding_enabled: true,
  advisor_enabled: true,
};

export const FEATURES_ENDPOINT = "/v1/features";

/**
 * Short-name → flag-field mapping used by DEV_DISABLE_FEATURES.
 * Unknown names are ignored (noop) so typos don't break the app.
 */
const DEV_SHORT_NAME_TO_FLAG: Record<string, keyof FeatureFlags> = {
  social: "social_enabled",
  share: "share_enabled",
  onboarding: "onboarding_enabled",
  advisor: "advisor_enabled",
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
  const next = { ...features };
  for (const name of DEV_DISABLE_FEATURES) {
    const flag = DEV_SHORT_NAME_TO_FLAG[name];
    if (flag) next[flag] = false;
  }
  return next;
}
