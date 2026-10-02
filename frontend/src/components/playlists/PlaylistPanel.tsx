import { ListVideo, SkipBack, SkipForward } from "lucide-react";
import { useEffect, useRef } from "react";
import { Link } from "react-router";

import { IconButton } from "@/components/ui/Button";
import { Thumbnail } from "@/components/video/Thumbnail";
import { WatchOverlay } from "@/components/video/WatchOverlay";
import { cn } from "@/lib/cn";
import { formatDuration } from "@/lib/format";
import type { PlaylistDetail } from "@/lib/types";

interface PlaylistPanelProps {
  playlist: PlaylistDetail;
  currentId: number;
  onNavigate: (videoId: number) => void;
}

/** The playlist next to the player: where we are, what comes next. */
export function PlaylistPanel({ playlist, currentId, onNavigate }: PlaylistPanelProps) {
  const index = playlist.videos.findIndex((v) => v.id === currentId);
  const previous = index > 0 ? playlist.videos[index - 1] : undefined;
  const next = index >= 0 ? playlist.videos[index + 1] : undefined;
  const listRef = useRef<HTMLOListElement>(null);

  useEffect(() => {
    const list = listRef.current;
    const item = list?.querySelector<HTMLElement>("[aria-current='true']");
    if (list && item) list.scrollTop = item.offsetTop - list.offsetTop - 8;
  }, [currentId]);

  return (
    <section aria-labelledby="playlist-heading" className="overflow-hidden rounded-2xl bg-elevated">
      <div className="flex items-center gap-3 border-b border-separator px-4 py-3">
        <ListVideo className="size-5 shrink-0 text-secondary" strokeWidth={1.75} />
        <div className="min-w-0 flex-1">
          <h2 id="playlist-heading" className="truncate text-[15px] font-semibold">
            <Link to={`/playlists/${playlist.id}`} className="hover:underline">
              {playlist.name}
            </Link>
          </h2>
          <p className="text-[12px] text-secondary tabular-nums">
            {index >= 0 ? `${index + 1} von ${playlist.videos.length}` : playlist.videos.length}
          </p>
        </div>
        <IconButton
          label="Vorheriges Video"
          disabled={!previous}
          onClick={() => previous && onNavigate(previous.id)}
          className="size-8"
        >
          <SkipBack className="size-4 fill-current" strokeWidth={1.75} />
        </IconButton>
        <IconButton
          label="Nächstes Video"
          disabled={!next}
          onClick={() => next && onNavigate(next.id)}
          className="size-8"
        >
          <SkipForward className="size-4 fill-current" strokeWidth={1.75} />
        </IconButton>
      </div>
      <ol ref={listRef} className="relative max-h-[360px] overflow-y-auto p-1.5 lg:max-h-[420px]">
        {playlist.videos.map((video, position) => {
          const current = video.id === currentId;
          return (
            <li key={video.id}>
              <Link
                to={`/videos/${video.id}?playlist=${playlist.id}`}
                aria-current={current ? "true" : undefined}
                className={cn(
                  "flex items-center gap-3 rounded-xl p-1.5 transition-colors duration-200",
                  current ? "bg-surface" : "hover:bg-surface/60",
                )}
              >
                <span
                  className={cn(
                    "w-5 shrink-0 text-center text-[12px] tabular-nums",
                    current ? "font-semibold text-accent" : "text-tertiary",
                  )}
                >
                  {current ? "▶" : position + 1}
                </span>
                <div className="relative aspect-video w-24 shrink-0 overflow-hidden rounded-lg">
                  <Thumbnail video={video} className="size-full" />
                  <WatchOverlay video={video} />
                </div>
                <div className="min-w-0 flex-1">
                  <p
                    className={cn(
                      "line-clamp-2 text-[13px] leading-snug",
                      current ? "font-semibold" : "font-medium",
                      video.progress?.watched && !current && "text-secondary",
                    )}
                  >
                    {video.title}
                  </p>
                  <p className="mt-0.5 truncate text-[12px] text-secondary">
                    {[video.channel?.name, formatDuration(video.duration_s)]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
              </Link>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
