import { describe, expect, it } from "vitest";

import {
  codecLabel,
  formatBytes,
  formatDuration,
  formatEta,
  formatRelative,
  formatResolution,
} from "./format";

describe("formatDuration", () => {
  it("formats minutes and hours", () => {
    expect(formatDuration(5)).toBe("0:05");
    expect(formatDuration(65)).toBe("1:05");
    expect(formatDuration(3725)).toBe("1:02:05");
    expect(formatDuration(null)).toBe("");
  });
});

describe("formatBytes", () => {
  it("uses decimal units", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1_500_000)).toBe("1,5 MB");
    expect(formatBytes(2_000_000_000)).toBe("2 GB");
  });
});

describe("formatEta", () => {
  it("reads naturally", () => {
    expect(formatEta(30)).toBe("noch 30 s");
    expect(formatEta(600)).toBe("noch 10 min");
  });
});

describe("formatRelative", () => {
  it("handles plain dates and timestamps", () => {
    const now = new Date("2026-10-02T12:00:00Z").getTime();
    expect(formatRelative("2026-10-01T12:00:00Z", now)).toBe("gestern");
    expect(formatRelative("2026-10-02T11:59:50Z", now)).toBe("gerade eben");
  });
});

describe("labels", () => {
  it("maps codecs and resolutions", () => {
    expect(codecLabel("avc1.640028")).toBe("H.264");
    expect(codecLabel("vp09.00.40.08")).toBe("VP9");
    expect(codecLabel("none")).toBe("");
    expect(formatResolution(2160)).toBe("4K");
    expect(formatResolution(720)).toBe("720p");
    expect(formatResolution(1920, 1080)).toBe("1080p");
    expect(formatResolution(3840, 2160)).toBe("4K");
    expect(formatResolution(4320, 7680)).toBe("8K");
  });
});
