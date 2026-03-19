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

/**
 * Retrieve stored refresh token from SecureStore.
 * Returns null if no refresh token is stored.
 */
export async function getRefreshToken(): Promise<string | null> {
  return SecureStore.getItemAsync(SECURE_STORE_KEYS.REFRESH_TOKEN);
}

/**
 * Persist refresh token to SecureStore after successful authentication.
 */
export async function storeRefreshToken(token: string): Promise<void> {
  await SecureStore.setItemAsync(SECURE_STORE_KEYS.REFRESH_TOKEN, token);
}

/**
 * Remove stored refresh token (logout).
 */
export async function clearRefreshToken(): Promise<void> {
  await SecureStore.deleteItemAsync(SECURE_STORE_KEYS.REFRESH_TOKEN);
}

/**
 * Clear all auth tokens (JWT + refresh token).
 */
export async function clearAllTokens(): Promise<void> {
  await Promise.all([clearJwt(), clearRefreshToken()]);
}
