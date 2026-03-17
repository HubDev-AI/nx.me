import * as SecureStore from "expo-secure-store";

import { SECURE_STORE_KEYS } from "../constants/config";

/**
 * Retrieve stored JWT from SecureStore.
 * Returns null if no token is stored (guest/unauthenticated).
 */
export async function getStoredJwt(): Promise<string | null> {
  return SecureStore.getItemAsync(SECURE_STORE_KEYS.JWT);
}

/**
 * Persist JWT to SecureStore after successful authentication.
 */
export async function storeJwt(jwt: string): Promise<void> {
  await SecureStore.setItemAsync(SECURE_STORE_KEYS.JWT, jwt);
}

/**
 * Remove stored JWT (logout).
 */
export async function clearJwt(): Promise<void> {
  await SecureStore.deleteItemAsync(SECURE_STORE_KEYS.JWT);
}
