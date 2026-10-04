import { motion } from "motion/react";

import type { VideoSummary } from "@/lib/types";

import { VideoCard, VideoCardSkeleton } from "./VideoCard";

const GRID =
  "grid grid-cols-1 gap-x-5 gap-y-8 min-[480px]:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 min-[2000px]:grid-cols-5";

export function VideoGrid({
  videos,
  hideChannel,
  heading = "h2",
}: {
  videos: VideoSummary[];
  hideChannel?: boolean;
  /** Level of the card titles: h2 right below the page title, h3 below a section. */
  heading?: "h2" | "h3";
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
          <VideoCard video={video} hideChannel={hideChannel} heading={heading} />
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
