import { Platform } from "react-native";
import { getItem, setItem } from "./secure-storage";
import { SECURE_STORE_KEYS } from "../constants/config";

/**
 * Retrieve existing guest token or create a new one.
 * Web: uses crypto.randomUUID() or Math.random fallback.
 * Native: uses expo-crypto for secure random bytes.
 */
export async function getOrCreateGuestToken(): Promise<string> {
  const existing = await getItem(SECURE_STORE_KEYS.GUEST_TOKEN);
  if (existing) return existing;

  let token: string;

  if (Platform.OS === "web") {
    // Web: use browser crypto API
    if (typeof crypto !== "undefined" && crypto.randomUUID) {
      token = crypto.randomUUID() + crypto.randomUUID();
    } else {
      token = Math.random().toString(36).slice(2) + Date.now().toString(36);
    }
  } else {
    // Native: use expo-crypto
    const Crypto = require("expo-crypto");
    const randomBytes = await Crypto.getRandomBytesAsync(32);
    token = Array.from(randomBytes as Uint8Array)
      .map((b: number) => b.toString(16).padStart(2, "0"))
      .join("");
  }

  await setItem(SECURE_STORE_KEYS.GUEST_TOKEN, token);
  return token;
}
