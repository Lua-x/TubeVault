import { afterEach, describe, expect, it } from "vitest";

import { apiUrl, basePath } from "./base";

afterEach(() => {
  document.head.querySelectorAll("base").forEach((el) => el.remove());
});

describe("basePath", () => {
  it("defaults to the root", () => {
    expect(basePath()).toBe("/");
    expect(apiUrl("videos/1")).toBe("/api/videos/1");
  });

  it("follows the injected <base href>", () => {
    const base = document.createElement("base");
    base.setAttribute("href", "/tubevault/");
    document.head.appendChild(base);
    expect(basePath()).toBe("/tubevault/");
    expect(apiUrl("/health")).toBe("/tubevault/api/health");
  });
});
