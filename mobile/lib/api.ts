import { API_BASE_URL, AUTH_ENDPOINTS } from "../constants/config";
import {
  getStoredJwt,
  storeJwt,
  getRefreshToken,
  storeRefreshToken,
  clearAllTokens,
} from "./auth";
import { getOrCreateGuestToken } from "./guest-session";

type RequestOptions = Omit<RequestInit, "headers"> & {
  headers?: Record<string, string>;
};

/** Flag to prevent concurrent refresh attempts */
let isRefreshing = false;
/** Queued requests waiting for a refresh to complete */
let refreshPromise: Promise<string | null> | null = null;

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
    return null;
  }
}

/**
 * Authenticated fetch wrapper.
 * Attaches JWT if available, otherwise attaches guest token.
 * On 401, attempts a single token refresh before retrying.
 * All requests go to API_BASE_URL.
 */
export async function apiFetch<T = unknown>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const jwt = await getStoredJwt();
  const guestToken = jwt ? null : await getOrCreateGuestToken();

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
    // Coalesce concurrent refresh attempts into a single request
    if (!isRefreshing) {
      isRefreshing = true;
      refreshPromise = refreshAccessToken().finally(() => {
        isRefreshing = false;
        refreshPromise = null;
      });
    }

    const newJwt = await (refreshPromise ?? refreshAccessToken());

    if (newJwt) {
      // Retry the original request with the new token
      const retryHeaders = { ...headers, Authorization: `Bearer ${newJwt}` };
      const retryResponse = await fetch(url, { ...options, headers: retryHeaders });

      if (!retryResponse.ok) {
        const body = await retryResponse.text().catch(() => "");
        throw new ApiError(retryResponse.status, body, url);
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
    throw new ApiError(response.status, body, url);
  }

  // 204 No Content — return undefined (callers should type T as void)
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}


export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: string,
    public readonly url: string,
  ) {
    const message = __DEV__ ? `API ${status}: ${url}` : `API ${status}`;
    super(message);
    this.name = "ApiError";
  }
}
