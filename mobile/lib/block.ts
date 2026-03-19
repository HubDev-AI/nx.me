/**
 * Block API — user-to-user blocking.
 *
 * POST /v1/users/{userId}/block — 204 on success
 * DELETE /v1/users/{userId}/block — 204 on success
 */
import { API_BASE_URL } from "../constants/config";
import { getStoredJwt } from "./auth";

/**
 * Block a user. Requires authentication.
 * Server returns 204 (no content) on success.
 */
export async function blockUser(userId: string): Promise<void> {
  const jwt = await getStoredJwt();
  if (!jwt) {
    throw new Error("Authentication required to block a user");
  }

  const url = `${API_BASE_URL}/v1/users/${userId}/block`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${jwt}`,
    },
  });

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new Error(
      __DEV__
        ? `Block failed (${response.status}): ${body}`
        : `Block failed (${response.status})`,
    );
  }
}

/**
 * Unblock a user. Requires authentication.
 * Server returns 204 (no content) on success.
 */
export async function unblockUser(userId: string): Promise<void> {
  const jwt = await getStoredJwt();
  if (!jwt) {
    throw new Error("Authentication required to unblock a user");
  }

  const url = `${API_BASE_URL}/v1/users/${userId}/block`;
  const response = await fetch(url, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${jwt}`,
    },
  });

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new Error(
      __DEV__
        ? `Unblock failed (${response.status}): ${body}`
        : `Unblock failed (${response.status})`,
    );
  }
}
