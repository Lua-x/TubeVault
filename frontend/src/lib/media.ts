import { apiUrl } from "./base";
import type { VideoSummary } from "./types";

/** "small" (640 px) for cards and lists, "large" (1280 px) for the start page and the player.
 *  Both come from the server's image cache, so browsing leaves the media disks asleep. */
export function thumbnailUrl(
  video: Pick<VideoSummary, "id" | "updated_at">,
  size: "small" | "large" = "small",
): string {
  return apiUrl(
    `videos/${video.id}/thumbnail?size=${size}&v=${encodeURIComponent(video.updated_at)}`,
  );
}

export function channelImageUrl(
  channel: { id: number; updated_at: string },
  kind: "avatar" | "banner",
): string {
  return apiUrl(`channels/${channel.id}/${kind}?v=${encodeURIComponent(channel.updated_at)}`);
}
