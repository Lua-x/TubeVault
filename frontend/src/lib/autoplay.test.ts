import { afterEach, describe, expect, it } from "vitest";

import { nextInOrder, rememberPlayed, shuffleFrom } from "./autoplay";
import type { VideoSummary } from "./types";

const video = (id: number, watched = false) =>
  ({ id, progress: watched ? { watched: true } : null }) as unknown as VideoSummary;

describe("autoplay", () => {
  afterEach(() => sessionStorage.clear());

  it("remembers what was played in this tab, newest first", () => {
    rememberPlayed(1);
    rememberPlayed(2);
    expect(rememberPlayed(1)).toEqual([1, 2]);
  });

  it("shuffles among videos not played yet, unwatched ones first", () => {
    const list = [video(1), video(2, true), video(3), video(4)];
    expect(shuffleFrom(list, [1, 3], () => 0.99)?.id).toBe(4);
    expect(shuffleFrom(list, [1, 3, 4], () => 0)?.id).toBe(2); // only watched ones left
    expect(shuffleFrom(list, [1, 2, 3, 4])).toBeNull();
  });

  it("without shuffle takes the first unwatched one", () => {
    expect(nextInOrder([video(1, true), video(2), video(3)], [])?.id).toBe(2);
    expect(nextInOrder([video(1, true)], [])?.id).toBe(1);
  });
});
