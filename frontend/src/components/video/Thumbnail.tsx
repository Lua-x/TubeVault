import { Film } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/cn";
import { thumbnailUrl } from "@/lib/media";
import type { VideoSummary } from "@/lib/types";

interface ThumbnailProps {
  video: Pick<VideoSummary, "id" | "updated_at" | "has_thumbnail" | "title">;
  className?: string;
  eager?: boolean;
  /** "large" where the picture is shown big. */
  size?: "small" | "large";
}

export function Thumbnail({ video, className, eager, size = "small" }: ThumbnailProps) {
  const [failed, setFailed] = useState(false);
  if (!video.has_thumbnail || failed) {
    return (
      <div className={cn("flex items-center justify-center bg-surface text-tertiary", className)}>
        <Film className="size-8" strokeWidth={1.25} />
      </div>
    );
  }
  return (
    <img
      src={thumbnailUrl(video, size)}
      alt=""
      loading={eager ? "eager" : "lazy"}
      decoding="async"
      onError={() => setFailed(true)}
      className={cn("bg-surface object-cover", className)}
    />
  );
}
