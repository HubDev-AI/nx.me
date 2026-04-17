/**
 * Dynamic Theme — matches card-web's accent rotation exactly.
 * 20 accent colors, randomly picked per session. No persistence:
 * every cold start / reload picks a fresh accent.
 * Same palette as card-web/src/components/theme-provider.tsx.
 */

/** Exact card-web accent palette */
const ACCENTS = [
  "#F43F5E", "#14B8A6", "#D4A060", "#38BDF8", "#FB923C",
  "#6366F1", "#EF4444", "#A78BFA", "#F472B6", "#E879F9",
  "#34D399", "#F59E0B", "#EC4899", "#8B5CF6", "#10B981",
  "#0EA5E9", "#F97316", "#84CC16", "#E11D48", "#7C3AED",
] as const;

export interface DynamicTheme {
  accent: string;
  accentMuted: string;
  glowColors: [string, string, string];
  glowShadow: string;
}

export function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function buildThemeFromIndex(index: number): DynamicTheme {
  const accent = ACCENTS[index % ACCENTS.length] as string;
  return {
    accent,
    accentMuted: hexToRgba(accent, 0.12),
    glowColors: [
      hexToRgba(accent, 0.18),
      hexToRgba(accent, 0.10),
      hexToRgba(accent, 0.06),
    ],
    glowShadow: hexToRgba(accent, 0.5),
  };
}

export function buildSessionTheme(): DynamicTheme {
  const index = Math.floor(Math.random() * ACCENTS.length);
  return buildThemeFromIndex(index);
}

export const DEFAULT_THEME: DynamicTheme = {
  accent: "#F43F5E",
  accentMuted: "rgba(244, 63, 94, 0.12)",
  glowColors: ["rgba(244, 63, 94, 0.18)", "rgba(244, 63, 94, 0.10)", "rgba(244, 63, 94, 0.06)"],
  glowShadow: "rgba(244, 63, 94, 0.5)",
};
