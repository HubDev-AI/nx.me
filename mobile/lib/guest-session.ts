import { getItem, setItem } from "./secure-storage";
import {
  API_BASE_URL,
  AUTH_ENDPOINTS,
  SECURE_STORE_KEYS,
} from "../constants/config";

interface GuestResponse {
  user_id: string;
  guest_token: string;
}

/**
 * Retrieve the cached guest token or ask the backend for a fresh one.
 *
 * The backend `POST /v1/auth/guest` endpoint:
 * - Provisions a `users.is_guest=true` row and a 64-hex session token.
 * - Returns 403 `FEATURE_DISABLED` when `FEATURE_AUTH_REQUIRED=true`.
 *
 * Callers must only invoke this in guest mode (features.auth_required=false);
 * the token is persisted to SecureStore so subsequent calls skip the network.
 */
export async function getOrCreateGuestToken(): Promise<string> {
  const existing = await getItem(SECURE_STORE_KEYS.GUEST_TOKEN);
  if (existing) return existing;

  const resp = await fetch(`${API_BASE_URL}${AUTH_ENDPOINTS.GUEST}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!resp.ok) {
    throw new Error(`Guest token request failed: HTTP ${resp.status}`);
  }
  const data = (await resp.json()) as GuestResponse;
  if (!data.guest_token) {
    throw new Error("Guest token response missing guest_token field");
  }
  await setItem(SECURE_STORE_KEYS.GUEST_TOKEN, data.guest_token);
  return data.guest_token;
}

/**
 * Return the persisted guest token without provisioning a new guest session.
 *
 * Use this in generic request code paths where guest mode may be disabled.
 */
export async function getStoredGuestToken(): Promise<string | null> {
  return getItem(SECURE_STORE_KEYS.GUEST_TOKEN);
}
