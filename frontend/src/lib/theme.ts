import type { Theme } from "./types";

const STORAGE_KEY = "tubevault.theme";
const media = () => window.matchMedia("(prefers-color-scheme: light)");

export function storedTheme(): Theme {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    if (value === "system" || value === "dark" || value === "light") return value;
  } catch {
    // storage unavailable (private mode): fall back to the default
  }
  return "dark";
}

export function resolveTheme(theme: Theme): "dark" | "light" {
  if (theme === "system") return media().matches ? "light" : "dark";
  return theme;
}

export function applyTheme(theme: Theme): void {
  const resolved = resolveTheme(theme);
  document.documentElement.dataset.theme = resolved;
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", resolved === "light" ? "#f5f5f7" : "#000000");
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // ignore
  }
}

/** Re-applies "system" when the OS switches between light and dark. */
export function watchSystemTheme(getTheme: () => Theme): () => void {
  const query = media();
  const listener = () => {
    if (getTheme() === "system") applyTheme("system");
  };
  query.addEventListener("change", listener);
  return () => query.removeEventListener("change", listener);
}
