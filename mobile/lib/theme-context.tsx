/**
 * ThemeContext — provides the dynamic session theme to all screens.
 * On first mount, loads the persisted accent from storage so the accent
 * stays consistent across JS reloads within the same session.
 */
import { createContext, useContext, useEffect, useMemo, useState, useCallback, type ReactNode } from "react";
import {
  buildSessionTheme,
  loadOrCreateSessionTheme,
  persistAccentIndex,
  DEFAULT_THEME,
  hexToRgba,
  type DynamicTheme,
} from "./dynamic-theme";

/** Exact card-web accent palette — kept in sync with dynamic-theme.ts */
const ACCENTS = [
  "#F43F5E", "#14B8A6", "#D4A060", "#38BDF8", "#FB923C",
  "#6366F1", "#EF4444", "#A78BFA", "#F472B6", "#E879F9",
  "#34D399", "#F59E0B", "#EC4899", "#8B5CF6", "#10B981",
  "#0EA5E9", "#F97316", "#84CC16", "#E11D48", "#7C3AED",
] as const;

interface ThemeContextValue {
  theme: DynamicTheme;
  /** Regenerate a new random theme (e.g., on pull-to-refresh) */
  refreshTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: DEFAULT_THEME,
  refreshTheme: () => {},
});

export function ThemeProvider({ children }: { children: ReactNode }) {
  // Synchronous initial value so there is no flash on first render
  const [theme, setTheme] = useState<DynamicTheme>(() => buildSessionTheme());

  // On mount: replace with the persisted session accent (async)
  useEffect(() => {
    loadOrCreateSessionTheme().then(setTheme).catch(() => {
      // If loading fails, keep the synchronous initial value
    });
  }, []);

  const refreshTheme = useCallback(() => {
    const index = Math.floor(Math.random() * ACCENTS.length);
    const accent = ACCENTS[index] as string;
    const newTheme: DynamicTheme = {
      accent,
      accentMuted: hexToRgba(accent, 0.12),
      glowColors: [
        hexToRgba(accent, 0.18),
        hexToRgba(accent, 0.10),
        hexToRgba(accent, 0.06),
      ],
      glowShadow: hexToRgba(accent, 0.5),
    };
    setTheme(newTheme);
    persistAccentIndex(index).catch(() => {});
  }, []);

  const value = useMemo(() => ({ theme, refreshTheme }), [theme, refreshTheme]);

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
}

/** Hook to access the current dynamic theme */
export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}
