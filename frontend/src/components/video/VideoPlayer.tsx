import "video.js/dist/video-js.css";
import "./player.css";

import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import videojs from "video.js";
import german from "video.js/dist/lang/de.json";

import { apiUrl } from "@/lib/base";
import type { VideoDetail } from "@/lib/types";

import { thumbnailUrl } from "@/lib/media";

type Player = ReturnType<typeof videojs>;

videojs.addLanguage("de", german);

export interface PlayerHandle {
  seek: (seconds: number) => void;
}

interface VideoPlayerProps {
  video: VideoDetail;
  onTimeUpdate?: (seconds: number) => void;
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

function addChapterMarkers(player: Player, video: VideoDetail) {
  const holder = player.el().querySelector(".vjs-progress-holder");
  const duration = player.duration() || video.duration_s || 0;
  if (!holder || !duration) return;
  holder.querySelectorAll(".vjs-chapter-marker").forEach((el) => el.remove());
  for (const chapter of video.chapters) {
    if (chapter.start <= 0 || chapter.start >= duration) continue;
    const marker = document.createElement("div");
    marker.className = "vjs-chapter-marker";
    marker.style.left = `${(chapter.start / duration) * 100}%`;
    marker.title = chapter.title;
    holder.appendChild(marker);
  }
}

export const VideoPlayer = forwardRef<PlayerHandle, VideoPlayerProps>(function VideoPlayer(
  { video, onTimeUpdate },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<Player | null>(null);
  const timeUpdateRef = useRef(onTimeUpdate);

  const latestVideo = useRef(video);

  useEffect(() => {
    timeUpdateRef.current = onTimeUpdate;
    latestVideo.current = video;
  });

  useImperativeHandle(ref, () => ({
    seek: (seconds: number) => {
      const player = playerRef.current;
      if (!player) return;
      player.currentTime(seconds);
      void player.play();
      (player.el() as HTMLElement).focus();
    },
  }));

  // Recreate the player only when the video itself changes, not on every refetch.
  const videoKey = `${video.id}:${video.updated_at}`;
  useEffect(() => {
    const container = containerRef.current;
    const video = latestVideo.current;
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

    player.ready(() => {
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
    });
    player.on("loadedmetadata", () => addChapterMarkers(player, video));
    player.on("timeupdate", () => timeUpdateRef.current?.(player.currentTime() ?? 0));
    player.on("error", () => {
      const error = player.error();
      if (error?.code === 4 && video.container === "mkv") {
        player.error(
          "Dein Browser kann MKV nicht direkt abspielen. Lade die Datei herunter oder nutze Chrome, Edge oder Firefox.",
        );
      }
    });

    return () => {
      if (!player.isDisposed()) player.dispose();
      playerRef.current = null;
    };
  }, [videoKey]);

  return (
    <div
      ref={containerRef}
      data-vjs-player
      className="relative aspect-video w-full overflow-hidden bg-black sm:rounded-2xl"
    />
  );
});
