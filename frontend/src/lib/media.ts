import { apiUrl } from "./base";
import type { VideoSummary } from "./types";

export function thumbnailUrl(video: Pick<VideoSummary, "id" | "updated_at">): string {
  return apiUrl(`videos/${video.id}/thumbnail?v=${encodeURIComponent(video.updated_at)}`);
}

export function channelImageUrl(
  channel: { id: number; updated_at: string },
  kind: "avatar" | "banner",
): string {
  return apiUrl(`channels/${channel.id}/${kind}?v=${encodeURIComponent(channel.updated_at)}`);
}
