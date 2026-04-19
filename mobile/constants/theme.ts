/**
 * Global Theme Constants — single source of truth for all visual styling.
 * Every component should import from here, never use inline magic values.
 *
 * This file defines the STATIC design tokens. For the dynamic session accent,
 * use useTheme() from lib/theme-context.
 */
import { StyleSheet } from "react-native";
import { FONTS } from "../hooks/useFonts";

// ─── Colors ──────────────────────────────────────────────────────────────────

export const THEME = {
  colors: {
    bg: "#0a0a0a",
    surface: "#111111",
    surfaceElevated: "#1a1a1a",
    border: "rgba(255, 255, 255, 0.06)",
    borderFocused: "rgba(255, 255, 255, 0.25)",
    textPrimary: "#e8e8e8",
    textSecondary: "#888888",
    textMuted: "#555555",
    textDisabled: "#444444",
    destructive: "#ef4444",
    white: "#ffffff",
    /** Background image overlay — applied on pages with hero/bg images */
    bgImageOverlay: "rgba(10, 10, 10, 0.55)",
    /** Glass surface — semi-transparent for frosted effects */
    glass: "rgba(17, 17, 17, 0.75)",
    glassBorder: "rgba(255, 255, 255, 0.08)",
    /** Subtle glass — lighter, for cards over images */
    glassLight: "rgba(17, 17, 17, 0.55)",
    /** Modal scrim base color (combine with backdrop opacity) */
    backdrop: "#000000",
    /** Hairline top border on bottom-sheet modals (matches EditProfileSheet) */
    sheetTopBorder: "rgba(255, 255, 255, 0.1)",
    /** Destructive notification background (10% destructive red) */
    destructiveBg: "rgba(239, 68, 68, 0.1)",
    /** Success notification background (10% success green) */
    successBg: "rgba(74, 222, 128, 0.1)",
    /** Amber-gold credit/diamond accent — used for credit pack icons */
    creditAccent: "#F59E0B",
  },

  /**
   * Hex alpha suffixes for compositing 8-digit hex colors.
   * Append to a 6-digit hex string (e.g. `theme.accent + THEME.alpha.subtle`).
   */
  alpha: {
    /** ~15% — subtle accent fill (badge background) */
    subtle: "26",
    /** ~20% — low accent fill (badge border) */
    low: "33",
    /** ~25% — medium accent fill (premium card border) */
    med: "40",
    /** ~38% — mid accent fill (active pack card border) */
    mid: "60",
  },

  radius: {
    sm: 8,
    md: 12,
    lg: 16,
    xl: 20,
    pill: 9999,
  },

  spacing: {
    xs: 4,
    sm: 8,
    md: 12,
    lg: 16,
    xl: 20,
    xxl: 24,
    xxxl: 32,
  },

  shadow: {
    card: {
      shadowColor: "rgba(0, 0, 0, 0.3)",
      shadowOffset: { width: 0, height: 4 },
      shadowOpacity: 1,
      shadowRadius: 12,
      elevation: 4,
    },
    glass: {
      shadowColor: "rgba(0, 0, 0, 0.2)",
      shadowOffset: { width: 0, height: 2 },
      shadowOpacity: 1,
      shadowRadius: 8,
      elevation: 2,
    },
    glow: (color: string) => ({
      shadowColor: color,
      shadowOffset: { width: 0, height: 0 },
      shadowOpacity: 0.3,
      shadowRadius: 12,
      elevation: 4,
    }),
  },

  typography: {
    /** Body text: 1.5x line-height, slight positive letter-spacing */
    body: { fontSize: 15, lineHeight: 23, letterSpacing: 0.15 },
    /** Caption/secondary */
    caption: { fontSize: 13, lineHeight: 18, letterSpacing: 0.3 },
    /** Heading — tighter line-height, negative letter-spacing */
    heading: { fontSize: 22, lineHeight: 28, letterSpacing: -0.3 },
    /** Large heading */
    headingLg: { fontSize: 28, lineHeight: 34, letterSpacing: -0.5 },
  },

  opacity: {
    textPrimary: 0.87,
    textSecondary: 0.55,
    textTertiary: 0.33,
    textDisabled: 0.20,
    border: 0.08,
    surface: 0.05,
    icon: 0.15,
  },

  animation: {
    press: { damping: 15, stiffness: 200 },
    quick: { damping: 20, stiffness: 300 },
    slow: { damping: 12, stiffness: 100 },
    duration: {
      instant: 150,
      fast: 200,
      normal: 300,
      /**
       * Reserved for celebratory / first-time surfaces only (e.g. glow-up
       * reveal). Never use for recurring UI — keep recurring animations
       * at or below `normal` (300ms) so the interface stays responsive.
       */
      celebration: 500,
    },
  },
} as const;

// ─── Shared Styles ───────────────────────────────────────────────────────────

export const sharedStyles = StyleSheet.create({
  /** Glass card — used for cards, inputs, overlays */
  glassCard: {
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.lg,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
  },

  /** Surface card — solid dark card */
  surfaceCard: {
    backgroundColor: THEME.colors.surface,
    borderRadius: THEME.radius.lg,
    borderWidth: 1,
    borderColor: THEME.colors.border,
  },

  /** Pill button base */
  pillButton: {
    borderRadius: THEME.radius.pill,
    alignItems: "center" as const,
    justifyContent: "center" as const,
    minHeight: 48,
    paddingHorizontal: 24,
  },

  /** Pill button text — dark on accent */
  pillButtonText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 16,
    color: THEME.colors.bg,
  },

  /** Outline pill button */
  outlinePillButton: {
    borderRadius: THEME.radius.pill,
    borderWidth: 1,
    borderColor: THEME.colors.borderFocused,
    alignItems: "center" as const,
    justifyContent: "center" as const,
    minHeight: 48,
    paddingHorizontal: 24,
  },

  /** Background image overlay */
  bgOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: THEME.colors.bgImageOverlay,
  },

  /** Page container */
  page: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
  },

  /** Section title — Instrument Serif */
  sectionTitle: {
    fontFamily: FONTS.display,
    fontSize: 28,
    color: THEME.colors.textPrimary,
  },

  /** Section subtitle — Inter */
  sectionSubtitle: {
    fontFamily: FONTS.body,
    fontSize: 15,
    color: THEME.colors.textSecondary,
  },

  /** Small uppercase label — magazine style */
  label: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 11,
    color: THEME.colors.textSecondary,
    letterSpacing: 1,
    textTransform: "uppercase" as const,
  },
});
