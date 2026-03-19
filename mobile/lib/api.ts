import * as SecureStore from "expo-secure-store";

import { API_BASE_URL } from "../constants/config";
import { getStoredJwt } from "./auth";
import { getOrCreateGuestToken } from "./guest-session";

type RequestOptions = Omit<RequestInit, "headers"> & {
  headers?: Record<string, string>;
};

/**
 * Authenticated fetch wrapper.
 * Attaches JWT if available, otherwise attaches guest token.
 * All requests go to API_BASE_URL.
 */
export async function apiFetch<T = unknown>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const jwt = await getStoredJwt();
  const guestToken = jwt ? null : await getOrCreateGuestToken();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...options.headers,
  };

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

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new ApiError(response.status, body, url);
  }

  return response.json() as Promise<T>;
}

/**
 * Store refresh token from login/signup response.
 * Call after storing the JWT on successful authentication.
 */
export async function storeRefreshToken(
  response: { refresh_token?: string },
): Promise<void> {
  if (response.refresh_token) {
    await SecureStore.setItemAsync("nxme_refresh_token", response.refresh_token);
  }
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
