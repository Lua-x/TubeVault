import { Link } from "react-router";

import { cn } from "@/lib/cn";
import { channelImageUrl } from "@/lib/media";
import type { Subscription } from "@/lib/types";

import { ChannelAvatar } from "./ChannelAvatar";
import { checkStatus } from "./status";

export function SubscriptionCard({ sub }: { sub: Subscription }) {
  const status = checkStatus(sub);
  const banner = sub.kind === "channel" && sub.channel?.has_banner ? sub.channel : null;
  const counts = [
    `${sub.stats.downloaded} ${sub.stats.downloaded === 1 ? "Video" : "Videos"}`,
    sub.stats.queued ? `${sub.stats.queued} in der Warteschlange` : null,
  ].filter(Boolean);

  return (
    <Link
      to={`/subscriptions/${sub.id}`}
      className={cn(
        "group flex flex-col overflow-hidden rounded-2xl bg-elevated shadow-[0_0_0_1px_var(--tv-separator)]",
        "transition-[transform,box-shadow] duration-300 ease-out-soft hover:-translate-y-0.5 hover:shadow-card",
        !sub.enabled && "opacity-70",
      )}
    >
      <div className="relative h-20 bg-surface">
        {banner && (
          <img
            src={channelImageUrl(banner, "banner")}
            alt=""
            loading="lazy"
            className="size-full object-cover"
          />
        )}
      </div>
      <div className="flex items-start gap-3 px-4 pb-4">
        <ChannelAvatar
          channel={sub.channel}
          name={sub.title}
          kind={sub.kind}
          className="relative z-10 -mt-7 size-14 border-4 border-elevated bg-surface text-[22px]"
        />
        <div className="min-w-0 flex-1 pt-2">
          <h3 className="truncate text-[16px] font-semibold">{sub.title}</h3>
          <p className="text-[13px] text-secondary">
            {sub.kind === "channel" ? "Kanal" : "Playlist"} · {counts.join(" · ")}
          </p>
          <p
            className={cn(
              "mt-1 line-clamp-1 text-[12px]",
              status.tone === "danger" && "text-danger",
              status.tone === "accent" && "text-accent",
              status.tone === "muted" && "text-tertiary",
            )}
          >
            {status.text}
          </p>
        </div>
      </div>
    </Link>
  );
}
