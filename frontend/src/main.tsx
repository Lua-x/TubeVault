import "./styles/index.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { ApiError } from "./lib/api";
import { applyTheme, storedTheme } from "./lib/theme";
import { reloadOnUpdate } from "./lib/updates";
import { AuthProvider } from "./hooks/auth";
import { ThemeProvider } from "./hooks/theme";
import { ToastProvider } from "./hooks/toast";

applyTheme(storedTheme());

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: true,
      retry: (count, error) =>
        !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 2,
    },
  },
});

if (import.meta.env.PROD) reloadOnUpdate();

// Installable app (PWA). Browsers only allow service workers on HTTPS or localhost.
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    // Relative to <base href>, so it also works below a BASE_PATH.
    navigator.serviceWorker.register("sw.js", { scope: "./" }).catch(() => undefined);
  });
}

const root = document.getElementById("root");
if (!root) throw new Error("#root missing");

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <MotionConfig reducedMotion="user">
        <AuthProvider>
          <ThemeProvider>
            <ToastProvider>
              <App />
            </ToastProvider>
          </ThemeProvider>
        </AuthProvider>
      </MotionConfig>
    </QueryClientProvider>
  </StrictMode>,
);
