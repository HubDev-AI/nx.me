/**
 * Block API — user-to-user blocking.
 *
 * POST /v1/users/{userId}/block — 204 on success
 * DELETE /v1/users/{userId}/block — 204 on success
 */
import { apiFetch } from "./api";

/**
 * Block a user. Requires authentication.
 * Server returns 204 (no content) on success.
 */
export async function blockUser(userId: string): Promise<void> {
  await apiFetch(`/v1/users/${userId}/block`, { method: "POST" });
}

/**
 * Unblock a user. Requires authentication.
 * Server returns 204 (no content) on success.
 */
export async function unblockUser(userId: string): Promise<void> {
  await apiFetch(`/v1/users/${userId}/block`, { method: "DELETE" });
}
