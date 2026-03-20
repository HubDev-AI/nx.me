/**
 * ThemeContext — provides the dynamic session theme to all screens.
 * A new random accent is picked on each cold start.
 */
import { createContext, useContext, useMemo, useState, useCallback, type ReactNode } from "react";
import { buildSessionTheme, DEFAULT_THEME, type DynamicTheme } from "./dynamic-theme";

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
  const [theme, setTheme] = useState<DynamicTheme>(() => buildSessionTheme());

  const refreshTheme = useCallback(() => {
    setTheme(buildSessionTheme());
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
