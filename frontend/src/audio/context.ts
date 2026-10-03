import { createContext, useContext } from "react";

import { thumbnailUrl } from "@/lib/media";
import type { VideoSummary } from "@/lib/types";

export interface AudioTrack {
  /** The video this sound belongs to. */
  id: number;
  title: string;
  channel: string | null;
  duration: number | null;
  artwork?: string;
  startAt?: number;
  /** A file ready to play (saved on the device); otherwise the server prepares the sound. */
  src?: string;
  /** Where progress goes instead of the server (saved videos without connection). */
  save?: (position: number, duration: number) => void;
  /** Called once the track is done with, e.g. to free an object URL. */
  release?: () => void;
}

export type SleepTimer = { kind: "minutes"; until: number } | { kind: "end" };

export interface AudioPlayerValue {
  track: AudioTrack | null;
  queue: AudioTrack[];
  index: number;
  playing: boolean;
  preparing: boolean;
  error: string | null;
  position: number;
  duration: number;
  rate: number;
  sleep: SleepTimer | null;
  expanded: boolean;
  play: (tracks: AudioTrack[], index?: number) => void;
  toggle: () => void;
  pause: () => void;
  seek: (seconds: number) => void;
  skip: (delta: number) => void;
  next: () => void;
  previous: () => void;
  setRate: (rate: number) => void;
  setSleep: (minutes: number | "end" | null) => void;
  setExpanded: (expanded: boolean) => void;
  close: () => void;
}

export const AudioPlayerContext = createContext<AudioPlayerValue | null>(null);

export function useAudioPlayer(): AudioPlayerValue {
  const ctx = useContext(AudioPlayerContext);
  if (!ctx) throw new Error("useAudioPlayer must be used inside <AudioPlayerProvider>");
  return ctx;
}

export const RATES = [0.75, 1, 1.25, 1.5, 1.75, 2];
export const SLEEP_MINUTES = [5, 15, 30, 45, 60];

const MIN_RESUME_S = 10;

/** A library video as something to listen to – resuming where it stopped. */
export function trackFromVideo(video: VideoSummary): AudioTrack {
  const progress = video.progress;
  const resume =
    progress && !progress.watched && progress.position_s >= MIN_RESUME_S
      ? progress.position_s
      : undefined;
  return {
    id: video.id,
    title: video.title,
    channel: video.channel?.name ?? null,
    duration: video.duration_s,
    artwork: video.has_thumbnail ? thumbnailUrl(video) : undefined,
    startAt: resume,
  };
}
