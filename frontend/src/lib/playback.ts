import type { PlaybackInfo } from "./types";

/** What the viewer picked in the quality menu: the best possible or a converted height. */
export type QualityChoice = "auto" | number;

export type PlaybackPlan =
  { kind: "direct" } | { kind: "remux" } | { kind: "hls"; quality: "source" | number };

export type Fallback = "direct" | "remux";

const QUALITY_KEY = "tubevault.quality";

export function storedQuality(): QualityChoice {
  try {
    const value = localStorage.getItem(QUALITY_KEY);
    const height = Number(value);
    return value && Number.isInteger(height) && height > 0 ? height : "auto";
  } catch {
    return "auto";
  }
}

export function storeQuality(choice: QualityChoice): void {
  try {
    localStorage.setItem(QUALITY_KEY, String(choice));
  } catch {
    // Private mode: the choice just isn't remembered.
  }
}

function canPlay(type: string): boolean {
  if (typeof document === "undefined") return false;
  if (document.createElement("video").canPlayType(type) !== "") return true;
  return typeof MediaSource !== "undefined" && MediaSource.isTypeSupported(type);
}

function codecs(info: PlaybackInfo): string {
  return [info.video_codec, info.audio_codec].filter(Boolean).join(", ");
}

/** Whether the browser should manage the original file as it is. */
export function canPlayDirectly(info: PlaybackInfo, isWebKit: boolean): boolean {
  const list = codecs(info);
  const mp4 = `video/mp4; codecs="${list}"`;
  const webm = `video/webm; codecs="${list}"`;
  switch (info.container) {
    case "mp4":
    case "m4v":
    case "mov":
      return canPlay(mp4);
    case "webm":
      return canPlay(webm);
    case "mkv":
      // Chromium (and recent Firefox) read Matroska like WebM; Safari and iOS can't.
      return !isWebKit && (canPlay(webm) || canPlay(mp4));
    default:
      return false;
  }
}

export function canPlayRemuxed(info: PlaybackInfo): boolean {
  return info.can_remux && canPlay(`video/mp4; codecs="${codecs(info)}"`);
}

export function choosePlan(
  info: PlaybackInfo,
  choice: QualityChoice,
  failed: ReadonlySet<Fallback>,
  isWebKit: boolean,
): PlaybackPlan {
  if (choice !== "auto" && info.qualities.includes(choice)) return { kind: "hls", quality: choice };
  if (!failed.has("direct") && canPlayDirectly(info, isWebKit)) return { kind: "direct" };
  if (!failed.has("remux") && canPlayRemuxed(info)) return { kind: "remux" };
  return { kind: "hls", quality: "source" };
}

export function planHeight(plan: PlaybackPlan, info: PlaybackInfo): number | null {
  if (plan.kind !== "hls") return info.height;
  return plan.quality === "source" ? info.transcode_height : plan.quality;
}

/** MIME type for the original file. */
export function directSourceType(container: string | null): string {
  if (container === "mkv") {
    // Chromium plays Matroska but doesn't advertise the MIME type.
    const probe = document.createElement("video");
    return probe.canPlayType("video/x-matroska") ? "video/x-matroska" : "video/webm";
  }
  if (container === "webm") return "video/webm";
  return "video/mp4";
}
