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

/** Analysis API paths */
export const ANALYSIS_ENDPOINTS = {
  CREATE: "/v1/analyses",
  GENERATE: (id: string) => `/v1/analyses/${id}/generate`,
  JOB_STATUS: (id: string) => `/v1/jobs/${id}`,
  JOB_CANCEL: (id: string) => `/v1/jobs/${id}/cancel`,
} as const;

/** Analysis polling configuration */
export const ANALYSIS_POLLING = {
  /** Interval between job status polls (ms) */
  INTERVAL_MS: 1500,
  /** Maximum time to wait before showing timeout hint (ms) */
  TIMEOUT_HINT_MS: 30000,
} as const;

/** Image picker configuration */
export const IMAGE_PICKER = {
  /** Max quality for uploaded images (0-1) */
  QUALITY: 0.85,
  /** Aspect ratio for cropping [width, height] */
  ASPECT: [1, 1] as [number, number],
} as const;

/** Feed API paths */
export const FEED_ENDPOINTS = {
  FEED: "/v1/feed",
  REACT: (postId: string) => `/v1/posts/${postId}/react`,
  COMMENTS: (postId: string) => `/v1/posts/${postId}/comments`,
} as const;

/** Comments configuration */
export const COMMENTS_CONFIG = {
  /** Number of comments per page */
  PAGE_SIZE: 20,
  /** Max comment length (characters) */
  MAX_COMMENT_LENGTH: 500,
  /** Bottom sheet scrim opacity */
  SCRIM_OPACITY: 0.5,
  /** Sheet entry animation duration (ms) */
  ENTER_DURATION_MS: 300,
  /** Sheet exit animation duration (ms) */
  EXIT_DURATION_MS: 200,
  /** Swipe-down dismiss threshold (px) */
  SWIPE_DISMISS_THRESHOLD: 100,
  /** Placeholder text for deleted comments */
  DELETED_PLACEHOLDER: "Comment removed",
} as const;

/** Feed configuration */
export const FEED_CONFIG = {
  /** Number of posts per page */
  PAGE_SIZE: 10,
  /** Stagger delay per card for entrance animation (ms) */
  STAGGER_DELAY_MS: 40,
  /** Max stagger items (avoid long delays for later items) */
  MAX_STAGGER_ITEMS: 8,
  /** FlatList performance: items to render per batch */
  MAX_TO_RENDER_PER_BATCH: 10,
  /** FlatList performance: batching period (ms) */
  UPDATE_CELLS_BATCHING_PERIOD_MS: 50,
  /** FlatList performance: window size (number of viewports to render) */
  WINDOW_SIZE: 21,
} as const;

/** Feed sort options */
export const FEED_SORT = {
  NEWEST: "newest",
  TRENDING: "trending",
  BIGGEST_IMPROVEMENTS: "biggest_improvements",
} as const;

export type FeedSortValue = (typeof FEED_SORT)[keyof typeof FEED_SORT];

/** Stripe — publishable key from env / Expo config extras */
export const STRIPE_PUBLISHABLE_KEY: string =
  (extra.stripePublishableKey as string) ?? "";

/** Apple Pay merchant identifier */
export const APPLE_MERCHANT_ID: string =
  (extra.appleMerchantId as string) ?? "merchant.ai.nxme.app";

/** Entitlement + payment API paths */
export const ENTITLEMENT_ENDPOINTS = {
  GET: "/v1/entitlement",
  PURCHASE_CREDITS: "/v1/credits/purchase",
  SUBSCRIBE: "/v1/subscriptions",
} as const;

/** Advisor API paths */
export const ADVISOR_ENDPOINTS = {
  MESSAGES: "/v1/advisor/messages",
  NUDGES: "/v1/advisor/nudges",
  NUDGE_READ: (id: string) => `/v1/advisor/nudges/${id}/read`,
  MEMORIES: "/v1/memories",
  MEMORY_DELETE: (id: string) => `/v1/memories/${id}`,
} as const;

/** Advisor configuration */
export const ADVISOR_CONFIG = {
  /** Number of nudges per page */
  NUDGE_PAGE_SIZE: 20,
  /** Number of messages per page */
  MESSAGE_PAGE_SIZE: 30,
  /** Typing indicator dot animation duration (ms) */
  TYPING_DOT_DURATION_MS: 400,
  /** Typing indicator dot delay between dots (ms) */
  TYPING_DOT_DELAY_MS: 150,
  /** Auto-scroll debounce (ms) */
  AUTO_SCROLL_DELAY_MS: 100,
  /** FlatList performance: items to render per batch */
  MAX_TO_RENDER_PER_BATCH: 15,
  /** FlatList performance: batching period (ms) */
  UPDATE_CELLS_BATCHING_PERIOD_MS: 50,
  /** FlatList performance: window size */
  WINDOW_SIZE: 21,
} as const;

/** Paywall animation configuration */
export const PAYWALL_ANIMATION = {
  /** Modal backdrop opacity */
  SCRIM_OPACITY: 0.5,
  /** Modal entry duration (ms) */
  ENTER_DURATION_MS: 300,
  /** Modal exit duration (ms) */
  EXIT_DURATION_MS: 200,
  /** Press feedback scale */
  PRESS_SCALE: 0.98,
  /** Press feedback duration (ms) */
  PRESS_DURATION_MS: 150,
  /** Credit badge count animation duration (ms) */
  COUNT_ANIMATION_DURATION_MS: 600,
} as const;

/** Profile API paths */
export const PROFILE_ENDPOINTS = {
  PROFILE: (username: string) => `/v1/users/${username}/profile`,
  HISTORY: (username: string) => `/v1/users/${username}/history`,
  REACTIONS: (username: string) => `/v1/users/${username}/reactions`,
  UPDATE: (username: string) => `/v1/users/${username}`,
} as const;

/** Profile grid configuration */
export const PROFILE_CONFIG = {
  /** Number of columns in the glow-up grid */
  GRID_COLUMNS: 3,
  /** Gap between grid items (dp) */
  GRID_GAP: 4,
  /** Number of items per page for history / reactions */
  PAGE_SIZE: 18,
  /** Display name max length */
  DISPLAY_NAME_MAX_LENGTH: 50,
} as const;

/** Touch target minimum (pt) — WCAG / platform guidelines */
export const MIN_TOUCH_TARGET = 44;

/** Validation constants */
export const AUTH_VALIDATION = {
  PASSWORD_MIN_LENGTH: 8,
  USERNAME_MIN_LENGTH: 3,
  USERNAME_MAX_LENGTH: 30,
  /** Alphanumeric + underscores, starts with letter */
  USERNAME_PATTERN: /^[a-zA-Z][a-zA-Z0-9_]*$/,
  EMAIL_PATTERN: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
} as const;
