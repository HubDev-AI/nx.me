/**
 * Dynamic Theme — matches card-web's accent rotation exactly.
 * 20 accent colors, randomly picked per session.
 * Same palette as card-web/src/components/theme-provider.tsx.
 */
import { Platform } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";

/** Exact card-web accent palette */
const ACCENTS = [
  "#F43F5E", "#14B8A6", "#D4A060", "#38BDF8", "#FB923C",
  "#6366F1", "#EF4444", "#A78BFA", "#F472B6", "#E879F9",
  "#34D399", "#F59E0B", "#EC4899", "#8B5CF6", "#10B981",
  "#0EA5E9", "#F97316", "#84CC16", "#E11D48", "#7C3AED",
] as const;

const ACCENT_STORAGE_KEY = "nxme_session_accent";

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

export async function loadOrCreateSessionTheme(): Promise<DynamicTheme> {
  // On web, AsyncStorage is not reliable — just use a random theme
  if (Platform.OS === "web") {
    return buildSessionTheme();
  }

  try {
    const stored = await AsyncStorage.getItem(ACCENT_STORAGE_KEY);
    if (stored !== null) {
      const index = parseInt(stored, 10);
      if (!isNaN(index) && index >= 0 && index < ACCENTS.length) {
        return buildThemeFromIndex(index);
      }
    }
  } catch {
    // Storage read failed — fall through to create a new one
  }

  // No stored accent (or invalid) — pick a random one and persist it
  const index = Math.floor(Math.random() * ACCENTS.length);
  try {
    await AsyncStorage.setItem(ACCENT_STORAGE_KEY, String(index));
  } catch {
    // Storage write failed — continue with the randomly picked theme
  }
  return buildThemeFromIndex(index);
}

export async function persistAccentIndex(index: number): Promise<void> {
  if (Platform.OS === "web") return;
  try {
    await AsyncStorage.setItem(ACCENT_STORAGE_KEY, String(index));
  } catch {
    // ignore
  }
}

export const DEFAULT_THEME: DynamicTheme = {
  accent: "#F43F5E",
  accentMuted: "rgba(244, 63, 94, 0.12)",
  glowColors: ["rgba(244, 63, 94, 0.18)", "rgba(244, 63, 94, 0.10)", "rgba(244, 63, 94, 0.06)"],
  glowShadow: "rgba(244, 63, 94, 0.5)",
};
