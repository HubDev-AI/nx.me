/**
 * ThemeContext — provides the dynamic session theme to all screens.
 * Every JS reload (cold start, Fast Refresh, shake-menu reload) picks a
 * fresh random accent. No cross-reload persistence — `refreshTheme()`
 * rotates the accent in-memory only.
 */
import { createContext, useContext, useMemo, useState, useCallback, type ReactNode } from "react";
import {
  buildSessionTheme,
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
  // Synchronous initial value — fresh random accent on every mount.
  const [theme, setTheme] = useState<DynamicTheme>(() => buildSessionTheme());

  const refreshTheme = useCallback(() => {
    const index = Math.floor(Math.random() * ACCENTS.length);
    const accent = ACCENTS[index] as string;
    setTheme({
      accent,
      accentMuted: hexToRgba(accent, 0.12),
      glowColors: [
        hexToRgba(accent, 0.18),
        hexToRgba(accent, 0.10),
        hexToRgba(accent, 0.06),
      ],
      glowShadow: hexToRgba(accent, 0.5),
    });
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
