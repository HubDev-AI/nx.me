/**
 * App-wide constants for card-web.
 * All values that would otherwise be magic strings/numbers live here.
 * Environment-sensitive values are read from process.env at runtime.
 */

/** ISR revalidation window in seconds (60s = FCP ≤2s target at P95 on 4G) */
export const CARD_REVALIDATE_SECONDS = 60;

/**
 * HTTP 404 Not Found — emitted by the public cards API when a username or
 * share hash does not resolve to a visible card.
 */
export const HTTP_NOT_FOUND = 404;

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
 * Falls back to NEXT_PUBLIC_API_URL, then the production URL.
 */
export const API_BASE_URL: string = (() => {
  const serverUrl = process.env.API_URL;
  if (serverUrl) return serverUrl;
  if (process.env.NODE_ENV === "production") {
    console.warn(
      "[config] API_URL not set — falling back to NEXT_PUBLIC_API_URL."
    );
  }
  return process.env.NEXT_PUBLIC_API_URL ?? "https://api.nxme.ai";
})();

/**
 * App Store URL for iOS.
 * When NEXT_PUBLIC_APP_STORE_URL is unset (e.g. pre-launch), this
 * falls back to the site's universal link origin so the CTA still
 * resolves to a working page instead of a broken id=0 App Store URL.
 * cta-button treats an empty string as "skip store redirect" — the
 * fallback keeps the landing-page links navigable while keeping that
 * semantics in place for the CTA flow.
 */
export const APP_STORE_URL =
  process.env.NEXT_PUBLIC_APP_STORE_URL ??
  process.env.NEXT_PUBLIC_APP_BASE_URL ??
  'https://nxme.ai';

/**
 * Play Store URL for Android. Same fallback as APP_STORE_URL — resolves
 * to the marketing site until NEXT_PUBLIC_PLAY_STORE_URL is configured.
 */
export const PLAY_STORE_URL =
  process.env.NEXT_PUBLIC_PLAY_STORE_URL ??
  process.env.NEXT_PUBLIC_APP_BASE_URL ??
  'https://nxme.ai';

/** Universal link / web base URL (used for app deep-links) */
export const APP_BASE_URL =
  process.env.NEXT_PUBLIC_APP_BASE_URL ?? 'https://nxme.ai';

/** Privacy policy URL (external — defaults to marketing site). */
export const PRIVACY_URL =
  process.env.NEXT_PUBLIC_PRIVACY_URL ?? `${APP_BASE_URL}/privacy`;

/** Terms of service URL (external — defaults to marketing site). */
export const TERMS_URL =
  process.env.NEXT_PUBLIC_TERMS_URL ?? `${APP_BASE_URL}/terms`;

/** ms to wait for the native app to open before redirecting to the store */
export const APP_OPEN_TIMEOUT_MS = 1500;

/** ms before a backend API fetch is aborted (prevents hanging when backend is down) */
export const API_FETCH_TIMEOUT_MS = Number(
  process.env.API_FETCH_TIMEOUT_MS ?? '3000',
);

/** Site name used in metadata */
export const SITE_NAME = 'NXME';

/** Site URL — canonical base */
export const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? 'https://nxme.ai';

/** Native app bundle identifier — shared between iOS App ID and Android package name. */
export const APP_BUNDLE_ID = 'ai.nxme.app';

/**
 * Paths the mobile app claims via iOS universal links and Android app-links.
 *
 * **Keep in parity with `mobile/app.config.ts`** — claiming a path here but not
 * registering a matching Expo route means iOS captures URLs the app can't
 * resolve and silently 404s inside the app instead of opening the browser.
 *
 * Entries use Apple AASA path-pattern syntax (`*` = multi-segment wildcard).
 * Only add paths that have a corresponding `mobile/app/...` route.
 */
export const APP_LINK_PATHS: ReadonlyArray<string> = [
  '/signup',
  '/card/*',
];

/**
 * Sitemap pagination + caching constants.
 * - PAGE_SIZE: backend default/max per_page is 1000; we use the max to minimise round-trips.
 * - MAX_ENTRIES: Google sitemap cap (50,000 URLs per sitemap file). Above this we'd need a
 *   sitemap index. We log a warning when we hit the cap instead of silently truncating.
 * - REVALIDATE_SECONDS: 24h — the listing changes slowly and each page has its
 *   own ISR cache entry, so a shorter window amplifies latency on the first
 *   crawl after expiry (50 pages × backend latency, worst case). Daily refresh
 *   is well inside Google's recrawl cadence for a sitemap.
 */
export const SITEMAP_PAGE_SIZE = 1000;
export const SITEMAP_MAX_ENTRIES = 50000;
export const SITEMAP_REVALIDATE_SECONDS = 86400;

/** Public card listing path on the backend — used by the sitemap generator. */
export const PUBLIC_CARDS_LIST_PATH = '/v1/public/cards';

/** Public makeup listing path — only opted-in makeup posts. */
export const PUBLIC_MAKEUP_LIST_PATH = '/v1/public/makeup';

/**
 * Accent palette rotated per-request by `buildTheme()`. Typed as a non-empty
 * tuple so `THEME_ACCENTS[0]` is non-optional and `DEFAULT_ACCENT` can derive
 * from it without a fallback literal.
 */
export const THEME_ACCENTS: readonly [string, ...string[]] = [
  '#F43F5E', '#14B8A6', '#D4A060', '#38BDF8', '#FB923C',
  '#6366F1', '#EF4444', '#A78BFA', '#F472B6', '#E879F9',
  '#34D399', '#F59E0B', '#EC4899', '#8B5CF6', '#10B981',
  '#0EA5E9', '#F97316', '#84CC16', '#E11D48', '#7C3AED',
];

/**
 * Fallback accent colour used when the `--accent` CSS custom property is not
 * set (e.g. error pages rendered before the theme provider runs, icon assets,
 * SSR paths that bypass `buildTheme()`). First entry of `THEME_ACCENTS` so the
 * fallback visually matches the default theme rotation.
 */
export const DEFAULT_ACCENT: string = THEME_ACCENTS[0];

/**
 * Image CDN hostnames trusted by the OG image renderer. URLs whose host
 * matches (exact or sub-domain) are passed through to satori; everything else
 * is dropped to `""` so the renderer falls back to the placeholder layout.
 */
export const IMAGE_CDN_HOSTS: ReadonlyArray<string> = [
  'supabase.co',
  'fal.ai',
  'fal.media',
  'fal.run',
  'images.unsplash.com',
];
