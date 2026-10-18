import { afterEach, describe, expect, it } from "vitest";

import { storedVolume, storeVolume } from "./volume";

describe("remembered volume", () => {
  afterEach(() => localStorage.clear());

  it("is kept, rounded and with mute", () => {
    expect(storedVolume()).toBeNull();
    storeVolume(0.4321, false);
    expect(storedVolume()).toEqual({ volume: 0.43, muted: false });
    storeVolume(0.8, true);
    expect(storedVolume()).toEqual({ volume: 0.8, muted: true });
  });

  it("ignores what doesn't make sense", () => {
    localStorage.setItem("tubevault.volume", "not json");
    expect(storedVolume()).toBeNull();
    localStorage.setItem("tubevault.volume", JSON.stringify({ volume: 7 }));
    expect(storedVolume()).toBeNull();
  });
});
