import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Captions,
  Check,
  CircleCheck,
  Clock,
  Download,
  ExternalLink,
  FolderPlus,
  HardDriveDownload,
  Headphones,
  ListPlus,
  RefreshCw,
  Trash2,
  Tv2,
  UsersRound,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router";

import {
  keys,
  reportProgress,
  useCreateParty,
  useDeleteVideo,
  useRedownloadVideo,
  usePlaylist,
  useSegments,
  useSetWatched,
  useSpeechState,
  useSpeechSubtitles,
  useToggleWatchLater,
  useVideo,
  useWatchLater,
} from "@/api/queries";
import { trackFromVideo, useAudioPlayer } from "@/audio/context";
import { AddToFolderDialog } from "@/components/folders/AddToFolderDialog";
import { AddToPlaylistDialog } from "@/components/playlists/AddToPlaylistDialog";
import { Comments } from "@/components/comments/Comments";
import { PlaylistPanel } from "@/components/playlists/PlaylistPanel";
import { ChannelAvatar } from "@/components/subscriptions/ChannelAvatar";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageSpinner } from "@/components/ui/Spinner";
import { PlayerOverlay, type PlayerNotice, type UpNext } from "@/components/video/PlayerOverlay";
import { PlaybackStatus, QualityMenu } from "@/components/video/QualityMenu";
import { SleepMenu } from "@/components/video/SleepMenu";
import { RichText } from "@/components/video/RichText";
import { SimilarVideos } from "@/components/video/SimilarVideos";
import { SaveToDevice } from "@/components/offline/SaveToDevice";
import { MoreMenu } from "@/components/ui/MoreMenu";
import { VideoPlayer, type PlayerHandle, type SaveReason } from "@/components/video/VideoPlayer";
import { useAuth } from "@/hooks/auth";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { useRemoteControl } from "@/hooks/remoteControl";
import { useChannelRate } from "@/hooks/useChannelRate";
import { usePlaybackSource } from "@/hooks/usePlaybackSource";
import { useToast } from "@/hooks/toast";
import { setVideoSleep, useVideoSleep, videoSleep } from "@/lib/sleepTimer";
import { useOffline } from "@/offline/context";
import { apiUrl } from "@/lib/base";
import { cn } from "@/lib/cn";
import {
  codecLabel,
  formatBytes,
  formatCount,
  formatDate,
  formatDuration,
  formatResolution,
} from "@/lib/format";
import { categoryLabel } from "@/lib/sponsorblock";
import type { SponsorSegment, VideoDetail } from "@/lib/types";

const MIN_RESUME_S = 10;
const UP_NEXT_SECONDS = 5;

interface LocationState {
  autoplay?: boolean;
}

/** Where to continue: unfinished, and neither at the very start nor at the very end. */
function resumePosition(video: VideoDetail): number | undefined {
  const progress = video.progress;
  if (!progress || progress.watched || progress.position_s < MIN_RESUME_S) return undefined;
  if (video.duration_s && progress.position_s > video.duration_s - 15) return undefined;
  return progress.position_s;
}

export function VideoPage() {
  const { id } = useParams();
  const videoId = Number(id);
  const [searchParams] = useSearchParams();
  const playlistParam = Number(searchParams.get("playlist"));
  const playlistId = Number.isInteger(playlistParam) && playlistParam > 0 ? playlistParam : null;
  const autoplay = Boolean((useLocation().state as LocationState | null)?.autoplay);
  const { data: video, isLoading, error } = useVideo(videoId);
  useDocumentTitle(video?.title);

  if (isLoading) return <PageSpinner />;
  if (error || !video) {
    return (
      <EmptyState
        icon={<ArrowLeft className="size-7" strokeWidth={1.5} />}
        title="Video nicht gefunden"
      >
        <Link to="/library" className="text-accent hover:underline">
          Zur Bibliothek
        </Link>
      </EmptyState>
    );
  }
  return <VideoView key={video.id} video={video} playlistId={playlistId} autoplay={autoplay} />;
}

interface VideoViewProps {
  video: VideoDetail;
  playlistId: number | null;
  autoplay: boolean;
}

function VideoView({ video, playlistId, autoplay }: VideoViewProps) {
  const player = useRef<PlayerHandle>(null);
  const navigate = useNavigate();
  const client = useQueryClient();
  const { user } = useAuth();
  const preferences = user?.preferences ?? {};

  const playback = usePlaybackSource(video);
  const [channelRate, saveChannelRate] = useChannelRate(video.channel?.id);
  const [time, setTime] = useState(0);
  const onTimeUpdate = useCallback((seconds: number) => setTime(Math.floor(seconds)), []);

  const [startAt] = useState(() => resumePosition(video));
  const [hasPlayed, setHasPlayed] = useState(false);
  const [notice, setNotice] = useState<PlayerNotice | null>(() =>
    startAt
      ? {
          id: 0,
          message: `Weiter bei ${formatDuration(startAt)}`,
          action: { label: "Von vorne", run: () => player.current?.seek(0) },
          untilPlay: true,
        }
      : null,
  );
  useEffect(() => {
    if (!notice || (notice.untilPlay && !hasPlayed)) return;
    const timer = setTimeout(() => setNotice(null), 6000);
    return () => clearTimeout(timer);
  }, [notice, hasPlayed]);

  // SponsorBlock: segments are only fetched when skipping is enabled server-side.
  const { data: sponsor } = useSegments(video.id, !video.sponsorblock_cut);
  const segments = sponsor?.mode === "skip" ? sponsor.segments : undefined;
  const autoSkip = preferences.sponsorblock_skip !== false;
  const [currentSegment, setCurrentSegment] = useState<SponsorSegment | null>(null);
  const onSegmentSkipped = useCallback((segment: SponsorSegment) => {
    setNotice({
      id: Date.now(),
      message: `${categoryLabel(segment.category)} übersprungen`,
      action: {
        label: "Zurück",
        run: () => {
          player.current?.allowSegment(segment);
          player.current?.seek(segment.start_s);
        },
      },
    });
  }, []);

  // Playlist context: panel, next video, autoplay.
  const { data: playlist } = usePlaylist(playlistId);
  const index = playlist?.videos.findIndex((v) => v.id === video.id) ?? -1;
  const nextVideo = playlist && index >= 0 ? playlist.videos[index + 1] : undefined;
  const [upNext, setUpNext] = useState<UpNext | null>(null);

  const openInPlaylist = useCallback(
    (videoId: number, options?: { autoplay?: boolean }) => {
      if (!playlistId) return;
      navigate(`/videos/${videoId}?playlist=${playlistId}`, {
        replace: options?.autoplay,
        state: { autoplay: options?.autoplay ?? true } satisfies LocationState,
      });
    },
    [navigate, playlistId],
  );

  useEffect(() => {
    if (!upNext) return;
    const timer = setTimeout(() => {
      if (upNext.remaining <= 1) openInPlaylist(upNext.video.id, { autoplay: true });
      else setUpNext({ ...upNext, remaining: upNext.remaining - 1 });
    }, 1000);
    return () => clearTimeout(timer);
  }, [upNext, openInPlaylist]);

  // Progress: saved by the player at sensible moments. After "mark as watched" we stop
  // saving until playback resumes, otherwise the next save would undo it.
  const savesPaused = useRef(false);
  const onSave = useCallback(
    (position: number, duration: number, reason: SaveReason) => {
      if (savesPaused.current) return;
      void reportProgress(video.id, position, duration).then((state) => {
        if (state && reason !== "unmount") {
          client.setQueryData<VideoDetail>(keys.video(video.id), (old) =>
            old ? { ...old, progress: state } : old,
          );
        }
        if (reason === "unmount" || reason === "ended") {
          void client.invalidateQueries({ queryKey: keys.videos });
          void client.invalidateQueries({ queryKey: keys.channels });
          void client.invalidateQueries({ queryKey: keys.playlists });
        }
      });
    },
    [client, video.id],
  );
  const onPlay = useCallback(() => {
    savesPaused.current = false;
    setHasPlayed(true);
    setUpNext(null);
  }, []);
  const onEnded = useCallback(() => {
    if (videoSleep()?.kind === "end") {
      setVideoSleep(null);
      setNotice({ id: Date.now(), message: "Schlaf-Timer: Gute Nacht" });
      return; // no next video
    }
    if (nextVideo && preferences.autoplay_next !== false) {
      setUpNext({ video: nextVideo, remaining: UP_NEXT_SECONDS });
    }
  }, [nextVideo, preferences.autoplay_next]);

  // Sleep timer: when the time is up, the sound fades out and the video pauses. A timer that
  // ran out long ago (nobody was watching) is just dropped.
  const sleep = useVideoSleep();
  useEffect(() => {
    if (sleep?.kind !== "minutes") return;
    const timer = setTimeout(
      () => {
        setVideoSleep(null);
        if (Date.now() - sleep.until > 60_000) return;
        player.current?.fadeOutAndPause();
        setNotice({ id: Date.now(), message: "Schlaf-Timer: Gute Nacht" });
      },
      Math.max(0, sleep.until - Date.now()),
    );
    return () => clearTimeout(timer);
  }, [sleep]);

  // Timestamps in the description and comments: jump there and bring the player into view.
  const seek = useCallback((seconds: number) => {
    player.current?.seek(seconds);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  const playlistPanel = playlist ? (
    <PlaylistPanel
      playlist={playlist}
      currentId={video.id}
      onNavigate={(id) => openInPlaylist(id)}
    />
  ) : null;

  return (
    <div className="-mx-4 sm:mx-0">
      <div className="mb-3 px-4 sm:px-0 md:mb-4">
        <Button
          variant="ghost"
          size="sm"
          className="-ml-3 text-secondary"
          icon={<ArrowLeft className="size-4" strokeWidth={2} />}
          onClick={() => (window.history.length > 1 ? navigate(-1) : navigate("/"))}
        >
          Zurück
        </Button>
      </div>

      <div className="mx-auto max-w-[1400px]">
        <VideoPlayer
          ref={player}
          video={video}
          source={playback.source}
          onSourceError={playback.onSourceError}
          startAt={startAt}
          autoplay={autoplay}
          segments={segments}
          skipSegments={autoSkip}
          onTimeUpdate={onTimeUpdate}
          onSave={onSave}
          onPlay={onPlay}
          onEnded={onEnded}
          onSegmentSkipped={onSegmentSkipped}
          onSegmentChange={setCurrentSegment}
          playbackRate={channelRate}
          onRateChange={saveChannelRate}
          normalizeVolume={user?.preferences.normalize_volume !== false}
          overlay={
            <>
              <div className="absolute top-3 right-3 flex items-start gap-2 sm:top-4 sm:right-4">
                <SleepMenu />
                {playback.showMenu && (
                  <QualityMenu
                    options={playback.options}
                    value={playback.choice}
                    onChange={playback.setChoice}
                  />
                )}
              </div>
              <PlaybackStatus
                preparing={playback.preparing}
                error={playback.error}
                onRetry={playback.retry}
              />
              <PlayerOverlay
                notice={notice}
                onDismissNotice={() => setNotice(null)}
                skipLabel={
                  currentSegment ? `${categoryLabel(currentSegment.category)} überspringen` : null
                }
                onSkip={() => currentSegment && player.current?.seek(currentSegment.end_s)}
                upNext={upNext}
                onPlayNext={() => upNext && openInPlaylist(upNext.video.id, { autoplay: true })}
                onCancelNext={() => setUpNext(null)}
              />
            </>
          }
        />

        <div className="mt-6 grid gap-10 px-4 sm:px-0 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div className="min-w-0">
            <h1 className="text-[24px] leading-tight font-bold tracking-tight sm:text-[28px]">
              {video.title}
            </h1>
            <ChannelLine video={video} />
            <VideoActions
              video={video}
              onWatchedChange={(watched) => {
                savesPaused.current = watched;
              }}
            />
            {/* Phones: the playlist matters more than the description. */}
            {playlistPanel && <div className="mt-6 lg:hidden">{playlistPanel}</div>}
            {video.description && (
              <Description text={video.description} duration={video.duration_s} onSeek={seek} />
            )}
            {!video.is_local && <Comments video={video} onSeek={seek} />}
          </div>

          <aside aria-label="Kapitel und weitere Videos" className="flex min-w-0 flex-col gap-8">
            {playlistPanel && <div className="max-lg:hidden">{playlistPanel}</div>}
            {video.chapters.length > 0 && (
              <section aria-labelledby="chapters-heading">
                <h2 id="chapters-heading" className="mb-3 text-[17px] font-semibold">
                  Kapitel
                </h2>
                <ol className="flex flex-col gap-0.5">
                  {video.chapters.map((chapter, chapterIndex) => {
                    const active = time >= chapter.start && time < chapter.end;
                    return (
                      <li key={`${chapter.start}-${chapterIndex}`}>
                        <button
                          type="button"
                          onClick={() => player.current?.seek(chapter.start)}
                          aria-current={active ? "true" : undefined}
                          className={cn(
                            "flex w-full items-baseline gap-3 rounded-lg px-3 py-2 text-left text-[14px] transition-colors duration-200",
                            active
                              ? "bg-surface text-primary"
                              : "text-secondary hover:bg-surface/60 hover:text-primary",
                          )}
                        >
                          <span
                            className={cn(
                              "w-14 shrink-0 text-[13px] tabular-nums",
                              active ? "text-accent" : "text-tertiary",
                            )}
                          >
                            {formatDuration(chapter.start)}
                          </span>
                          <span className="min-w-0">{chapter.title}</span>
                        </button>
                      </li>
                    );
                  })}
                </ol>
              </section>
            )}
            <SimilarVideos videoId={video.id} />
            <FileInfo video={video} skipped={segments?.length ?? 0} />
          </aside>
        </div>
      </div>
    </div>
  );
}

function ChannelLine({ video }: { video: VideoDetail }) {
  const meta = [
    formatDate(video.upload_date),
    video.view_count != null ? `${formatCount(video.view_count)} Aufrufe` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  if (!video.channel) return <p className="mt-2 text-[15px] text-secondary">{meta}</p>;
  return (
    <div className="mt-3 flex items-center gap-3">
      <Link to={`/channels/${video.channel.id}`} className="shrink-0" tabIndex={-1} aria-hidden>
        <ChannelAvatar channel={video.channel} name={video.channel.name} className="size-10" />
      </Link>
      <div className="min-w-0">
        <Link
          to={`/channels/${video.channel.id}`}
          className="block truncate text-[15px] font-semibold hover:underline"
        >
          {video.channel.name}
        </Link>
        {meta && <p className="text-[13px] text-secondary">{meta}</p>}
      </div>
    </div>
  );
}

// Kept apart because cn() only joins classes; conflicting utilities must not meet.
const actionBase =
  "inline-flex h-9 items-center gap-2 rounded-full text-[14px] font-medium transition-colors duration-200";
const actionNeutral = "bg-surface hover:bg-surface-hover";
const actionClass = cn(actionBase, actionNeutral, "px-4");

function WatchLaterButton({ videoId }: { videoId: number }) {
  const { data: later } = useWatchLater();
  const toggle = useToggleWatchLater();
  const toast = useToast();
  if (!later) return null;
  const saved = later.videos.some((v) => v.id === videoId);
  return (
    <button
      type="button"
      aria-pressed={saved}
      disabled={toggle.isPending}
      onClick={() =>
        toggle.mutate(
          { listId: later.id, videoId, add: !saved },
          {
            onSuccess: () => toast(saved ? "Aus „Später ansehen“ entfernt" : "Für später gemerkt"),
            onError: (err) => toast(err.message, "error"),
          },
        )
      }
      className={cn(
        actionBase,
        "px-4",
        saved ? "bg-accent/15 text-accent hover:bg-accent/25" : actionNeutral,
      )}
    >
      {saved ? (
        <Check className="size-4" strokeWidth={2.5} />
      ) : (
        <Clock className="size-4" strokeWidth={2} />
      )}
      Später ansehen
    </button>
  );
}

interface VideoActionsProps {
  video: VideoDetail;
  onWatchedChange: (watched: boolean) => void;
}

function VideoActions({ video, onWatchedChange }: VideoActionsProps) {
  const { user } = useAuth();
  const remote = useRemoteControl();
  const party = useCreateParty();
  const [confirming, setConfirming] = useState(false);
  const [addingToPlaylist, setAddingToPlaylist] = useState(false);
  const [addingToFolder, setAddingToFolder] = useState(false);
  const [savingToDevice, setSavingToDevice] = useState(false);
  const [redownloading, setRedownloading] = useState(false);
  const audio = useAudioPlayer();
  const offline = useOffline();
  const remove = useDeleteVideo();
  const redownload = useRedownloadVideo();
  const setWatched = useSetWatched();
  const { data: speech } = useSpeechState(Boolean(user?.is_admin));
  const makeSubtitles = useSpeechSubtitles();
  const toast = useToast();
  const navigate = useNavigate();
  const watched = video.progress?.watched ?? false;

  const toggleWatched = () => {
    const next = !watched;
    setWatched.mutate(
      { id: video.id, watched: next },
      {
        onSuccess: () => {
          onWatchedChange(next);
          toast(next ? "Als gesehen markiert" : "Als ungesehen markiert");
        },
        onError: (err) => toast(err.message, "error"),
      },
    );
  };

  const confirmDelete = async () => {
    try {
      await remove.mutateAsync(video.id);
      toast("Video gelöscht");
      navigate("/library", { replace: true });
    } catch (err) {
      toast(err instanceof Error ? err.message : "Löschen fehlgeschlagen", "error");
      setConfirming(false);
    }
  };

  return (
    <div className="mt-5 flex flex-wrap gap-2.5">
      <button
        type="button"
        onClick={toggleWatched}
        disabled={setWatched.isPending}
        aria-pressed={watched}
        className={cn(
          actionBase,
          "px-4",
          watched ? "bg-accent/15 text-accent hover:bg-accent/25" : actionNeutral,
        )}
      >
        {watched ? (
          <Check className="size-4" strokeWidth={2.5} />
        ) : (
          <CircleCheck className="size-4" strokeWidth={2} />
        )}
        {watched ? "Gesehen" : "Als gesehen markieren"}
      </button>
      <WatchLaterButton videoId={video.id} />
      <button type="button" onClick={() => setAddingToPlaylist(true)} className={actionClass}>
        <ListPlus className="size-4" strokeWidth={2} />
        Zur Playlist
      </button>
      <button type="button" onClick={() => setAddingToFolder(true)} className={actionClass}>
        <FolderPlus className="size-4" strokeWidth={2} />
        In Ordner
      </button>
      {remote.status === "paired" && (
        <button
          type="button"
          onClick={() => {
            remote.send("open", video.id);
            toast(`Läuft auf dem Fernseher (${remote.tv})`);
          }}
          className={actionClass}
        >
          <Tv2 className="size-4" strokeWidth={2} />
          Auf Fernseher
        </button>
      )}
      {/* Shows itself only while saving or once saved; started from the menu. */}
      <SaveToDevice
        video={video}
        buttonless
        open={savingToDevice}
        onOpenChange={setSavingToDevice}
      />
      <MoreMenu
        items={[
          {
            key: "listen",
            label: audio.track?.id === video.id ? "Im Audio-Player öffnen" : "Anhören",
            icon: Headphones,
            onSelect: () => {
              if (audio.track?.id === video.id) audio.setExpanded(true);
              else audio.play([trackFromVideo(video)]);
            },
          },
          {
            key: "party",
            label: "Gemeinsam schauen",
            icon: UsersRound,
            disabled: party.isPending,
            onSelect: () =>
              party.mutate(video.id, {
                onSuccess: (room) => navigate(`/party/${room.id}`),
                onError: (err) => toast(err.message, "error"),
              }),
          },
          ...(offline.supported &&
          !offline.entries[video.id] &&
          !offline.tasks.some((task) => task.id === video.id)
            ? [
                {
                  key: "device",
                  label: "Aufs Gerät laden",
                  icon: HardDriveDownload,
                  onSelect: () => setSavingToDevice(true),
                },
              ]
            : []),
          {
            key: "file",
            label: "Datei laden",
            icon: Download,
            href: apiUrl(`videos/${video.id}/download`),
          },
          ...(video.source_url
            ? [
                {
                  key: "youtube",
                  label: "Auf YouTube öffnen",
                  icon: ExternalLink,
                  href: video.source_url,
                  external: true,
                },
              ]
            : []),
          ...(user?.is_admin && speech?.ready
            ? [
                {
                  key: "subtitles",
                  label: "Untertitel erzeugen",
                  icon: Captions,
                  separated: true,
                  disabled: makeSubtitles.isPending,
                  onSelect: () =>
                    makeSubtitles.mutate(video.id, {
                      onSuccess: ({ queued }) =>
                        toast(
                          queued > 1
                            ? `Untertitel kommen dran – ${queued - 1} vorher in der Reihe`
                            : "Untertitel werden erzeugt – sie erscheinen von selbst im Player",
                        ),
                      onError: (err) => toast(err.message, "error"),
                    }),
                },
              ]
            : []),
          ...(user?.is_admin && user.can_add && !video.is_local
            ? [
                {
                  key: "reload",
                  label: "Neu laden",
                  icon: RefreshCw,
                  separated: !speech?.ready,
                  onSelect: () => setRedownloading(true),
                },
              ]
            : []),
          ...(user?.is_admin
            ? [
                {
                  key: "delete",
                  label: "Video löschen",
                  icon: Trash2,
                  danger: true,
                  separated: true,
                  onSelect: () => setConfirming(true),
                },
              ]
            : []),
        ]}
      />
      <AddToPlaylistDialog
        open={addingToPlaylist}
        onClose={() => setAddingToPlaylist(false)}
        videoId={video.id}
      />
      <AddToFolderDialog
        open={addingToFolder}
        onClose={() => setAddingToFolder(false)}
        videoId={video.id}
      />
      <Dialog open={redownloading} onClose={() => setRedownloading(false)} title="Video neu laden?">
        <p className="text-[15px] text-secondary">
          TubeVault lädt „{video.title}“ mit den aktuellen Einstellungen noch einmal
          {video.height ? ` (jetzt: ${formatResolution(video.height, video.width)})` : ""} – etwa in
          besserer Qualität – und ersetzt die Datei, sobald der Download fertig ist. Bis dahin läuft
          die jetzige Fassung weiter; Wiedergabestand und Playlists bleiben erhalten.
        </p>
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="secondary" onClick={() => setRedownloading(false)}>
            Abbrechen
          </Button>
          <Button
            loading={redownload.isPending}
            onClick={() =>
              redownload.mutate(video.id, {
                onSuccess: () => {
                  setRedownloading(false);
                  toast("Wird neu geladen – den Fortschritt siehst du unter Downloads");
                },
                onError: (err) => {
                  setRedownloading(false);
                  toast(err.message, "error");
                },
              })
            }
          >
            Neu laden
          </Button>
        </div>
      </Dialog>
      <Dialog open={confirming} onClose={() => setConfirming(false)} title="Video löschen?">
        <p className="text-[15px] text-secondary">
          „{video.title}“ wird mit Thumbnail und Untertiteln von der Festplatte entfernt.
        </p>
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="secondary" onClick={() => setConfirming(false)}>
            Abbrechen
          </Button>
          <Button
            className="bg-danger-fill hover:bg-danger-fill/90"
            loading={remove.isPending}
            onClick={() => void confirmDelete()}
          >
            Löschen
          </Button>
        </div>
      </Dialog>
    </div>
  );
}

interface DescriptionProps {
  text: string;
  duration: number | null;
  onSeek: (seconds: number) => void;
}

function Description({ text, duration, onSeek }: DescriptionProps) {
  const [expanded, setExpanded] = useState(false);
  const long = text.length > 280 || text.split("\n").length > 4;
  return (
    <section className="mt-6 rounded-2xl bg-elevated p-4 sm:p-5">
      <div
        className={cn(
          "text-[14px] leading-relaxed break-words whitespace-pre-line text-secondary",
          !expanded && long && "line-clamp-4",
        )}
      >
        <RichText text={text} duration={duration} onSeek={onSeek} />
      </div>
      {long && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-2 text-[14px] font-medium text-primary hover:underline"
        >
          {expanded ? "Weniger" : "Mehr"}
        </button>
      )}
    </section>
  );
}

function FileInfo({ video, skipped }: { video: VideoDetail; skipped: number }) {
  const sponsorblock = video.sponsorblock_cut
    ? "Herausgeschnitten"
    : skipped > 0
      ? `${skipped} ${skipped === 1 ? "Abschnitt" : "Abschnitte"} zum Überspringen`
      : "";
  const rows: [string, string][] = [
    ["Dauer", formatDuration(video.duration_s)],
    [
      "Auflösung",
      video.width && video.height
        ? `${formatResolution(video.height, video.width)} · ${video.width} × ${video.height}`
        : formatResolution(video.height, video.width),
    ],
    ["Video", codecLabel(video.vcodec)],
    ["Audio", codecLabel(video.acodec)],
    ["Format", video.container?.toUpperCase() ?? ""],
    ["Größe", formatBytes(video.filesize)],
    ["Untertitel", video.subtitles.map((s) => s.label).join(", ")],
    ["SponsorBlock", sponsorblock],
    [video.is_local ? "Importiert" : "Heruntergeladen", formatDate(video.downloaded_at)],
  ];
  const visible = rows.filter(([, value]) => value);
  if (visible.length === 0) return null;
  return (
    <section aria-labelledby="file-heading">
      <h2 id="file-heading" className="mb-3 text-[17px] font-semibold">
        Details
      </h2>
      <dl className="divide-y divide-separator rounded-2xl bg-elevated px-4">
        {visible.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-4 py-2.5 text-[14px]">
            <dt className="text-secondary">{label}</dt>
            <dd className="text-right">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
