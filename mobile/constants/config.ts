/**
 * App-wide configuration constants.
 * Environment-sensitive values are read from Expo Constants (extra / env).
 */
import Constants from "expo-constants";

const extra = Constants.expoConfig?.extra ?? {};

/** Base URL for the NXME backend API */
export const API_BASE_URL: string =
  (extra.apiBaseUrl as string) ?? "https://api.nxme.ai";

/** Universal link origin — only HTTPS allowed, no custom URI schemes */
export const UNIVERSAL_LINK_ORIGIN = "https://nxme.ai";

/** SecureStore keys */
export const SECURE_STORE_KEYS = {
  GUEST_TOKEN: "nxme_guest_token",
  JWT: "nxme_jwt",
  PUSH_TOKEN: "nxme_push_token",
} as const;
