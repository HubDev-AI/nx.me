import * as SecureStore from "expo-secure-store";
import * as Crypto from "expo-crypto";

import { SECURE_STORE_KEYS } from "../constants/config";

/**
 * Retrieve existing guest token from SecureStore, or create and persist a new one.
 * The token is a SHA-256 hex digest of timestamp + random data.
 */
export async function getOrCreateGuestToken(): Promise<string> {
  const existing = await SecureStore.getItemAsync(
    SECURE_STORE_KEYS.GUEST_TOKEN,
  );
  if (existing) {
    return existing;
  }

  const raw = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const token = await Crypto.digestStringAsync(
    Crypto.CryptoDigestAlgorithm.SHA256,
    raw,
  );

  await SecureStore.setItemAsync(SECURE_STORE_KEYS.GUEST_TOKEN, token);
  return token;
}
