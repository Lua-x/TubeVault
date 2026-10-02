import { afterEach, describe, expect, it, vi } from "vitest";

import { choosePlan, planHeight, type Fallback } from "./playback";
import type { PlaybackInfo } from "./types";

const base: PlaybackInfo = {
  container: "mp4",
  video_codec: "avc1.640028",
  audio_codec: "mp4a.40.2",
  width: 1920,
  height: 1080,
  duration: 120,
  can_remux: true,
  qualities: [720, 480],
  transcode_height: 1080,
};

/** Pretends the browser supports exactly the given containers and codecs. */
function supports(...needles: string[]) {
  vi.spyOn(HTMLMediaElement.prototype, "canPlayType").mockImplementation((type: string) =>
    needles.every((n) => type.includes(n)) ? "probably" : "",
  );
}

const none = new Set<Fallback>();

describe("choosePlan", () => {
  afterEach(() => vi.restoreAllMocks());

  it("plays MP4 with H.264 directly", () => {
    supports("mp4", "avc1");
    expect(choosePlan(base, "auto", none, false)).toEqual({ kind: "direct" });
  });

  it("remuxes MKV on WebKit and falls back to HLS when that fails", () => {
    supports("mp4");
    const mkv = { ...base, container: "mkv" };
    expect(choosePlan(mkv, "auto", none, true)).toEqual({ kind: "remux" });
    expect(choosePlan(mkv, "auto", new Set<Fallback>(["remux"]), true)).toEqual({
      kind: "hls",
      quality: "source",
    });
  });

  it("transcodes codecs the browser can't decode", () => {
    supports("webm", "vp09");
    const av1 = { ...base, video_codec: "av01.0.08M.08", audio_codec: "opus" };
    expect(choosePlan(av1, "auto", none, false)).toEqual({ kind: "hls", quality: "source" });
  });

  it("honours a chosen quality when it exists", () => {
    supports("mp4", "avc1");
    expect(choosePlan(base, 480, none, false)).toEqual({ kind: "hls", quality: 480 });
    expect(choosePlan(base, 360, none, false)).toEqual({ kind: "direct" });
    expect(planHeight({ kind: "hls", quality: "source" }, base)).toBe(1080);
  });
});
