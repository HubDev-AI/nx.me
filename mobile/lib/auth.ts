import { getItem, setItem, deleteItem } from "./secure-storage";
import { SECURE_STORE_KEYS } from "../constants/config";

export async function getStoredJwt(): Promise<string | null> {
  return getItem(SECURE_STORE_KEYS.JWT);
}

export async function storeJwt(jwt: string): Promise<void> {
  await setItem(SECURE_STORE_KEYS.JWT, jwt);
}

export async function clearJwt(): Promise<void> {
  await deleteItem(SECURE_STORE_KEYS.JWT);
}

export async function getRefreshToken(): Promise<string | null> {
  return getItem(SECURE_STORE_KEYS.REFRESH_TOKEN);
}

export async function storeRefreshToken(token: string): Promise<void> {
  await setItem(SECURE_STORE_KEYS.REFRESH_TOKEN, token);
}

export async function clearRefreshToken(): Promise<void> {
  await deleteItem(SECURE_STORE_KEYS.REFRESH_TOKEN);
}

export async function clearAllTokens(): Promise<void> {
  await Promise.all([clearJwt(), clearRefreshToken()]);
}
