import { Link } from "react-router";

import { ChannelAvatar } from "@/components/subscriptions/ChannelAvatar";
import type { ChannelCard } from "@/lib/types";

export function ChannelTile({ channel }: { channel: ChannelCard }) {
  const counts = [
    `${channel.video_count} ${channel.video_count === 1 ? "Video" : "Videos"}`,
    channel.unwatched_count > 0 && channel.unwatched_count < channel.video_count
      ? `${channel.unwatched_count} neu`
      : null,
  ].filter(Boolean);
  return (
    <Link
      to={`/channels/${channel.id}`}
      className="group flex flex-col items-center gap-3 rounded-2xl p-2 text-center"
    >
      <ChannelAvatar
        channel={channel}
        name={channel.name}
        className="aspect-square w-full max-w-[132px] text-[44px] shadow-[0_0_0_1px_var(--tv-separator)] transition-[transform,box-shadow] duration-300 ease-out-soft group-hover:scale-[1.04] group-hover:shadow-card"
      />
      <div className="min-w-0">
        <p className="line-clamp-2 text-[14px] leading-snug font-medium">{channel.name}</p>
        <p className="text-[12px] text-tertiary">{counts.join(" · ")}</p>
      </div>
    </Link>
  );
}
