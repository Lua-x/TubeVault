import { createContext, useContext } from "react";

import { formatBytes } from "@/lib/format";
import { canPlayDirectly, canPlayRemuxed } from "@/lib/playback";
import type { PlaybackInfo, VideoDetail } from "@/lib/types";

/** What to save: the original file, the original repacked as MP4, or a compact copy. */
export type OfflineQuality = "original" | "remux" | 720 | 480;
/** What can be asked for: also "the best that plays here", decided per video. */
export type SaveQuality = OfflineQuality | "best";

export interface OfflineEntry {
  id: number;
  video: VideoDetail;
  quality: OfflineQuality;
  size: number;
  saved_at: string;
  subtitles: number[];
  has_chapters: boolean;
  has_thumbnail: boolean;
}

export interface OfflineTask {
  id: number;
  title: string;
  quality: SaveQuality;
  phase: "queued" | "preparing" | "downloading";
  progress: number;
}

export interface StorageUsage {
  used: number;
  quota: number;
}

export interface OfflineContextValue {
  /** False when this browser can't keep videos (no storage API). */
  supported: boolean;
  /** The user whose saved videos these are (null: nobody signed in on this device). */
  owner: number | null;
  ready: boolean;
  entries: Record<number, OfflineEntry>;
  tasks: OfflineTask[];
  usage: StorageUsage | null;
  save: (video: { id: number; title: string }, quality: SaveQuality) => void;
  cancel: (id: number) => void;
  remove: (id: number) => Promise<void>;
  /** Object URLs for playing a saved video; call `revoke` when done. */
  open: (id: number) => Promise<OfflineFiles | null>;
}

export interface OfflineFiles {
  video: string;
  poster?: string;
  subtitles: Record<number, string>;
  chapters?: string;
  revoke: () => void;
}

export const OfflineContext = createContext<OfflineContextValue | null>(null);

export function useOffline(): OfflineContextValue {
  const ctx = useContext(OfflineContext);
  if (!ctx) throw new Error("useOffline must be used inside <OfflineProvider>");
  return ctx;
}

export const QUALITY_LABELS: Record<string, string> = {
  best: "Original",
  original: "Original",
  remux: "Original (MP4)",
  720: "Kompakt · 720p",
  480: "Sparsam · 480p",
};

export function notEnoughSpace(needed: number, usage: StorageUsage | null): string | null {
  if (!usage) return null;
  const free = usage.quota - usage.used;
  return needed * 1.05 > free
    ? `Nicht genug Speicher auf diesem Gerät – frei: ${formatBytes(free)}, nötig: ${formatBytes(needed)}.`
    : null;
}

const IS_WEBKIT =
  typeof navigator !== "undefined" &&
  (/iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (/Safari\//.test(navigator.userAgent) && !/Chrome|Chromium|Android/.test(navigator.userAgent)));

/** How the original can be kept here: as it is, repacked as MP4, or not at all. */
export function originalQuality(info: PlaybackInfo): "original" | "remux" | null {
  // Saved files play from a blob: MP4 and WebM are safe, Matroska only after repacking.
  if (info.container !== "mkv" && canPlayDirectly(info, IS_WEBKIT)) return "original";
  return canPlayRemuxed(info) ? "remux" : null;
}
