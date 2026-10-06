import { Clock, ListVideo, type LucideIcon } from "lucide-react";

import { Thumbnail } from "@/components/video/Thumbnail";
import { cn } from "@/lib/cn";
import type { VideoSummary } from "@/lib/types";

/** One thumbnail, or a 2×2 mosaic once there are four videos. */
export function PlaylistCover({
  videos,
  className,
  watchLater = false,
  icon,
}: {
  videos: VideoSummary[];
  className?: string;
  /** "Später ansehen" gets a clock when it's empty. */
  watchLater?: boolean;
  /** Shown when there are no videos (e.g. a folder). */
  icon?: LucideIcon;
}) {
  const Icon = icon ?? (watchLater ? Clock : ListVideo);
  const base = cn("aspect-video overflow-hidden rounded-2xl bg-surface", className);
  if (videos.length === 0) {
    return (
      <div className={cn(base, "flex items-center justify-center text-tertiary")}>
        <Icon className="size-9" strokeWidth={1.25} />
      </div>
    );
  }
  if (videos.length < 4) {
    return <Thumbnail video={videos[0]!} className={cn(base, "w-full")} />;
  }
  return (
    <div className={cn(base, "grid grid-cols-2 grid-rows-2 gap-px")}>
      {videos.slice(0, 4).map((video) => (
        <Thumbnail key={video.id} video={video} className="size-full" />
      ))}
    </div>
  );
}
