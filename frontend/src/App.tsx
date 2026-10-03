import { WifiOff } from "lucide-react";
import { motion } from "motion/react";
import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes, useLocation } from "react-router";

import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/Button";
import { PageSpinner } from "@/components/ui/Spinner";
import { useAuth } from "@/hooks/auth";
import { LiveEventsProvider } from "@/hooks/live";
import { ApiError } from "@/lib/api";
import { basePath } from "@/lib/base";
import { AudioPlayerProvider } from "@/audio/AudioPlayerProvider";
import { MiniPlayer } from "@/components/audio/MiniPlayer";
import { OfflineProvider } from "@/offline/OfflineProvider";
import { lastOwner } from "@/offline/progress";
import { ChannelPage } from "@/pages/ChannelPage";
import { ChannelsPage } from "@/pages/ChannelsPage";
import { DevicePage } from "@/pages/DevicePage";
import { DownloadsPage } from "@/pages/DownloadsPage";
import { AdminPage } from "@/pages/AdminPage";
import { HomePage } from "@/pages/HomePage";
import { ImportPage } from "@/pages/ImportPage";
import { LibraryPage } from "@/pages/LibraryPage";
import { LoginPage } from "@/pages/LoginPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { HistoryPage } from "@/pages/HistoryPage";
import { PlaylistPage, WatchLaterPage } from "@/pages/PlaylistPage";
import { PlaylistsPage } from "@/pages/PlaylistsPage";
import { SearchPage } from "@/pages/SearchPage";
import { SharePage } from "@/pages/SharePage";
import { SettingsPage } from "@/pages/SettingsPage";
import { SetupPage } from "@/pages/SetupPage";
import { SubscriptionPage } from "@/pages/SubscriptionPage";
import { SubscriptionsPage } from "@/pages/SubscriptionsPage";

// The player (video.js) is only loaded when a video is opened.
const VideoPage = lazy(() => import("@/pages/VideoPage").then((m) => ({ default: m.VideoPage })));
const DeviceVideoPage = lazy(() =>
  import("@/pages/DeviceVideoPage").then((m) => ({ default: m.DeviceVideoPage })),
);

function AnimatedRoutes() {
  const location = useLocation();
  return (
    <motion.div
      key={location.pathname}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
    >
      <Suspense fallback={<PageSpinner />}>
        <Routes location={location}>
          <Route path="/" element={<HomePage />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/channels" element={<ChannelsPage />} />
          <Route path="/channels/:id" element={<ChannelPage />} />
          <Route path="/playlists" element={<PlaylistsPage />} />
          <Route path="/playlists/:id" element={<PlaylistPage />} />
          <Route path="/later" element={<WatchLaterPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/videos/:id" element={<VideoPage />} />
          <Route path="/subscriptions" element={<SubscriptionsPage />} />
          <Route path="/subscriptions/:id" element={<SubscriptionPage />} />
          <Route path="/downloads" element={<DownloadsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/add" element={<SharePage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="/admin/import" element={<ImportPage />} />
          <Route path="/device" element={<DevicePage />} />
          <Route path="/device/:id" element={<DeviceVideoPage online />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Suspense>
    </motion.div>
  );
}

function ConnectionError({ message, retry }: { message: string; retry: () => void }) {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="text-[22px] font-semibold">Server nicht erreichbar</h1>
      <p className="max-w-sm text-[15px] text-secondary">{message}</p>
      <Button variant="secondary" onClick={retry}>
        Erneut versuchen
      </Button>
    </main>
  );
}

/** The server is out of reach: what's saved on this device still plays. */
function OfflineApp({ retry }: { retry: () => void }) {
  return (
    <BrowserRouter basename={basePath().replace(/\/$/, "") || "/"}>
      <OfflineProvider online={false} owner={lastOwner()}>
        <AudioPlayerProvider>
          <div className="sticky top-0 z-30 border-b border-separator bg-elevated/90 px-4 py-2.5 backdrop-blur-xl">
            <div className="mx-auto flex max-w-[1680px] items-center justify-between gap-3 text-[14px]">
              <span className="flex items-center gap-2 text-secondary">
                <WifiOff className="size-4 shrink-0" strokeWidth={2} />
                <span>
                  Keine Verbindung zum Server
                  <span className="hidden sm:inline"> – hier ist, was auf diesem Gerät liegt</span>
                </span>
              </span>
              <Button variant="secondary" size="sm" onClick={retry}>
                Neu verbinden
              </Button>
            </div>
          </div>
          <main className="mx-auto w-full max-w-[1680px] px-4 pt-6 pb-12 sm:px-6 md:px-10">
            <Suspense fallback={<PageSpinner />}>
              <Routes>
                <Route path="/device/:id" element={<DeviceVideoPage online={false} />} />
                <Route path="*" element={<DevicePage offlineMode />} />
              </Routes>
            </Suspense>
          </main>
          <MiniPlayer />
        </AudioPlayerProvider>
      </OfflineProvider>
    </BrowserRouter>
  );
}

export function App() {
  const { status, isLoading, error, user, refresh } = useAuth();

  if (isLoading) return <PageSpinner />;
  if (error instanceof ApiError && error.status === 0) {
    return <OfflineApp retry={() => void refresh()} />;
  }
  if (error || !status) {
    return (
      <ConnectionError
        message={error?.message ?? "Unbekannter Fehler"}
        retry={() => void refresh()}
      />
    );
  }
  if (status.setup_required) return <SetupPage />;
  if (!user) return <LoginPage />;

  return (
    <BrowserRouter basename={basePath().replace(/\/$/, "") || "/"}>
      <OfflineProvider online owner={user.id}>
        <AudioPlayerProvider>
          <LiveEventsProvider>
            <AppShell>
              <AnimatedRoutes />
            </AppShell>
          </LiveEventsProvider>
        </AudioPlayerProvider>
      </OfflineProvider>
    </BrowserRouter>
  );
}
