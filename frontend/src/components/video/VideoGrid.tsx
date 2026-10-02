import { motion } from "motion/react";

import type { VideoSummary } from "@/lib/types";

import { VideoCard, VideoCardSkeleton } from "./VideoCard";

const GRID =
  "grid grid-cols-1 gap-x-5 gap-y-8 min-[480px]:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 min-[2000px]:grid-cols-5";

export function VideoGrid({
  videos,
  hideChannel,
}: {
  videos: VideoSummary[];
  hideChannel?: boolean;
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
            delay: Math.min(index, 12) * 0.03,
          }}
        >
          <VideoCard video={video} hideChannel={hideChannel} />
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
