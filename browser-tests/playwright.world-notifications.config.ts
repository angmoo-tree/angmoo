import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".", testMatch: "world-notifications.spec.ts", workers: 1, retries: 0, timeout: 45_000,
  outputDir: "../artifacts/world-notifications-bulk-20261015/browser-next",
  reporter: [["list"], ["json", { outputFile: "../artifacts/world-notifications-bulk-20261015/browser-next.json" }]],
  use: { ...devices["Desktop Chrome"], locale: "ko-KR", timezoneId: "Asia/Seoul", serviceWorkers: "block", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [{ name: "next-production", use: { baseURL: "http://127.0.0.1:3390" } }],
  webServer: [
    { command: "node ../frontend/scripts/serve-production.mjs --port 3390", env: { ANGMOO_API_BASE_URL: "http://127.0.0.1:3392" }, url: "http://127.0.0.1:3390", reuseExistingServer: false, timeout: 90_000 },
    { command: "node visual-fixture-server.mjs", env: { ANGMOO_VISUAL_FIXTURE_PORT: "3392" }, url: "http://127.0.0.1:3392/health", reuseExistingServer: false, timeout: 30_000 },
  ],
});
