/**
 * Feature flag context. Fetches `GET /v1/features` once on cold start,
 * applies dev overrides, and exposes the resolved registry via `useFeatures()`.
 *
 * Fetch uses a raw `fetch` (not `apiFetch`) because this provider mounts
 * before auth/headers are wired — the endpoint is public.
 */
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { API_BASE_URL } from "../constants/config";
import {
  FEATURES_ENDPOINT,
  PROD_DEFAULT_FEATURES,
  applyDevOverrides,
  type FeatureFlags,
} from "../constants/features";

interface FeaturesContextValue {
  features: FeatureFlags;
  isLoading: boolean;
}

const DEFAULT_VALUE: FeaturesContextValue = {
  features: applyDevOverrides(PROD_DEFAULT_FEATURES),
  isLoading: true,
};

const FeaturesContext = createContext<FeaturesContextValue>(DEFAULT_VALUE);

export function FeaturesProvider({ children }: { children: ReactNode }) {
  const [features, setFeatures] = useState<FeatureFlags>(
    DEFAULT_VALUE.features,
  );
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function fetchFeatures() {
      try {
        const resp = await fetch(`${API_BASE_URL}${FEATURES_ENDPOINT}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = (await resp.json()) as FeatureFlags;
        if (!cancelled) setFeatures(applyDevOverrides(data));
      } catch (err) {
        if (__DEV__) {
          console.warn("Feature flags fetch failed, using defaults:", err);
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    fetchFeatures();
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo(() => ({ features, isLoading }), [features, isLoading]);

  return (
    <FeaturesContext.Provider value={value}>
      {children}
    </FeaturesContext.Provider>
  );
}

export function useFeatures(): FeaturesContextValue {
  return useContext(FeaturesContext);
}
