import { Check } from "lucide-react";

import type { VideoSummary } from "@/lib/types";

/** Progress line and "watched" badge drawn over a thumbnail. */
export function WatchOverlay({ video }: { video: Pick<VideoSummary, "progress" | "duration_s"> }) {
  const progress = video.progress;
  if (!progress) return null;
  if (progress.watched) {
    return (
      <span
        className="absolute top-2 right-2 flex size-6 items-center justify-center rounded-full bg-black/60 text-white backdrop-blur-md"
        title="Gesehen"
      >
        <Check className="size-3.5" strokeWidth={3} />
        <span className="sr-only">Gesehen</span>
      </span>
    );
  }
  const duration = video.duration_s ?? 0;
  if (!duration || progress.position_s < 10) return null;
  const share = Math.min(progress.position_s / duration, 1);
  return (
    <div className="absolute inset-x-2.5 bottom-2 h-1 overflow-hidden rounded-full bg-white/30">
      <div className="h-full rounded-full bg-white" style={{ width: `${share * 100}%` }} />
    </div>
  );
}
