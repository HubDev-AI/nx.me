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

/** OAuth Client IDs — sourced from env / Expo config extras */
export const GOOGLE_CLIENT_ID: string =
  (extra.googleClientId as string) ?? "";

export const APPLE_CLIENT_ID: string =
  (extra.appleClientId as string) ?? "";

/** Auth API paths */
export const AUTH_ENDPOINTS = {
  REGISTER: "/v1/auth/register",
  LOGIN: "/v1/auth/login",
  SOCIAL_LOGIN: "/v1/auth/social",
} as const;

/** Validation constants */
export const AUTH_VALIDATION = {
  PASSWORD_MIN_LENGTH: 8,
  USERNAME_MIN_LENGTH: 3,
  USERNAME_MAX_LENGTH: 30,
  /** Alphanumeric + underscores, starts with letter */
  USERNAME_PATTERN: /^[a-zA-Z][a-zA-Z0-9_]*$/,
  EMAIL_PATTERN: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
} as const;
