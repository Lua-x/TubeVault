import type { ReactNode } from "react";
import { Link } from "react-router";

import { ChannelAvatar } from "@/components/subscriptions/ChannelAvatar";
import { Thumbnail } from "@/components/video/Thumbnail";
import { cn } from "@/lib/cn";
import { formatDuration } from "@/lib/format";
import type { ChannelCard, Playlist, VideoSummary } from "@/lib/types";

const focusRing =
  "transition-[transform,box-shadow] duration-200 ease-out group-focus:scale-[1.06] group-focus:shadow-[0_0_0_4px_white,0_24px_48px_rgb(0_0_0/0.6)]";

export function TvVideoTile({ video, to }: { video: VideoSummary; to: string }) {
  const progress = video.progress;
  const share =
    progress && !progress.watched && video.duration_s
      ? Math.min(1, progress.position_s / video.duration_s)
      : 0;
  return (
    <Link
      to={to}
      data-tv-focus
      data-tv-key={`video-${video.id}`}
      className="group block w-[max(16rem,22vw)] shrink-0 outline-none"
    >
      <div
        className={cn("relative aspect-video overflow-hidden rounded-2xl bg-surface", focusRing)}
      >
        <Thumbnail video={video} className="size-full object-cover" />
        {video.duration_s ? (
          <span className="absolute right-3 bottom-3 rounded-md bg-black/75 px-2 py-0.5 text-[max(14px,1vw)] font-medium text-white tabular-nums">
            {formatDuration(video.duration_s)}
          </span>
        ) : null}
        {share > 0 && (
          <span className="absolute inset-x-0 bottom-0 h-1.5 bg-white/25">
            <span className="block h-full bg-accent" style={{ width: `${share * 100}%` }} />
          </span>
        )}
      </div>
      <p className="mt-4 line-clamp-2 text-[max(17px,1.25vw)] leading-snug font-medium text-secondary group-focus:text-primary">
        {video.title}
      </p>
    </Link>
  );
}

export function TvChannelTile({ channel }: { channel: ChannelCard }) {
  return (
    <Link
      to={`/tv/channels/${channel.id}`}
      data-tv-focus
      data-tv-key={`channel-${channel.id}`}
      className="group flex w-[max(9rem,11vw)] shrink-0 flex-col items-center outline-none"
    >
      <span className={cn("block rounded-full", focusRing)}>
        <ChannelAvatar
          channel={channel}
          name={channel.name}
          className="size-[max(8rem,10vw)] text-[3vw]"
        />
      </span>
      <span className="mt-4 line-clamp-2 text-center text-[max(16px,1.1vw)] font-medium text-secondary group-focus:text-primary">
        {channel.name}
      </span>
    </Link>
  );
}

export function TvPlaylistTile({ playlist }: { playlist: Playlist }) {
  const cover = playlist.cover[0];
  return (
    <Link
      to={`/tv/playlists/${playlist.id}`}
      data-tv-focus
      data-tv-key={`playlist-${playlist.id}`}
      className="group block w-[max(16rem,22vw)] shrink-0 outline-none"
    >
      <div
        className={cn("relative aspect-video overflow-hidden rounded-2xl bg-surface", focusRing)}
      >
        {cover && <Thumbnail video={cover} className="size-full object-cover" />}
        <span className="absolute right-3 bottom-3 rounded-md bg-black/75 px-2 py-0.5 text-[max(14px,1vw)] font-medium text-white">
          {playlist.video_count} Videos
        </span>
      </div>
      <p className="mt-4 truncate text-[max(17px,1.25vw)] font-medium text-secondary group-focus:text-primary">
        {playlist.name}
      </p>
    </Link>
  );
}

export function TvRow({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="mt-[3vw]">
      <h2 className="text-[max(22px,1.8vw)] font-semibold tracking-tight">{title}</h2>
      {/* Room around the tiles for the focus zoom; scrolls as the focus moves. */}
      <div className="no-scrollbar -mx-[4vw] flex gap-[1.6vw] overflow-x-auto px-[4vw] py-[1.5vw]">
        {children}
      </div>
    </section>
  );
}
