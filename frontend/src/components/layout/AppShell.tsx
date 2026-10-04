import { useCallback, useState, type ReactNode } from "react";
import { Outlet } from "react-router";

import { useAudioPlayer } from "@/audio/context";
import { MiniPlayer } from "@/components/audio/MiniPlayer";
import { AddVideoDialog } from "@/components/video/AddVideoDialog";
import { useCanAdd } from "@/hooks/auth";
import { RemoteControlProvider } from "@/hooks/remoteControl";
import { cn } from "@/lib/cn";

import { AddVideoContext } from "./addVideo";
import { Sidebar } from "./Sidebar";
import { TabBar } from "./TabBar";

export function AppShell({ children }: { children?: ReactNode }) {
  const [adding, setAdding] = useState<{ url: string; key: number } | null>(null);
  // Buttons pass their click event; only strings count as a link to fill in.
  const canAdd = useCanAdd();
  const openAdd = useCallback(
    (url?: unknown) => {
      if (canAdd) setAdding({ url: typeof url === "string" ? url : "", key: Date.now() });
    },
    [canAdd],
  );
  const closeAdd = useCallback(() => setAdding(null), []);
  const listening = useAudioPlayer().track !== null;

  return (
    <RemoteControlProvider>
      <AddVideoContext.Provider value={openAdd}>
        <a
          href="#main"
          onClick={(event) => {
            // With <base href> a bare "#main" would lead to the start page instead.
            event.preventDefault();
            const main = document.getElementById("main");
            main?.focus();
            main?.scrollIntoView();
          }}
          className="sr-only z-50 rounded-full bg-accent-fill px-4 py-2 text-white focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
        >
          Zum Inhalt springen
        </a>
        <Sidebar onAdd={openAdd} />
        <main
          id="main"
          tabIndex={-1}
          className={cn(
            "min-h-dvh outline-none md:pl-60",
            // Room for the tab bar – and the mini player above it.
            listening
              ? "pb-[calc(10rem+env(safe-area-inset-bottom))] md:pb-28"
              : "pb-[calc(5rem+env(safe-area-inset-bottom))] md:pb-0",
          )}
        >
          <div className="mx-auto w-full max-w-[1680px] px-4 pt-[max(1.25rem,env(safe-area-inset-top))] sm:px-6 md:px-10 md:pt-10">
            {children ?? <Outlet />}
          </div>
        </main>
        <MiniPlayer aboveTabBar />
        <TabBar />
        <AddVideoDialog
          key={adding?.key ?? 0}
          open={adding != null}
          initialUrl={adding?.url}
          onClose={closeAdd}
        />
      </AddVideoContext.Provider>
    </RemoteControlProvider>
  );
}
