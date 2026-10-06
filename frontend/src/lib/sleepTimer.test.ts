import { afterEach, describe, expect, it, vi } from "vitest";

import { remainingLabel, setVideoSleep, videoSleep } from "./sleepTimer";

describe("video sleep timer", () => {
  afterEach(() => {
    setVideoSleep(null);
    vi.useRealTimers();
  });

  it("counts minutes, then seconds", () => {
    expect(remainingLabel(30 * 60_000, 0)).toBe("30 min");
    expect(remainingLabel(90_500, 0)).toBe("2 min");
    expect(remainingLabel(42_000, 0)).toBe("0:42");
    expect(remainingLabel(0, 5_000)).toBe("0:00");
  });

  it("is set, ends with the video, or is off", () => {
    vi.useFakeTimers();
    vi.setSystemTime(1_000_000);
    setVideoSleep(15);
    expect(videoSleep()).toEqual({ kind: "minutes", until: 1_000_000 + 15 * 60_000 });
    setVideoSleep("end");
    expect(videoSleep()).toEqual({ kind: "end" });
    setVideoSleep(null);
    expect(videoSleep()).toBeNull();
  });
});
