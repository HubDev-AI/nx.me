import { API_BASE_URL, AUTH_ENDPOINTS } from "../constants/config";
import {
  getStoredJwt,
  storeJwt,
  getRefreshToken,
  storeRefreshToken,
  clearAllTokens,
} from "./auth";
import { getStoredGuestToken } from "./guest-session";

type RequestOptions = Omit<RequestInit, "headers"> & {
  headers?: Record<string, string>;
};

/** Coalesced refresh promise — all concurrent 401 handlers share this */
let refreshPromise: Promise<string | null> | null = null;

/** Callback invoked when the refresh token is expired / revoked */
let onSessionExpired: (() => void) | null = null;

/**
 * Register a handler that fires when the session expires (refresh fails).
 * AuthContext calls this on mount so it can trigger logout + navigation.
 */
export function setSessionExpiredHandler(handler: () => void) {
  onSessionExpired = handler;
}

/**
 * Coalesce concurrent token refresh attempts into a single request.
 * The promise is cleared only AFTER it settles, so every waiter that
 * called `getRefreshedToken()` while the refresh was in-flight will
 * receive the same result.
 */
async function getRefreshedToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = refreshAccessToken().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

/**
 * Attempt to refresh the access token using the stored refresh token.
 * Returns the new JWT on success, or null if refresh fails.
 */
async function refreshAccessToken(): Promise<string | null> {
  const currentRefreshToken = await getRefreshToken();
  if (!currentRefreshToken) return null;

  try {
    const url = `${API_BASE_URL}${AUTH_ENDPOINTS.REFRESH}`;
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: currentRefreshToken }),
    });

    if (!response.ok) {
      await clearAllTokens();
      onSessionExpired?.();
      return null;
    }

    const data = (await response.json()) as {
      access_token: string;
      refresh_token?: string;
    };
    await storeJwt(data.access_token);
    if (data.refresh_token) {
      await storeRefreshToken(data.refresh_token);
    }
    return data.access_token;
  } catch {
    await clearAllTokens();
    onSessionExpired?.();
    return null;
  }
}

/**
 * Restore a stored session on app launch using the refresh token, if present.
 */
export async function restoreStoredSession(): Promise<string | null> {
  return refreshAccessToken();
}

/**
 * Authenticated fetch wrapper.
 * Attaches JWT if available, otherwise attaches an already-provisioned guest token.
 * On 401, attempts a single token refresh before retrying.
 * All requests go to API_BASE_URL.
 */
export async function apiFetch<T = unknown>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const jwt = await getStoredJwt();
  const guestToken = jwt ? null : await getStoredGuestToken();

  const headers: Record<string, string> = {
    ...options.headers,
  };
  // Only default to JSON content type for non-FormData bodies.
  // FormData needs fetch to set Content-Type automatically (includes boundary).
  const isFormData =
    typeof FormData !== "undefined" && options.body instanceof FormData;
  if (options.body && !isFormData) {
    headers["Content-Type"] ??= "application/json";
  }

  if (jwt) {
    headers["Authorization"] = `Bearer ${jwt}`;
  } else if (guestToken) {
    headers["X-Guest-Token"] = guestToken;
  }

  const url = `${API_BASE_URL}${path}`;

  if (!__DEV__ && !url.startsWith("https://")) {
    throw new Error("API calls must use HTTPS in production");
  }

  const response = await fetch(url, { ...options, headers });

  // On 401 with a JWT, attempt token refresh and retry once
  if (response.status === 401 && jwt) {
    const newJwt = await getRefreshedToken();

    if (newJwt) {
      // Retry the original request with the new token
      const retryHeaders = { ...headers, Authorization: `Bearer ${newJwt}` };
      const retryResponse = await fetch(url, { ...options, headers: retryHeaders });

      if (!retryResponse.ok) {
        const body = await retryResponse.text().catch(() => "");
        throw new ApiError(retryResponse.status, body, url, retryResponse.headers);
      }

      // 204 No Content — return undefined (callers should type T as void)
      if (retryResponse.status === 204) {
        return undefined as T;
      }

      return retryResponse.json() as Promise<T>;
    }

    // Refresh failed — fall through to guest mode error
  }

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new ApiError(response.status, body, url, response.headers);
  }

  // 204 No Content — return undefined (callers should type T as void)
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}


export class ApiError extends Error {
  readonly status: number;
  readonly body: string;
  readonly url: string;
  readonly headers: Headers | null;
  constructor(
    status: number,
    body: string,
    url: string,
    headers: Headers | null = null,
  ) {
    const message = __DEV__ ? `API ${status}: ${url}` : `API ${status}`;
    super(message);
    this.status = status;
    this.body = body;
    this.url = url;
    this.headers = headers;
    this.name = "ApiError";
  }
}
