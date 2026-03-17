/**
 * App-wide constants for card-web.
 * All values that would otherwise be magic strings/numbers live here.
 * Environment-sensitive values are read from process.env at runtime.
 */

/** ISR revalidation window in seconds (60s = FCP ≤2s target at P95 on 4G) */
export const CARD_REVALIDATE_SECONDS = 60;

/** HTTP status code the backend returns for a deleted/gone card */
export const HTTP_GONE = 410;

/** OG image dimensions (pixels) */
export const OG_IMAGE_WIDTH = 1200;
export const OG_IMAGE_HEIGHT = 630;

/** Number of improvement recommendations to display */
export const RECOMMENDATIONS_DISPLAY_COUNT = 5;

/** Deep-link path prefix for the native app */
export const APP_DEEP_LINK_PATH = '/signup';

/**
 * Backend API base URL (server-only).
 * Used by server-side data fetching (e.g. getCardData).
 * Falls back to NEXT_PUBLIC_API_URL, then localhost for local development.
 */
export const API_BASE_URL =
  process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

/**
 * Backend API base URL (client-safe).
 * Only use this in client components where the URL must be exposed to the browser.
 */
export const PUBLIC_API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

/** App Store URL for iOS */
export const APP_STORE_URL =
  process.env.NEXT_PUBLIC_APP_STORE_URL ??
  'https://apps.apple.com/app/nxme/id0000000000';

/** Play Store URL for Android */
export const PLAY_STORE_URL =
  process.env.NEXT_PUBLIC_PLAY_STORE_URL ??
  'https://play.google.com/store/apps/details?id=ai.nxme.app';

/** Universal link / web base URL (used for app deep-links) */
export const APP_BASE_URL =
  process.env.NEXT_PUBLIC_APP_BASE_URL ?? 'https://nxme.ai';

/** ms to wait for the native app to open before redirecting to the store */
export const APP_OPEN_TIMEOUT_MS = 1500;

/** Site name used in metadata */
export const SITE_NAME = 'NXME';

/** Site URL — canonical base */
export const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? 'https://nxme.ai';
