/**
 * NXME Design Tokens — sourced from colors.tokens.json.
 * Dark-first. Before/After dual-accent architecture.
 */

export const COLORS = {
  /** Coral/Rose — CTAs, reveals, active states, glow-up moments */
  after: {
    50: "#FFF1F3",
    100: "#FFE4E8",
    200: "#FECDD5",
    300: "#FDA4B4",
    400: "#FB7091",
    500: "#F43F5E", // primary CTA
    600: "#E11D48", // hover
    700: "#BE123C", // active/pressed
    800: "#9F1239",
    900: "#881337",
  },
  /** Slate — inactive, subdued, before-state */
  before: {
    400: "#94A3B8", // accent-before dark
    500: "#64748B",
    600: "#475569", // accent-before light
  },
  neutral: {
    dark: {
      0: "#0a0a0a",     // page background — exact card-web value
      50: "#0F0F0F",
      100: "#111111",   // card background — card-web surface.card
      150: "#181818",   // input fill — card-web surface.elevated
      200: "#1f1f1f",   // elevated surface — card-web surface.subtle
      300: "#222222",   // hover fill
      400: "#333333",   // subtle border — card-web divider color
      500: "#444444",   // strong border — card-web content.disabled
      600: "#555555",   // disabled text
      700: "#888888",   // secondary text — exact card-web content.secondary
      800: "#cccccc",   // card-web recommendation text
      900: "#e8e8e8",   // primary text — exact card-web content.primary
    },
    light: {
      0: "#FFFFFF",     // card background
      50: "#F9F9F9",    // page background
      100: "#F2F2F2",   // hover fill
      300: "#E5E5E5",   // subtle border
      400: "#D1D1D1",   // strong border
      600: "#9CA3AF",   // disabled text
      700: "#6B7280",   // secondary text
      900: "#111111",   // primary text
    },
  },
} as const;

/** Active tab accent — coral 500 */
export const TAB_ACTIVE_COLOR = COLORS.after[500];

/** Inactive tab color — secondary text dark */
export const TAB_INACTIVE_COLOR = COLORS.neutral.dark[700];

/** Dark background */
export const BG_PAGE = COLORS.neutral.dark[0];
export const BG_CARD = COLORS.neutral.dark[100];
export const BG_ELEVATED = COLORS.neutral.dark[200];

/** Text colors */
export const TEXT_PRIMARY = COLORS.neutral.dark[900];
export const TEXT_SECONDARY = COLORS.neutral.dark[700];
export const TEXT_DISABLED = COLORS.neutral.dark[600];

/** Input */
export const INPUT_FILL = COLORS.neutral.dark[150];
export const BORDER_DEFAULT = COLORS.neutral.dark[400];
export const BORDER_STRONG = COLORS.neutral.dark[500];

/** CTA / Accent */
export const CTA_PRIMARY = COLORS.after[500];
export const CTA_PRESSED = COLORS.after[600];
export const CTA_ACTIVE = COLORS.after[700];

/** Feed-specific tokens */
export const FEED_DIVIDER = "rgba(255,255,255,0.05)";
export const BEFORE_OVERLAY = "rgba(15,23,42,0.72)";

/** Reveal / Glow-up */
export const GLOW_AMBER = "#FF8C42";
export const AFTER_OVERLAY = "rgba(244, 63, 94, 0.08)";

/** After-state label overlay — 72% opacity for feed card labels */
export const AFTER_OVERLAY_STRONG = "rgba(244, 63, 94, 0.72)";

/** Credit Badge — amber-gold accent */
export const CREDIT_BADGE_BG = "rgba(245,158,11,0.15)";
export const CREDIT_BADGE_TEXT = "#FCD34D";
export const CREDIT_BADGE_ICON = "#F59E0B";

/** Advisor — Ada bubble styling */
export const ADA_BUBBLE_BG = COLORS.neutral.dark[150];
export const ADA_BUBBLE_BORDER = COLORS.after[500];
export const USER_BUBBLE_BG = "rgba(244,63,94,0.08)";
export const NUDGE_UNREAD_DOT = COLORS.after[500];

/** Feedback */
export const ERROR_DARK = "#F87171";
export const ERROR_LIGHT = "#DC2626";
export const SUCCESS_DARK = "#4ADE80";

/** Inverse / Scrim */
export const TEXT_INVERSE = "#FFFFFF";
export const SCRIM_BG = "#000000";

/** Social login brand colors */
export const SOCIAL_GOOGLE_BLUE = "#4285F4";
export const SOCIAL_GOOGLE_BORDER = "#DADCE0";
export const SOCIAL_GOOGLE_TEXT = "#1F1F1F";

/** Common rgba tokens */
export const ERROR_BG = "rgba(248,113,113,0.1)";
export const CORAL_TINT = "rgba(244,63,94,0.08)";
export const CORAL_TINT_STRONG = "rgba(244,63,94,0.12)";
export const SKELETON_SHIMMER = "rgba(255,255,255,0.05)";
export const SUCCESS_BG = "rgba(74,222,128,0.1)";
export const OVERLAY_LIGHT = "rgba(0,0,0,0.4)";
export const OVERLAY_MEDIUM = "rgba(0,0,0,0.6)";
export const OVERLAY_HEAVY = "rgba(0,0,0,0.95)";

/** Auth / form tokens */
export const AUTH_INPUT_BG = "rgba(8, 8, 8, 0.78)";
export const TEXT_SHADOW_DARK = "rgba(0, 0, 0, 0.4)";
export const TEXT_MUTED = "rgba(255, 255, 255, 0.7)";
export const ERROR_BORDER = "rgba(239, 68, 68, 0.2)";

/** Tab bar tokens */
export const TAB_BAR_BG = "rgba(17, 17, 17, 0.85)";
export const TAB_BAR_BORDER = "rgba(255, 255, 255, 0.08)";
export const TAB_BAR_GLOW = "rgba(255, 255, 255, 0.1)";
export const SCROLL_TOP_BG = "rgba(10, 10, 10, 0.95)";
