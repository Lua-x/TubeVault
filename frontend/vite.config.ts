import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

/** Stamps public/sw.js with a hash of the build, so each release gets a fresh cache,
 * and the list of built assets – all of them are cached at install, so the app (player
 * included) starts without the server even if a page was never opened before. */
function serviceWorkerBuildId(): Plugin {
  return {
    name: "tubevault-sw-build-id",
    apply: "build",
    async writeBundle(options, bundle) {
      if (!options.dir) return;
      const id = createHash("sha256")
        .update(Object.keys(bundle).sort().join("\n"))
        .digest("hex")
        .slice(0, 12);
      const file = join(options.dir, "sw.js");
      const source = await readFile(file, "utf8");
      const assets = Object.keys(bundle).filter((name) => name.startsWith("assets/"));
      await writeFile(
        file,
        source
          .replaceAll("__BUILD_ID__", id)
          .replace("[] /* __ASSETS__ */", JSON.stringify(assets)),
      );
    },
  };
}

const backend = process.env.TUBEVAULT_BACKEND ?? "http://127.0.0.1:8096";

export default defineConfig({
  // Relative asset paths: the server injects <base href> for the configured BASE_PATH,
  // so the same build works under any sub-path.
  base: "./",
  plugins: [react(), tailwindcss(), serviceWorkerBuildId()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    proxy: {
      "/api": { target: backend, ws: true, changeOrigin: false },
    },
  },
  build: {
    target: "es2022",
    chunkSizeWarningLimit: 1200,
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
