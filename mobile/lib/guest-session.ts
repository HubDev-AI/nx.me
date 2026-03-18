import * as SecureStore from "expo-secure-store";
import * as Crypto from "expo-crypto";

import { SECURE_STORE_KEYS } from "../constants/config";

/**
 * Retrieve existing guest token from SecureStore, or create and persist a new one.
 * Uses cryptographically secure random bytes (32 bytes = 256 bits).
 */
export async function getOrCreateGuestToken(): Promise<string> {
  const existing = await SecureStore.getItemAsync(
    SECURE_STORE_KEYS.GUEST_TOKEN,
  );
  if (existing) {
    return existing;
  }

  // Generate 32 cryptographically secure random bytes
  const randomBytes = await Crypto.getRandomBytesAsync(32);
  const token = Array.from(randomBytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  await SecureStore.setItemAsync(SECURE_STORE_KEYS.GUEST_TOKEN, token);
  return token;
}
