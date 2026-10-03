import { afterEach, describe, expect, it } from "vitest";

import { apiUrl, appPath, basePath } from "./base";

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

describe("appPath", () => {
  it("strips the base path", () => {
    document.head.innerHTML = '<base href="/tubevault/">';
    window.history.replaceState(null, "", "/tubevault/library");
    expect(appPath()).toBe("/library");
    document.head.innerHTML = "";
    window.history.replaceState(null, "", "/videos/3");
    expect(appPath()).toBe("/videos/3");
  });
});
