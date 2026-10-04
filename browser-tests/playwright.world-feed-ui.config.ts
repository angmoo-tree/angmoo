import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".", testMatch: "world-feed-ui.spec.ts", workers: 1, fullyParallel: false, retries: 0, timeout: 45_000,
  outputDir: "../artifacts/world-feed-ui-20261004/next",
  reporter: [["list"], ["json", { outputFile: "../artifacts/world-feed-ui-20261004/next-results.json" }]],
  use: { ...devices["Desktop Chrome"], locale: "ko-KR", timezoneId: "Asia/Seoul", serviceWorkers: "block", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [{ name: "next-production", use: { baseURL: "http://127.0.0.1:3330" } }],
  webServer: [
    { command: "node ../frontend/scripts/serve-production.mjs --port 3330", env: { ANGMOO_API_BASE_URL: "http://127.0.0.1:3332" }, url: "http://127.0.0.1:3330", reuseExistingServer: false, timeout: 90_000 },
    { command: "node visual-fixture-server.mjs", env: { ANGMOO_VISUAL_FIXTURE_PORT: "3332" }, url: "http://127.0.0.1:3332/health", reuseExistingServer: false, timeout: 30_000 },
  ],
});
