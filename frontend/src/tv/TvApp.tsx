import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef } from "react";
import { Route, Routes, useNavigate, useParams, useSearchParams } from "react-router";

import {
  keys,
  reportProgress,
  useChannel,
  useHome,
  usePlaylist,
  usePlaylists,
  useVideo,
  useVideos,
} from "@/api/queries";
import { PageSpinner } from "@/components/ui/Spinner";
import { PlaybackStatus } from "@/components/video/QualityMenu";
import { VideoPlayer } from "@/components/video/VideoPlayer";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { useAuth } from "@/hooks/auth";
import { useChannelRate } from "@/hooks/useChannelRate";
import { usePlaybackSource } from "@/hooks/usePlaybackSource";
import type { VideoDetail, VideoSummary } from "@/lib/types";

import { chooseView, useInitialFocus, useTvNavigation } from "./navigation";
import { TvChannelTile, TvPlaylistTile, TvRow, TvVideoTile } from "./TvTile";

const MIN_RESUME_S = 10;

function TvShell({ children }: { children: React.ReactNode }) {
  return (
    <main className="min-h-dvh bg-canvas px-[4vw] pt-[3vw] pb-[5vw] text-primary">{children}</main>
  );
}

function TvHome() {
  useDocumentTitle("TubeVault");
  const navigate = useNavigate();
  const { data: home } = useHome();
  const { data: playlists } = usePlaylists();
  useTvNavigation();
  useInitialFocus(Boolean(home));
  if (!home) return <PageSpinner />;

  const rows: [string, VideoSummary[]][] = [
    ["Weiterschauen", home.continue_watching],
    ["Später ansehen", home.watch_later ?? []],
    ["Neu von deinen Abos", home.from_subscriptions],
    [
      home.from_subscriptions.length ? "Von dir hinzugefügt" : "Zuletzt hinzugefügt",
      home.recently_added,
    ],
  ];
  return (
    <TvShell>
      <header className="flex items-center justify-between">
        <h1 className="flex items-center gap-3 text-[max(24px,2vw)] font-bold tracking-tight">
          <img src="favicon.svg" alt="" className="size-[max(2rem,2.4vw)]" />
          TubeVault
        </h1>
        <button
          type="button"
          data-tv-focus
          data-tv-key="standard-view"
          onClick={() => {
            chooseView("standard");
            navigate("/");
          }}
          className="rounded-full bg-surface px-[1.4vw] py-[0.6vw] text-[max(15px,1vw)] font-medium text-secondary outline-none focus:bg-primary focus:text-canvas"
        >
          Normale Ansicht
        </button>
      </header>
      {rows.map(
        ([title, videos]) =>
          videos.length > 0 && (
            <TvRow key={title} title={title}>
              {videos.map((video) => (
                <TvVideoTile key={video.id} video={video} to={`/tv/play/${video.id}`} />
              ))}
            </TvRow>
          ),
      )}
      {home.channels.length > 0 && (
        <TvRow title="Kanäle">
          {home.channels.map((channel) => (
            <TvChannelTile key={channel.id} channel={channel} />
          ))}
        </TvRow>
      )}
      {playlists && playlists.some((p) => p.video_count > 0) && (
        <TvRow title="Playlists">
          {playlists
            .filter((p) => p.video_count > 0)
            .map((playlist) => (
              <TvPlaylistTile key={playlist.id} playlist={playlist} />
            ))}
        </TvRow>
      )}
    </TvShell>
  );
}

function TvGrid({
  title,
  subtitle,
  videos,
  link,
}: {
  title: string;
  subtitle?: string;
  videos: VideoSummary[] | undefined;
  link: (video: VideoSummary) => string;
}) {
  const navigate = useNavigate();
  const back = useCallback(() => navigate(-1), [navigate]);
  useTvNavigation({ onBack: back });
  useInitialFocus(videos !== undefined);
  useDocumentTitle(title);
  if (!videos) return <PageSpinner />;
  return (
    <TvShell>
      <h1 className="text-[max(30px,2.8vw)] font-bold tracking-tight">{title}</h1>
      {subtitle && <p className="mt-1 text-[max(16px,1.2vw)] text-secondary">{subtitle}</p>}
      <div className="mt-[2.5vw] flex flex-wrap gap-x-[1.6vw] gap-y-[2.5vw]">
        {videos.map((video) => (
          <TvVideoTile key={video.id} video={video} to={link(video)} />
        ))}
      </div>
      {videos.length === 0 && (
        <p className="mt-10 text-[max(18px,1.3vw)] text-secondary">Hier gibt es noch nichts.</p>
      )}
    </TvShell>
  );
}

function TvChannel() {
  const channelId = Number(useParams().id);
  const { data: channel } = useChannel(channelId);
  const { data: page } = useVideos({ channelId, sort: "newest", limit: 120 });
  return (
    <TvGrid
      title={channel?.name ?? "Kanal"}
      subtitle={channel ? `${channel.video_count} Videos` : undefined}
      videos={page?.items}
      link={(video) => `/tv/play/${video.id}`}
    />
  );
}

function TvPlaylist() {
  const playlistId = Number(useParams().id);
  const { data: playlist } = usePlaylist(playlistId);
  return (
    <TvGrid
      title={playlist?.name ?? "Playlist"}
      subtitle={playlist ? `${playlist.video_count} Videos` : undefined}
      videos={playlist?.videos}
      link={(video) => `/tv/play/${video.id}?list=${playlistId}`}
    />
  );
}

function TvPlayerView({ video, listId }: { video: VideoDetail; listId: number | null }) {
  const navigate = useNavigate();
  const client = useQueryClient();
  const playback = usePlaybackSource(video);
  const { data: list } = usePlaylist(listId);
  const container = useRef<HTMLElement>(null);
  const [channelRate, saveChannelRate] = useChannelRate(video.channel?.id);
  const { user } = useAuth();
  useDocumentTitle(video.title);
  const index = list?.videos.findIndex((v) => v.id === video.id) ?? -1;
  const next = list && index >= 0 ? list.videos[index + 1] : undefined;
  const progress = video.progress;
  const startAt =
    progress && !progress.watched && progress.position_s >= MIN_RESUME_S
      ? progress.position_s
      : undefined;

  const back = useCallback(() => navigate(-1), [navigate]);
  useTvNavigation({ onBack: back });

  useEffect(() => {
    // Keys go to the player: OK pauses, left/right seek.
    const timer = window.setTimeout(() => {
      container.current?.querySelector<HTMLElement>(".video-js")?.focus();
    }, 300);
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Enter" && event.key !== "MediaPlayPause") return;
      const media = container.current?.querySelector("video");
      if (!media) return;
      event.preventDefault();
      if (media.paused) void media.play();
      else media.pause();
    };
    window.addEventListener("keydown", onKey, true);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("keydown", onKey, true);
    };
  }, []);

  return (
    <main ref={container} className="fixed inset-0 bg-black">
      <h1 className="sr-only">{video.title}</h1>
      <VideoPlayer
        video={video}
        source={playback.source}
        onSourceError={playback.onSourceError}
        startAt={startAt}
        autoplay
        playbackRate={channelRate}
        onRateChange={saveChannelRate}
        normalizeVolume={user?.preferences.normalize_volume !== false}
        onSave={(position, duration, reason) => {
          void reportProgress(video.id, position, duration).then(() => {
            if (reason === "unmount" || reason === "ended") {
              void client.invalidateQueries({ queryKey: keys.videos });
            }
          });
        }}
        onEnded={() => {
          if (next) navigate(`/tv/play/${next.id}?list=${listId}`, { replace: true });
          else navigate(-1);
        }}
        overlay={
          <PlaybackStatus
            preparing={playback.preparing}
            error={playback.error}
            onRetry={playback.retry}
          />
        }
      />
    </main>
  );
}

function TvPlayer() {
  const videoId = Number(useParams().id);
  const [params] = useSearchParams();
  const listId = Number(params.get("list")) || null;
  const { data: video } = useVideo(videoId);
  if (!video) return <PageSpinner />;
  return <TvPlayerView key={video.id} video={video} listId={listId} />;
}

/** The view for TVs: big tiles, everything reachable with the arrow keys of a remote. */
export function TvApp() {
  return (
    <Routes>
      <Route index element={<TvHome />} />
      <Route path="channels/:id" element={<TvChannel />} />
      <Route path="playlists/:id" element={<TvPlaylist />} />
      <Route path="play/:id" element={<TvPlayer />} />
    </Routes>
  );
}
