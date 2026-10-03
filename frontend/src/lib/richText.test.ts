import { describe, expect, it } from "vitest";

import { tokenize } from "./richText";

describe("tokenize", () => {
  it("finds timestamps and links", () => {
    expect(
      tokenize("Ab 1:05 geht's los, Teil 2 bei 1:02:03 – mehr: https://example.org/x."),
    ).toEqual([
      { kind: "text", text: "Ab " },
      { kind: "time", text: "1:05", seconds: 65 },
      { kind: "text", text: " geht's los, Teil 2 bei " },
      { kind: "time", text: "1:02:03", seconds: 3723 },
      { kind: "text", text: " – mehr: " },
      { kind: "link", text: "https://example.org/x" },
      { kind: "text", text: "." },
    ]);
  });

  it("ignores times beyond the video and things that only look like times", () => {
    expect(tokenize("Um 14:30 im Stream", 600)).toEqual([
      { kind: "text", text: "Um 14:30 im Stream" },
    ]);
    expect(tokenize("Datum 2024:01:02 und 1:2345 und 3:75")).toEqual([
      { kind: "text", text: "Datum 2024:01:02 und 1:2345 und 3:75" },
    ]);
  });

  it("keeps timestamps inside the video", () => {
    expect(tokenize("Siehe 9:59", 600)).toEqual([
      { kind: "text", text: "Siehe " },
      { kind: "time", text: "9:59", seconds: 599 },
    ]);
  });
});
