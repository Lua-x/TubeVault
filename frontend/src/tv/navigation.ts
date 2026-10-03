import { useEffect } from "react";
import { useLocation } from "react-router";

import { directionOf, pickNext, type Box } from "./spatial";

const STORE_KEY = "tubevault.tv.focus";
const BACK_KEYS = new Set(["Escape", "Backspace", "GoBack", "BrowserBack"]);

/** User agents of TVs, sticks and consoles – they land in the TV view on their own. */
const TV_AGENT =
  /SMART-?TV|SmartTV|Tizen|Web0S|webOS|NetCast|BRAVIA|AFT[A-Z]|Android TV|GoogleTV|CrKey|AppleTV|HbbTV|Viera|PlayStation|Xbox/i;
const VIEW_KEY = "tubevault.view";

export function isTvBrowser(): boolean {
  return typeof navigator !== "undefined" && TV_AGENT.test(navigator.userAgent);
}

/** "tv" or "standard" once chosen, else null. */
export function chosenView(): string | null {
  try {
    return localStorage.getItem(VIEW_KEY);
  } catch {
    return null;
  }
}

export function chooseView(view: "tv" | "standard"): void {
  try {
    localStorage.setItem(VIEW_KEY, view);
  } catch {
    // not remembered
  }
}

const box = (element: Element): Box => {
  const rect = element.getBoundingClientRect();
  return { left: rect.left, top: rect.top, width: rect.width, height: rect.height };
};

function focusables(): HTMLElement[] {
  return [...document.querySelectorAll<HTMLElement>("[data-tv-focus]")];
}

function remembered(pathname: string): string | null {
  try {
    const all = JSON.parse(sessionStorage.getItem(STORE_KEY) ?? "{}") as Record<string, string>;
    return all[pathname] ?? null;
  } catch {
    return null;
  }
}

function remember(pathname: string, key: string): void {
  try {
    const all = JSON.parse(sessionStorage.getItem(STORE_KEY) ?? "{}") as Record<string, string>;
    sessionStorage.setItem(STORE_KEY, JSON.stringify({ ...all, [pathname]: key }));
  } catch {
    // focus just isn't restored
  }
}

/**
 * Arrow keys move the focus between `[data-tv-focus]` elements; the back key goes back.
 * The focus of each page is remembered, so returning lands where you left.
 */
export function useTvNavigation({ onBack }: { onBack?: () => void } = {}) {
  const { pathname } = useLocation();

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const active = document.activeElement as HTMLElement | null;
      if (BACK_KEYS.has(event.key) && onBack) {
        if (event.key === "Backspace" && active?.matches("input, textarea")) return;
        event.preventDefault();
        onBack();
        return;
      }
      const direction = directionOf(event.key);
      if (!direction || active?.closest(".video-js")) return;
      const items = focusables();
      if (items.length === 0) return;
      event.preventDefault();
      if (!active || !items.includes(active)) {
        items[0]?.focus();
        return;
      }
      const others = items.filter((item) => item !== active);
      const next = others[pickNext(box(active), others.map(box), direction)];
      if (!next) return;
      next.focus({ preventScroll: true });
      next.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
    };
    const onFocus = (event: FocusEvent) => {
      const key = (event.target as HTMLElement | null)?.dataset?.tvKey;
      if (key) remember(pathname, key);
    };
    window.addEventListener("keydown", onKey);
    document.addEventListener("focusin", onFocus);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("focusin", onFocus);
    };
  }, [pathname, onBack]);
}

/** Puts the focus back where it was on this page – or on the first tile. */
export function useInitialFocus(ready: boolean) {
  const { pathname } = useLocation();
  useEffect(() => {
    if (!ready) return;
    const key = remembered(pathname);
    // Remembered tile, else the first video (not the header buttons), else anything.
    const target =
      (key && document.querySelector<HTMLElement>(`[data-tv-key="${CSS.escape(key)}"]`)) ||
      document.querySelector<HTMLElement>('[data-tv-focus][data-tv-key^="video-"]') ||
      focusables()[0];
    target?.focus({ preventScroll: true });
    target?.scrollIntoView({ block: "center", inline: "nearest" });
  }, [ready, pathname]);
}
