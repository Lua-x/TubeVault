import { ListVideo } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/cn";
import { channelImageUrl } from "@/lib/media";
import type { Channel, SubscriptionKind } from "@/lib/types";

interface ChannelAvatarProps {
  channel: Channel | null;
  name: string;
  kind?: SubscriptionKind;
  className?: string;
}

export function ChannelAvatar({ channel, name, kind = "channel", className }: ChannelAvatarProps) {
  const [failed, setFailed] = useState(false);
  const base = cn(
    "flex shrink-0 items-center justify-center overflow-hidden bg-surface text-secondary",
    kind === "playlist" ? "rounded-xl" : "rounded-full",
    className,
  );
  if (kind === "channel" && channel?.has_avatar && !failed) {
    return (
      <img
        src={channelImageUrl(channel, "avatar")}
        alt=""
        loading="lazy"
        onError={() => setFailed(true)}
        className={cn(base, "object-cover")}
      />
    );
  }
  return (
    <div className={base} aria-hidden>
      {kind === "playlist" ? (
        <ListVideo className="size-1/2" strokeWidth={1.5} />
      ) : (
        <span className="text-[40%] font-semibold uppercase">{name.slice(0, 1)}</span>
      )}
    </div>
  );
}
