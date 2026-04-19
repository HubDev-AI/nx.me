import { API_BASE_URL, AUTH_ENDPOINTS, SECURE_STORE_KEYS } from "../constants/config";
import {
  getStoredJwt,
  storeJwt,
  getRefreshToken,
  storeRefreshToken,
  clearAllTokens,
} from "./auth";
import { getOrCreateGuestToken, getStoredGuestToken } from "./guest-session";
import { getOrCreateInstallUuid } from "./install-uuid";
import { getAuthRequired } from "./features-state";
import { deleteItem } from "./secure-storage";

/**
 * Auth endpoint paths that receive the `X-Install-UUID` header.
 * Kept as a Set for O(1) lookup on every request.
 */
const INSTALL_UUID_PATHS = new Set<string>([
  AUTH_ENDPOINTS.REGISTER,
  AUTH_ENDPOINTS.EMAIL_LOGIN,
  AUTH_ENDPOINTS.SOCIAL_LOGIN,
  AUTH_ENDPOINTS.TIKTOK_LOGIN,
]);

type RequestOptions = Omit<RequestInit, "headers"> & {
  headers?: Record<string, string>;
};

/** Coalesced refresh promise — all concurrent 401 handlers share this */
let refreshPromise: Promise<string | null> | null = null;

/** Coalesced guest-token rotation promise — mirrors refreshPromise for the guest path. */
let guestRotatePromise: Promise<string | null> | null = null;

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
/**
 * Resolve a guest token for the current request.
 *
 * - When backend guest mode is off (`auth_required=true`), returns any stored
 *   token but never provisions a new one.
 * - When guest mode is on, provisions a token on first use so every guest
 *   request carries `X-Guest-Token` even before `AuthGuard`'s bootstrap lands.
 *
 * Returns null on any provisioning failure — the caller will surface the
 * original 401/403 rather than crash.
 */
async function resolveGuestToken(): Promise<string | null> {
  const stored = await getStoredGuestToken();
  if (stored) return stored;
  if (getAuthRequired()) return null;
  try {
    return await getOrCreateGuestToken();
  } catch (err) {
    if (__DEV__) console.warn("Guest token provisioning failed:", err);
    return null;
  }
}

/**
 * Clear the stored guest token and provision a fresh one. Used when the
 * backend rejects a stored guest token (e.g., after a local DB reset wipes
 * the `users` row the token pointed at).
 *
 * Coalesces concurrent rotations so a burst of 401s issues one
 * `POST /v1/auth/guest`, not N.
 */
async function rotateGuestToken(): Promise<string | null> {
  if (!guestRotatePromise) {
    guestRotatePromise = (async () => {
      await deleteItem(SECURE_STORE_KEYS.GUEST_TOKEN);
      if (getAuthRequired()) return null;
      try {
        return await getOrCreateGuestToken();
      } catch (err) {
        if (__DEV__) console.warn("Guest token rotation failed:", err);
        return null;
      }
    })().finally(() => {
      guestRotatePromise = null;
    });
  }
  return guestRotatePromise;
}

export async function apiFetch<T = unknown>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const jwt = await getStoredJwt();
  const guestToken = jwt ? null : await resolveGuestToken();

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

  // Attach stable install UUID on auth endpoints so the backend can
  // correlate installs across register / login flows without requiring
  // a logged-in user. Errors are swallowed — a missing header is
  // non-fatal for auth calls.
  if (INSTALL_UUID_PATHS.has(path)) {
    try {
      headers["X-Install-UUID"] = await getOrCreateInstallUuid();
    } catch {
      // Non-fatal — proceed without the header
    }
  }

  const url = `${API_BASE_URL}${path}`;

  if (!__DEV__ && !url.startsWith("https://")) {
    throw new Error("API calls must use HTTPS in production");
  }

  // Dev-only request log — visible in the Metro terminal so we can see what
  // the app actually sends without instrumenting every callsite. Auth header
  // is summarized (not printed in full) to avoid leaking JWTs into terminal
  // history when sharing screenshots.
  if (__DEV__) {
    const method = options.method ?? "GET";
    const auth = jwt ? "JWT" : guestToken ? "Guest" : "none";
    const bodyPreview =
      typeof options.body === "string"
        ? options.body.slice(0, 500)
        : isFormData
          ? "[FormData]"
          : "";
    console.log(`[api] → ${method} ${url} auth=${auth} ${bodyPreview}`);
  }

  const response = await fetch(url, { ...options, headers });

  if (__DEV__ && !response.ok) {
    const cloned = response.clone();
    const errBody = await cloned.text().catch(() => "");
    console.log(
      `[api] ← ${response.status} ${url} ${errBody.slice(0, 500)}`,
    );
  }

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

  // On 401 with a guest token, the stored token is stale (e.g. DB reset).
  // Rotate and retry once — fixes the case where a dev wipes Supabase but
  // the mobile client still holds the old session token in SecureStore.
  if (response.status === 401 && !jwt && guestToken) {
    const freshGuestToken = await rotateGuestToken();
    if (freshGuestToken) {
      const retryHeaders = { ...headers, "X-Guest-Token": freshGuestToken };
      const retryResponse = await fetch(url, { ...options, headers: retryHeaders });
      if (!retryResponse.ok) {
        const body = await retryResponse.text().catch(() => "");
        throw new ApiError(retryResponse.status, body, url, retryResponse.headers);
      }
      if (retryResponse.status === 204) {
        return undefined as T;
      }
      return retryResponse.json() as Promise<T>;
    }
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
