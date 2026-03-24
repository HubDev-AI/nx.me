/**
 * Fetches the list of enabled auth providers from the backend.
 *
 * GET /auth/providers returns { providers: string[] }.
 * The mobile UI uses this to decide which login buttons to render.
 */
import { useState, useEffect, useCallback } from "react";

import { AUTH_ENDPOINTS } from "../constants/config";
import type { AuthProvider } from "../constants/config";
import { API_BASE_URL } from "../constants/config";

interface UseEnabledProvidersReturn {
  providers: AuthProvider[];
  isLoading: boolean;
  error: string | null;
  retry: () => void;
}

export function useEnabledProviders(): UseEnabledProvidersReturn {
  const [providers, setProviders] = useState<AuthProvider[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  const retry = useCallback(() => {
    setError(null);
    setIsLoading(true);
    setAttempt((prev) => prev + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function fetchProviders() {
      try {
        // Raw fetch (not apiFetch) — this runs before auth context is initialized,
        // and the endpoint requires no authentication.
        const resp = await fetch(`${API_BASE_URL}${AUTH_ENDPOINTS.PROVIDERS}`);
        if (!resp.ok) {
          throw new Error(`HTTP ${resp.status}`);
        }
        const data = (await resp.json()) as { providers: AuthProvider[] };
        if (!cancelled) {
          setProviders(data.providers);
          setError(null);
        }
      } catch {
        if (!cancelled) {
          setProviders([]);
          setError("Unable to load login options. Check your connection.");
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    fetchProviders();
    return () => { cancelled = true; };
  }, [attempt]);

  return { providers, isLoading, error, retry };
}
