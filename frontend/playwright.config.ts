import { defineConfig, devices } from "@playwright/test";

// Browser tests against a real TubeVault with demo videos (see e2e/serve.sh).
const port = 18823;

export default defineConfig({
  testDir: "e2e",
  testMatch: "**/*.e2e.ts",
  timeout: 30_000,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    locale: "de-DE",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "sh e2e/serve.sh",
    url: `http://127.0.0.1:${port}/api/health`,
    timeout: 300_000,
    reuseExistingServer: !process.env.CI,
    env: { E2E_PORT: String(port) },
  },
});
