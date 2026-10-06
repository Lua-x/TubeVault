import { useSyncExternalStore } from "react";

/** The video sleep timer. Lives outside the page, so it keeps running into the next video
 *  of a playlist. (The audio player has its own.) */
export type VideoSleep = { kind: "minutes"; until: number } | { kind: "end" };

let current: VideoSleep | null = null;
const listeners = new Set<() => void>();

export function videoSleep(): VideoSleep | null {
  return current;
}

export function setVideoSleep(value: number | "end" | null): void {
  current =
    value === null
      ? null
      : value === "end"
        ? { kind: "end" }
        : { kind: "minutes", until: Date.now() + value * 60_000 };
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useVideoSleep(): VideoSleep | null {
  return useSyncExternalStore(subscribe, videoSleep, videoSleep);
}

/** "23 min", and the seconds in the last minute. */
export function remainingLabel(until: number, now: number): string {
  const seconds = Math.max(0, Math.ceil((until - now) / 1000));
  if (seconds >= 60) return `${Math.ceil(seconds / 60)} min`;
  return `0:${String(seconds).padStart(2, "0")}`;
}
