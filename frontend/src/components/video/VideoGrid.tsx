import { X } from "lucide-react";
import { motion } from "motion/react";

import type { VideoSummary } from "@/lib/types";

import { VideoCard, VideoCardSkeleton } from "./VideoCard";

const GRID =
  "grid grid-cols-1 gap-x-5 gap-y-8 min-[480px]:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 min-[2000px]:grid-cols-5";

export function VideoGrid({
  videos,
  hideChannel,
  heading = "h2",
  onRemove,
  removeLabel = "Entfernen",
}: {
  videos: VideoSummary[];
  hideChannel?: boolean;
  /** Level of the card titles: h2 right below the page title, h3 below a section. */
  heading?: "h2" | "h3";
  /** A small × on each card, e.g. to take a video out of a folder. */
  onRemove?: (video: VideoSummary) => void;
  removeLabel?: string;
}) {
  return (
    <ul className={GRID}>
      {videos.map((video, index) => (
        <motion.li
          key={video.id}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{
            duration: 0.3,
            ease: [0.22, 1, 0.36, 1],
            // Stagger the first screen only; cards loaded while scrolling appear at once.
            delay: index < 12 ? index * 0.03 : 0,
          }}
        >
          <div className="group/item relative">
            <VideoCard video={video} hideChannel={hideChannel} heading={heading} />
            {onRemove && (
              <button
                type="button"
                aria-label={`${removeLabel}: ${video.title}`}
                title={removeLabel}
                onClick={() => onRemove(video)}
                className="absolute top-2 right-2 flex size-8 items-center justify-center rounded-full bg-black/65 text-white opacity-0 backdrop-blur-md transition-opacity group-hover/item:opacity-100 focus-visible:opacity-100 [@media(hover:none)]:opacity-100"
              >
                <X className="size-4" strokeWidth={2.25} />
              </button>
            )}
          </div>
        </motion.li>
      ))}
    </ul>
  );
}

export function VideoGridSkeleton({ count = 8 }: { count?: number }) {
  return (
    <div className={GRID}>
      {Array.from({ length: count }, (_, i) => (
        <VideoCardSkeleton key={i} />
      ))}
    </div>
  );
}
