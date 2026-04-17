/**
 * App-wide configuration constants.
 * Environment-sensitive values are read from Expo Constants (extra / env).
 */
import Constants from "expo-constants";

/** Base URL for the NXME backend API */
import { Platform } from "react-native";

const extra = Constants.expoConfig?.extra ?? {};
export const API_BASE_URL: string = (() => {
  // Web dev always hits local FastAPI; native dev + prod read from Expo extras.
  if (Platform.OS === "web" && __DEV__) return "http://localhost:8000";
  const configured = extra.apiBaseUrl as string | undefined;
  if (!configured) {
    throw new Error(
      "API_BASE_URL missing — set expo.extra.apiBaseUrl in app.config.ts " +
        "(driven by the API_BASE_URL env var).",
    );
  }
  return configured;
})();

/** Universal link origin — only HTTPS allowed, no custom URI schemes */
export const UNIVERSAL_LINK_ORIGIN = "https://nxme.ai";

/** SecureStore keys */
export const SECURE_STORE_KEYS = {
  GUEST_TOKEN: "nxme_guest_token",
  JWT: "nxme_jwt",
  REFRESH_TOKEN: "nxme_refresh_token",
  /** Set to "1" after registration when email_verification_required is true */
  PENDING_EMAIL_VERIFICATION: "nxme_pending_email_verification",
  /**
   * ISO timestamp written when AuthGuard observes auth_required=true and
   * purges any stale GUEST_TOKEN. Acts as an idempotency sentinel so the
   * purge runs once across launches in production builds.
   */
  GUEST_PURGED_AT: "nxme_guest_purged_at",
} as const;

/** OAuth Client IDs — sourced from env / Expo config extras */
export const GOOGLE_CLIENT_ID: string =
  (extra.googleClientId as string) ?? "";

export const APPLE_CLIENT_ID: string =
  (extra.appleClientId as string) ?? "";

/** Google Web Client ID — required by @react-native-google-signin to get idToken */
export const GOOGLE_WEB_CLIENT_ID: string =
  (extra.googleWebClientId as string) ?? "";



/** Auth API paths */
export const AUTH_ENDPOINTS = {
  REGISTER: "/v1/auth/register",
  /** Email/password login — backend accepts { email, password } */
  EMAIL_LOGIN: "/v1/auth/email-login",
  /** @deprecated Use EMAIL_LOGIN for email/password, SOCIAL_LOGIN for social providers */
  LOGIN: "/v1/auth/login",
  /** Social login uses the /login endpoint — backend accepts { provider, id_token, nonce? } */
  SOCIAL_LOGIN: "/v1/auth/login",
  /** TikTok native SDK code exchange — backend accepts { auth_code, code_verifier? } */
  TIKTOK_LOGIN: "/v1/auth/tiktok-login",
  /**
   * Guest session — POST creates a guest user and returns { user_id, guest_token }.
   * Only accepts requests when FEATURE_AUTH_REQUIRED is off server-side;
   * otherwise returns 403 FEATURE_DISABLED.
   */
  GUEST: "/v1/auth/guest",
  /** Returns { providers: string[] } — list of enabled auth providers */
  PROVIDERS: "/v1/auth/providers",
  /**
   * Refresh token endpoint — POST with { refresh_token }.
   * Backend: app/api/auth.py:refresh_token (POST /v1/auth/refresh).
   * Response: LoginResponse. lib/api.ts clears tokens on any non-200.
   */
  REFRESH: "/v1/auth/refresh",
  /** Server-side logout — POST with JWT in Authorization header */
  LOGOUT: "/v1/auth/logout",
} as const;

/** Auth provider type — matches backend provider strings */
export type AuthProvider = "tiktok" | "google" | "apple" | "email";

/** Analysis API paths */
export const ANALYSIS_ENDPOINTS = {
  CREATE: "/v1/analyses",
  GENERATE: (id: string) => `/v1/analyses/${id}/generate`,
  JOB_STATUS: (id: string) => `/v1/jobs/${id}`,
  JOB_CANCEL: (id: string) => `/v1/jobs/${id}/cancel`,
  /**
   * Request a refund for a completed job.
   * NOTE: As of 2026-03-20, the backend does NOT expose this endpoint in its
   * OpenAPI spec. The UI handles the error gracefully (shows failure alert).
   * Once the backend adds this endpoint, it will work without app changes.
   */
  JOB_REFUND: (id: string) => `/v1/jobs/${id}/refund`,
} as const;

/** Tier-3 upload + Glow Up API paths */
export const GLOWUP_ENDPOINTS = {
  /** POST /v1/uploads — multipart upload, returns {upload_id, face_detected} */
  UPLOAD: "/v1/uploads",
  /** POST /v1/uploads/{id}/glowup/analyze — returns analysis; 428 if no consent */
  ANALYZE: (uploadId: string) => `/v1/uploads/${uploadId}/glowup/analyze`,
  /** POST /v1/uploads/{id}/glowup/generate — returns {job_id, status, ...} */
  GENERATE: (uploadId: string) => `/v1/uploads/${uploadId}/glowup/generate`,
  /** GET /v1/jobs/{id} — same jobs endpoint as before */
  JOB_STATUS: (jobId: string) => `/v1/jobs/${jobId}`,
  /** POST /v1/jobs/{id}/save — saves result */
  JOB_SAVE: (jobId: string) => `/v1/jobs/${jobId}/save`,
  /** POST /v1/users/me/face-mod-consent — idempotent consent */
  FACE_MOD_CONSENT: "/v1/users/me/face-mod-consent",
} as const;

/** HTTP status code for missing face-mod consent (Tier-3 analyze gate). */
export const HTTP_FACE_MOD_CONSENT_REQUIRED = 428;

/** Retention disclosure text — shown on upload screen. */
export const RETENTION_DISCLOSURE =
  "Photos auto-delete after 30 days of no activity.";

/** AI disclosure text — shown on result screen. */
export const AI_DISCLOSURE = "AI-generated · not a photo";

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
  REACT: (postId: string) => `/v1/posts/${postId}/reactions`,
  COMMENTS: (postId: string) => `/v1/posts/${postId}/comments`,
  DELETE_POST: (postId: string) => `/v1/posts/${postId}`,
} as const;

/** Comments configuration */
export const COMMENTS_CONFIG = {
  /** Number of comments per page */
  PAGE_SIZE: 20,
  /** Max comment length (characters) */
  MAX_COMMENT_LENGTH: 1000,
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
  PURCHASE_CREDITS: "/v1/credit-purchases",
  /** PaymentIntent bootstrap for the in-app Stripe Payment Sheet (PR6). */
  PURCHASE_CREDITS_INTENT: "/v1/credit-purchases/intent",
  SUBSCRIBE: "/v1/subscriptions",
} as const;

/** Stripe Payment Sheet copy + configuration (no magic strings in callers). */
export const STRIPE_PAYMENT_SHEET = {
  /** Text shown at the top of the Payment Sheet. */
  MERCHANT_DISPLAY_NAME: "NXME",
  /** ISO country code for the Apple Pay / business registration. */
  MERCHANT_COUNTRY_CODE: "US",
  /** `@stripe/stripe-react-native` error code for user-initiated dismiss. */
  USER_CANCELED_ERROR_CODE: "Canceled",
  /** Success toast after credit pack payment. */
  SUCCESS_MESSAGE: "Credits added.",
} as const;

/** Advisor API paths */
export const ADVISOR_ENDPOINTS = {
  MESSAGES: "/v1/advisor/messages",
  NUDGES: "/v1/advisor/nudges",
  NUDGE_READ: (id: string) => `/v1/advisor/nudges/${id}`,
  MEMORIES: "/v1/memories",
  MEMORY_DELETE: (id: string) => `/v1/memories/${id}`,
} as const;

/**
 * Advisor Chat scoped seed-state copy. Replaces the generic
 * "Start a conversation / Ask Ada for style advice" overlay shown on
 * the Chat tab so first-time users see what Ada actually does. Other
 * advisor tabs (Nudges, Memories) still use AdvisorEmptyOverlay.
 *
 * The body's italic trailing clause is non-negotiable: the chip list
 * shouldn't read as exhaustive (Ada handles anything). If SOUL.md
 * persona lanes change, update this text and the chips below in lockstep
 * — see ADVISOR_PERSONA_NAME and app/advisor/SOUL.md.
 */
export const ADVISOR_CHAT_EMPTY_TITLE = "Hi, I'm Ada.";
export const ADVISOR_CHAT_EMPTY_BODY =
  "I can help with hair, beard, fit, skincare, or grooming — or ask me anything else you're thinking about.";

/**
 * Starter chips for the Chat empty state. Tap → handleSend(chipText)
 * fires the LLM call immediately (no extra Send tap). Keep these
 * short, conversational, and aligned with SOUL.md's lanes.
 */
export const ADVISOR_CHAT_STARTER_CHIPS: readonly string[] = [
  "What hairstyle would suit me?",
  "Should I try a beard?",
  "How do I fix the fit of my clothes?",
  "What should I focus on next?",
] as const;

/** Advisor configuration */
export const ADVISOR_CONFIG = {
  /** Number of nudges per page */
  NUDGE_PAGE_SIZE: 20,
  /** Number of messages per page */
  MESSAGE_PAGE_SIZE: 30,
  /** Maximum message length (characters) */
  MESSAGE_MAX_LENGTH: 2000,
  /** Maximum memory (goal/note) length (characters) */
  MEMORY_MAX_LENGTH: 500,
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

/**
 * Shared pagination retry backoff used by infinite-scroll hooks
 * (advisor nudges, chat messages, comments). Centralised so every
 * paginated list exhibits the same retry cadence and UX.
 */
export const PAGINATION_CONFIG = {
  /** Max consecutive retries before surfacing an error to the user */
  MAX_RETRIES: 3,
  /** Retry delays (ms) — backoff per attempt, indexed by attempt number */
  RETRY_DELAYS_MS: [2000, 3000] as const,
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
  /** Pixels of vertical pan before the sheet dismisses on release */
  SWIPE_DISMISS_THRESHOLD: 100,
  /** Pixels of vertical pan before the responder claims the gesture */
  PAN_MOVE_THRESHOLD: 10,
  /** Scale factor for the credit badge bounce when balance changes */
  BOUNCE_SCALE: 1.15,
} as const;

/** Public card API paths (no auth required) */
export const CARD_ENDPOINTS = {
  PUBLIC: (username: string) => `/api/public/cards/${username}`,
} as const;

/** Profile API paths */
export const PROFILE_ENDPOINTS = {
  /** Identity for the current session — works for JWT users and guest tokens. */
  ME: "/v1/users/me",
  PROFILE: (username: string) => `/v1/users/${username}/profile`,
  HISTORY: (username: string) => `/v1/users/${username}/history`,
  UPDATE: (username: string) => `/v1/users/${username}`,
} as const;

/**
 * Bound on how long AuthGuard waits for the guest /me lookup before
 * releasing the splash screen. A stalled network must not strand users.
 */
export const GUEST_ME_TIMEOUT_MS = 5_000;

/**
 * Result-screen latency tolerance.
 *
 * - HARD_TIMEOUT_MS bounds the entire waiting period after Analyze. Must
 *   stay above the server-side `GENERATION_TIMEOUT_SECONDS + 30s
 *   watchdog grace + watchdog cron cadence`. The watchdog runs on a
 *   `cron(second=0)` schedule (~once per minute), so the worst-case
 *   server-side reconcile window is 180 + 30 + 60 = 270s. 300_000
 *   gives the client a 30s buffer above that ceiling so a
 *   legitimately-still-running job never trips the client cap before
 *   the server flips it to failed.
 * - IMAGE_URL_TIMEOUT_MS gives a status=completed-with-null-URLs row a
 *   chance to land its `after_image_url` before falling to the
 *   terminal-failure branch. 60s matches the observed worker write
 *   envelope; data bug if exceeded.
 */
export const RESULT_SCREEN_HARD_TIMEOUT_MS = 300_000;
export const RESULT_SCREEN_IMAGE_URL_TIMEOUT_MS = 60_000;

/**
 * Waiting-view copy. Surfaces the "leave is safe" message without using
 * "wait" / "loading" language that primes a failure-shaped read.
 */
export const RESULT_WAITING_TITLE = "Your glow-up is being generated.";
export const RESULT_WAITING_BODY =
  "You can leave this screen — we'll drop the result on your profile when it's done.";

/**
 * Terminal-failure copy when the hard timeout fires before the worker
 * resolves. Distinct from the "Generation failed" copy because it
 * indicates client-side give-up, not server-confirmed failure.
 */
export const RESULT_HARD_TIMEOUT_COPY =
  "We couldn't reach the result in time. Try again or check your profile.";

/**
 * AsyncStorage keys (kept centralized so a typo can't silently leak data
 * into the wrong namespace).
 */
export const PROFILE_DISMISSED_ERRORED_JOBS_STORAGE_KEY =
  "@nxme:dismissed_errored_jobs";

/**
 * Profile pending-cell polling cadence. Matches the result screen's
 * existing 2s poll so the result screen + a pending cell observing the
 * same job collapse to a single React Query observer (`['job', jobId]`)
 * and only one network request fires per 2s.
 */
export const PROFILE_PENDING_CELL_POLL_INTERVAL_MS = 2_000;

/**
 * Visible pending cells that may run a poll concurrently. The cap
 * bounds polling load — per-user entitlement usually caps lower
 * anyway (3 concurrent generations). Extras render a static shimmer
 * but don't poll until a slot frees.
 */
export const PROFILE_PENDING_CELL_MAX_VISIBLE = 3;

/**
 * Refund-toast dedup. The store remembers which job_ids have already
 * fired their toast so the user sees one banner per refunded job
 * across the device's lifetime — even after kill+relaunch.
 *
 * The cap bounds the persisted entry count; oldest entries fall off
 * first. 200 covers months of normal-cadence use given how rare
 * refunds are in steady state.
 */
export const REFUND_TOAST_SEEN_STORAGE_KEY = "@nxme:refund_toasts_seen";
export const REFUND_TOAST_SEEN_MAX_ENTRIES = 200;

/** Refund-toast copy. Unified noun ("credit") across status branches. */
export const REFUND_TOAST_FAILED =
  "That one's on us — your credit's back. Try a new photo?";
export const REFUND_TOAST_CANCELLED = "Cancelled — your credit's back.";

/** Errored-cell dismiss action sheet copy. */
export const DISMISS_ERRORED_JOB_TITLE = "Remove from profile?";
export const DISMISS_ERRORED_JOB_BODY =
  "Hides this glow-up from your grid on this device. The credit refund still stands.";
export const DISMISS_ERRORED_JOB_REMOVE_LABEL = "Remove from profile";
export const DISMISS_ERRORED_JOB_CANCEL_LABEL = "Cancel";

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

/**
 * Dev-only: when set, authenticated users land on this route instead of (tabs).
 * Set DEV_FEATURE_FOCUS=upload in mobile/.env to jump straight to the glow-up flow.
 * Always null in production (guarded by __DEV__ at call site).
 */
export const DEV_FEATURE_FOCUS: string | null =
  __DEV__ ? ((extra.devFeatureFocus as string) || null) : null;

/** Sentry DSN — empty disables crash reporting (warns in dev) */
export const SENTRY_DSN: string = process.env.EXPO_PUBLIC_SENTRY_DSN ?? "";

/** Validation constants */
export const AUTH_VALIDATION = {
  PASSWORD_MIN_LENGTH: 8,
  /** Password must contain lowercase + uppercase + digits (Supabase policy) */
  PASSWORD_PATTERN: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/,
  USERNAME_MIN_LENGTH: 3,
  USERNAME_MAX_LENGTH: 30,
  /** Alphanumeric + underscores, starts with letter */
  USERNAME_PATTERN: /^[a-zA-Z][a-zA-Z0-9_]*$/,
  EMAIL_PATTERN: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
} as const;
