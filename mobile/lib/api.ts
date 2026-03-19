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
    ...options.headers,
  };
  if (options.body) {
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

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new ApiError(response.status, body, url);
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
