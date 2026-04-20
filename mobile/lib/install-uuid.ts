/**
 * install-uuid — stable per-install UUID for device attribution.
 *
 * Generated once on first launch using `expo-crypto` (UUID v4),
 * persisted to SecureStore under `SECURE_STORE_KEYS.INSTALL_UUID`.
 *
 * Sent as `X-Install-UUID` on auth endpoints so the backend can correlate
 * installs without requiring a logged-in user.
 *
 * Reads SecureStore, generates + persists on miss, regenerates on corruption.
 */
import * as Crypto from "expo-crypto";

import { SECURE_STORE_KEYS } from "../constants/config";
import { deleteItem, getItem, setItem } from "./secure-storage";

/**
 * UUID v4 format: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
 * y is one of 8, 9, a, b.
 */
const UUID_V4_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

/**
 * Return true if `value` is a well-formed UUID v4.
 * Corrupt / truncated values regenerate rather than silently persist.
 */
export function isValidUuidV4(value: string): boolean {
  return UUID_V4_PATTERN.test(value);
}

/**
 * Return the persisted install UUID, generating and storing one if absent
 * or corrupted.
 *
 * - First call: generates a UUID v4 via `Crypto.randomUUID()`, persists it,
 *   and returns it.
 * - Subsequent calls: reads and returns the stored value.
 * - Corruption (stored value fails UUID v4 format check): deletes the bad
 *   value, generates a fresh one, persists it, and returns it.
 */
export async function getOrCreateInstallUuid(): Promise<string> {
  const stored = await getItem(SECURE_STORE_KEYS.INSTALL_UUID);

  if (stored !== null) {
    if (isValidUuidV4(stored)) {
      return stored;
    }
    // Corrupted — purge and regenerate
    await deleteItem(SECURE_STORE_KEYS.INSTALL_UUID);
  }

  const fresh = Crypto.randomUUID();
  await setItem(SECURE_STORE_KEYS.INSTALL_UUID, fresh);
  return fresh;
}
