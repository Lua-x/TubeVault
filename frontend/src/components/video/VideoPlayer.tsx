import "video.js/dist/video-js.css";
import "./player.css";

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import videojs from "video.js";
import german from "video.js/dist/lang/de.json";

import { apiUrl } from "@/lib/base";
import { thumbnailUrl } from "@/lib/media";
import type { SponsorSegment, VideoDetail } from "@/lib/types";

type Player = ReturnType<typeof videojs>;

videojs.addLanguage("de", german);

export interface PlayerHandle {
  seek: (seconds: number, options?: { play?: boolean }) => void;
  /** Stops skipping this segment again, e.g. after the user jumped back into it. */
  allowSegment: (segment: SponsorSegment) => void;
}

/** Why a save point was reached; the page decides what to do with it. */
export type SaveReason = "interval" | "pause" | "seeked" | "ended" | "hidden" | "unmount";

interface VideoPlayerProps {
  video: VideoDetail;
  /** Position to continue from once the metadata is loaded. */
  startAt?: number;
  autoplay?: boolean;
  /** SponsorBlock segments: always drawn on the progress bar. */
  segments?: SponsorSegment[];
  /** Jump over `segments` automatically. */
  skipSegments?: boolean;
  onTimeUpdate?: (seconds: number) => void;
  onSave?: (seconds: number, duration: number, reason: SaveReason) => void;
  onSegmentSkipped?: (segment: SponsorSegment) => void;
  /** Segment the playhead is in right now (only reported when not skipping automatically). */
  onSegmentChange?: (segment: SponsorSegment | null) => void;
  onPlay?: () => void;
  onEnded?: () => void;
  /** Rendered inside the player element, so it stays visible in fullscreen. */
  overlay?: ReactNode;
}

function sourceType(container: string | null): string {
  if (container === "mkv") {
    // Chrome and Firefox play Matroska with H.264/VP9 but don't advertise the MIME type.
    const probe = document.createElement("video");
    return probe.canPlayType("video/x-matroska") ? "video/x-matroska" : "video/webm";
  }
  if (container === "webm") return "video/webm";
  return "video/mp4";
}

const SEEK_STEP = 10;
const SAVE_INTERVAL_S = 10;
// Don't skip the last fraction of a segment; seeking there would only cause a stutter.
const SKIP_TAIL_S = 0.4;

function handleHotkeys(this: Player, event: KeyboardEvent) {
  const key = event.key.toLowerCase();
  const time = this.currentTime() ?? 0;
  const volume = this.volume() ?? 1;
  switch (key) {
    case " ":
    case "k":
      if (this.paused()) void this.play();
      else this.pause();
      break;
    case "arrowleft":
    case "j":
      this.currentTime(Math.max(0, time - (key === "j" ? SEEK_STEP : 5)));
      break;
    case "arrowright":
    case "l":
      this.currentTime(time + (key === "l" ? SEEK_STEP : 5));
      break;
    case "arrowup":
      this.volume(Math.min(1, volume + 0.1));
      break;
    case "arrowdown":
      this.volume(Math.max(0, volume - 0.1));
      break;
    case "m":
      this.muted(!this.muted());
      break;
    case "f":
      if (this.isFullscreen()) void this.exitFullscreen();
      else void this.requestFullscreen();
      break;
    default:
      return;
  }
  event.preventDefault();
}

function drawMarkers(player: Player, video: VideoDetail, segments: SponsorSegment[]) {
  const holder = player.el()?.querySelector(".vjs-progress-holder");
  const duration = player.duration() || video.duration_s || 0;
  if (!holder || !duration) return;
  holder.querySelectorAll(".vjs-chapter-marker, .vjs-segment-marker").forEach((el) => el.remove());
  for (const segment of segments) {
    const start = Math.max(0, segment.start_s);
    const end = Math.min(duration, segment.end_s);
    if (end <= start) continue;
    const marker = document.createElement("div");
    marker.className = "vjs-segment-marker";
    marker.style.left = `${(start / duration) * 100}%`;
    marker.style.width = `${((end - start) / duration) * 100}%`;
    holder.appendChild(marker);
  }
  for (const chapter of video.chapters) {
    if (chapter.start <= 0 || chapter.start >= duration) continue;
    const marker = document.createElement("div");
    marker.className = "vjs-chapter-marker";
    marker.style.left = `${(chapter.start / duration) * 100}%`;
    marker.title = chapter.title;
    holder.appendChild(marker);
  }
}

const segmentKey = (s: SponsorSegment) => `${s.category}:${s.start_s}:${s.end_s}`;

export const VideoPlayer = forwardRef<PlayerHandle, VideoPlayerProps>(
  function VideoPlayer(props, ref) {
    const { video, segments, overlay } = props;
    const containerRef = useRef<HTMLDivElement>(null);
    const playerRef = useRef<Player | null>(null);
    const [overlayHost, setOverlayHost] = useState<HTMLElement | null>(null);
    // The player lives outside React; it reads the latest props through this ref.
    const latest = useRef(props);
    const allowed = useRef(new Set<string>());

    useEffect(() => {
      latest.current = props;
    });

    useImperativeHandle(ref, () => ({
      seek: (seconds, options) => {
        const player = playerRef.current;
        if (!player) return;
        player.currentTime(seconds);
        if (options?.play ?? true) void player.play();
        (player.el() as HTMLElement).focus();
      },
      allowSegment: (segment) => allowed.current.add(segmentKey(segment)),
    }));

    // Recreate the player only when the file changes, not on every metadata refresh.
    const fileKey = `${video.id}:${video.downloaded_at ?? ""}:${video.filesize ?? ""}`;
    useEffect(() => {
      const container = containerRef.current;
      const { video, startAt, autoplay } = latest.current;
      if (!container) return;
      const element = document.createElement("video-js");
      element.classList.add("vjs-tubevault", "vjs-big-play-centered");
      container.appendChild(element);

      const player = videojs(element, {
        controls: true,
        preload: "metadata",
        fill: true,
        playsinline: true,
        inactivityTimeout: 2500,
        poster: video.has_thumbnail ? thumbnailUrl(video) : undefined,
        playbackRates: [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2],
        language: "de",
        html5: { nativeTextTracks: false },
        userActions: { hotkeys: handleHotkeys },
        controlBar: {
          remainingTimeDisplay: { displayNegative: true },
          pictureInPictureToggle: true,
        },
        sources: [{ src: apiUrl(`videos/${video.id}/stream`), type: sourceType(video.container) }],
      });
      playerRef.current = player;
      allowed.current = new Set();

      let started = false;
      let lastSaved = startAt ?? 0;
      let currentSegment: SponsorSegment | null = null;

      const save = (reason: SaveReason) => {
        if (!started || player.isDisposed()) return;
        const position = player.currentTime() ?? 0;
        lastSaved = position;
        latest.current.onSave?.(position, player.duration() || video.duration_s || 0, reason);
      };

      const checkSegments = (time: number) => {
        const { segments = [], skipSegments, onSegmentSkipped, onSegmentChange } = latest.current;
        const inside =
          segments.find(
            (s) =>
              time >= s.start_s &&
              time < s.end_s - SKIP_TAIL_S &&
              !allowed.current.has(segmentKey(s)),
          ) ?? null;
        if (inside && skipSegments && !player.paused()) {
          player.currentTime(inside.end_s);
          onSegmentSkipped?.(inside);
          return;
        }
        const next = skipSegments ? null : inside;
        if (next !== currentSegment) {
          currentSegment = next;
          onSegmentChange?.(next);
        }
      };

      player.ready(() => {
        const host = document.createElement("div");
        host.className = "vjs-tubevault-overlay";
        // Keys typed on overlay buttons must not reach the player hotkeys.
        host.addEventListener("keydown", (event) => event.stopPropagation());
        player.el().appendChild(host);
        setOverlayHost(host);

        for (const sub of video.subtitles) {
          player.addRemoteTextTrack(
            {
              kind: "subtitles",
              src: apiUrl(`videos/${video.id}/subtitles/${sub.id}.vtt`),
              srclang: sub.lang,
              label: sub.label,
            },
            false,
          );
        }
        if (video.chapters.length > 0) {
          player.addRemoteTextTrack(
            {
              kind: "chapters",
              src: apiUrl(`videos/${video.id}/chapters.vtt`),
              srclang: "de",
              label: "Kapitel",
              default: true,
            },
            false,
          );
        }
        if (autoplay) {
          // Browsers may refuse without a user gesture; the big play button stays then.
          player.play()?.catch(() => undefined);
        }
      });
      player.one("loadedmetadata", () => {
        if (startAt && startAt > 0) player.currentTime(startAt);
      });
      player.on("loadedmetadata", () => drawMarkers(player, video, latest.current.segments ?? []));
      player.on("playing", () => {
        started = true;
      });
      player.on("play", () => latest.current.onPlay?.());
      player.on("timeupdate", () => {
        const time = player.currentTime() ?? 0;
        latest.current.onTimeUpdate?.(time);
        checkSegments(time);
        if (started && !player.paused() && Math.abs(time - lastSaved) >= SAVE_INTERVAL_S) {
          save("interval");
        }
      });
      player.on("pause", () => {
        // video.js pauses right before "ended"; that save point is reported separately.
        if (!player.ended()) save("pause");
      });
      player.on("seeked", () => save("seeked"));
      player.on("ended", () => {
        save("ended");
        latest.current.onEnded?.();
      });
      player.on("error", () => {
        const error = player.error();
        if (error?.code === 4 && video.container === "mkv") {
          player.error(
            "Dein Browser kann MKV nicht direkt abspielen. Lade die Datei herunter oder nutze Chrome, Edge oder Firefox.",
          );
        }
      });

      const onHidden = () => {
        if (document.visibilityState === "hidden") save("hidden");
      };
      const onPageHide = () => save("hidden");
      document.addEventListener("visibilitychange", onHidden);
      window.addEventListener("pagehide", onPageHide);

      return () => {
        document.removeEventListener("visibilitychange", onHidden);
        window.removeEventListener("pagehide", onPageHide);
        save("unmount");
        setOverlayHost(null);
        if (!player.isDisposed()) player.dispose();
        playerRef.current = null;
      };
    }, [fileKey]);

    // Segments usually arrive after the player was created.
    useEffect(() => {
      const player = playerRef.current;
      if (player && !player.isDisposed() && player.readyState() > 0) {
        drawMarkers(player, latest.current.video, segments ?? []);
      }
    }, [segments, fileKey]);

    return (
      <div
        ref={containerRef}
        data-vjs-player
        className="relative aspect-video w-full overflow-hidden bg-black sm:rounded-2xl"
      >
        {overlayHost && overlay ? createPortal(overlay, overlayHost) : null}
      </div>
    );
  },
);
