import { Link } from "react-router";

import { useSimilarVideos } from "@/api/queries";
import { Thumbnail } from "@/components/video/Thumbnail";
import { WatchOverlay } from "@/components/video/WatchOverlay";
import { formatDuration } from "@/lib/format";

/** More from the library about the same thing, then from the same channel. */
export function SimilarVideos({ videoId }: { videoId: number }) {
  const { data: videos } = useSimilarVideos(videoId);
  if (!videos || videos.length === 0) return null;
  return (
    <section aria-labelledby="similar-heading">
      <h2 id="similar-heading" className="mb-3 text-[17px] font-semibold">
        Ähnliche Videos
      </h2>
      <ul className="flex flex-col gap-3">
        {videos.map((video) => (
          <li key={video.id}>
            <Link to={`/videos/${video.id}`} className="group flex gap-3">
              <div className="relative aspect-video w-40 shrink-0 overflow-hidden rounded-lg">
                <Thumbnail
                  video={video}
                  className="size-full transition-transform duration-300 ease-out-soft group-hover:scale-105"
                />
                <WatchOverlay video={video} />
              </div>
              <div className="min-w-0 py-0.5">
                <p className="line-clamp-2 text-[14px] leading-snug font-medium">{video.title}</p>
                <p className="mt-1 truncate text-[12px] text-secondary">
                  {[video.channel?.name, formatDuration(video.duration_s)]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
