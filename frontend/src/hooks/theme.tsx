import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { applyTheme, storedTheme, watchSystemTheme } from "@/lib/theme";
import type { Theme } from "@/lib/types";

import { useAuth } from "./auth";

interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const { user, updatePreferences } = useAuth();
  const [theme, setThemeState] = useState<Theme>(storedTheme);

  // The account's preference wins once we know who is signed in.
  const accountTheme = user?.preferences.theme;
  const [syncedFrom, setSyncedFrom] = useState<Theme | undefined>(undefined);
  if (accountTheme && accountTheme !== syncedFrom) {
    setSyncedFrom(accountTheme);
    setThemeState(accountTheme);
  }

  useEffect(() => applyTheme(theme), [theme]);
  useEffect(() => watchSystemTheme(() => theme), [theme]);

  const setTheme = useCallback(
    (next: Theme) => {
      setThemeState(next);
      setSyncedFrom(next);
      if (user) void updatePreferences({ theme: next }).catch(() => undefined);
    },
    [user, updatePreferences],
  );

  return <ThemeContext.Provider value={{ theme, setTheme }}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used inside <ThemeProvider>");
  return ctx;
}
