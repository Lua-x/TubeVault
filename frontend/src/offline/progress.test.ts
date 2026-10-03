import { afterEach, describe, expect, it } from "vitest";

import {
  forgetLocalProgress,
  forgetOwner,
  lastOwner,
  loadLocalProgress,
  rememberOwner,
  saveLocalProgress,
} from "./progress";

afterEach(() => localStorage.clear());

describe("offline progress", () => {
  it("keeps each user's progress apart", () => {
    saveLocalProgress(1, 10, 42, 300);
    saveLocalProgress(2, 10, 7, 300);
    expect(loadLocalProgress(1)["10"]?.position_s).toBe(42);
    expect(loadLocalProgress(2)["10"]?.position_s).toBe(7);
    forgetLocalProgress(1, 10);
    expect(loadLocalProgress(1)).toEqual({});
    expect(loadLocalProgress(2)["10"]?.position_s).toBe(7);
  });

  it("remembers nothing without a user", () => {
    saveLocalProgress(null, 10, 42, 300);
    expect(loadLocalProgress(null)).toEqual({});
  });

  it("forgets the owner on sign-out", () => {
    expect(lastOwner()).toBeNull();
    rememberOwner(3);
    expect(lastOwner()).toBe(3);
    forgetOwner();
    expect(lastOwner()).toBeNull();
  });
});
