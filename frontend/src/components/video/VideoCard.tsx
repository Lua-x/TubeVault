import { Link } from "react-router";

import { cn } from "@/lib/cn";
import { formatDuration, formatRelative } from "@/lib/format";
import type { VideoSummary } from "@/lib/types";

import { Thumbnail } from "./Thumbnail";
import { WatchOverlay } from "./WatchOverlay";

interface VideoCardProps {
  video: VideoSummary;
  /** Link target, e.g. with a playlist context. */
  to?: string;
  hideChannel?: boolean;
  className?: string;
  /** One level below the heading the card stands under (h2 directly below the page title). */
  heading?: "h2" | "h3";
}

export function VideoCard({
  video,
  to,
  hideChannel,
  className,
  heading: Heading = "h3",
}: VideoCardProps) {
  const meta = [hideChannel ? null : video.channel?.name, formatRelative(video.upload_date)]
    .filter(Boolean)
    .join(" · ");
  const inProgress = video.progress && !video.progress.watched && video.progress.position_s >= 10;
  return (
    <Link
      to={to ?? `/videos/${video.id}`}
      className={cn(
        "group flex flex-col gap-3 rounded-2xl focus-visible:outline-offset-4",
        className,
      )}
    >
      <div className="relative aspect-video overflow-hidden rounded-2xl bg-surface shadow-[0_0_0_1px_var(--tv-separator)] transition-[transform,box-shadow] duration-300 ease-out-soft group-hover:scale-[1.03] group-hover:shadow-card group-focus-visible:scale-[1.03]">
        <Thumbnail video={video} className="size-full" />
        {video.duration_s != null && !inProgress && (
          <span className="absolute right-2 bottom-2 rounded-md bg-black/70 px-1.5 py-0.5 text-[12px] font-medium text-white tabular-nums backdrop-blur-md">
            {formatDuration(video.duration_s)}
          </span>
        )}
        <WatchOverlay video={video} />
      </div>
      <div className="min-w-0 px-0.5">
        <Heading
          className={cn(
            "line-clamp-2 text-[15px] leading-snug font-medium",
            video.progress?.watched && "text-secondary",
          )}
        >
          {video.title}
        </Heading>
        {meta && <p className="mt-1 truncate text-[13px] text-secondary">{meta}</p>}
      </div>
    </Link>
  );
}

export function VideoCardSkeleton() {
  return (
    <div className="flex flex-col gap-3" aria-hidden>
      <div className="aspect-video animate-pulse rounded-2xl bg-surface" />
      <div className="space-y-2 px-0.5">
        <div className="h-4 w-4/5 animate-pulse rounded bg-surface" />
        <div className="h-3 w-2/5 animate-pulse rounded bg-surface" />
      </div>
    </div>
  );
}
