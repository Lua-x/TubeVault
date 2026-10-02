import { motion } from "motion/react";
import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes, useLocation } from "react-router";

import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/Button";
import { PageSpinner } from "@/components/ui/Spinner";
import { useAuth } from "@/hooks/auth";
import { LiveEventsProvider } from "@/hooks/live";
import { basePath } from "@/lib/base";
import { ChannelPage } from "@/pages/ChannelPage";
import { ChannelsPage } from "@/pages/ChannelsPage";
import { DownloadsPage } from "@/pages/DownloadsPage";
import { HomePage } from "@/pages/HomePage";
import { LibraryPage } from "@/pages/LibraryPage";
import { LoginPage } from "@/pages/LoginPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { PlaylistPage } from "@/pages/PlaylistPage";
import { PlaylistsPage } from "@/pages/PlaylistsPage";
import { SearchPage } from "@/pages/SearchPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { SetupPage } from "@/pages/SetupPage";
import { SubscriptionPage } from "@/pages/SubscriptionPage";
import { SubscriptionsPage } from "@/pages/SubscriptionsPage";

// The player (video.js) is only loaded when a video is opened.
const VideoPage = lazy(() => import("@/pages/VideoPage").then((m) => ({ default: m.VideoPage })));

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
          <Route path="/videos/:id" element={<VideoPage />} />
          <Route path="/subscriptions" element={<SubscriptionsPage />} />
          <Route path="/subscriptions/:id" element={<SubscriptionPage />} />
          <Route path="/downloads" element={<DownloadsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
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

export function App() {
  const { status, isLoading, error, user, refresh } = useAuth();

  if (isLoading) return <PageSpinner />;
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
      <LiveEventsProvider>
        <AppShell>
          <AnimatedRoutes />
        </AppShell>
      </LiveEventsProvider>
    </BrowserRouter>
  );
}
