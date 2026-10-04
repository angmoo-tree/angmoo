import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".", testMatch: "responsive-shell.spec.ts", fullyParallel: false,
  workers: 1, retries: 0, timeout: 45_000,
  outputDir: "../artifacts/responsive-shell-20261004/next",
  reporter: [["list"], ["json", { outputFile: "../artifacts/responsive-shell-20261004/next-results.json" }]],
  use: { ...devices["Desktop Chrome"], locale: "ko-KR", timezoneId: "Asia/Seoul", serviceWorkers: "block", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [{ name: "next-production", use: { baseURL: "http://127.0.0.1:3300" } }],
  webServer: [
    { command: "node ../frontend/scripts/serve-production.mjs --port 3300", env: { ANGMOO_API_BASE_URL: "http://127.0.0.1:3302" }, url: "http://127.0.0.1:3300", reuseExistingServer: false, timeout: 90_000 },
    { command: "node visual-fixture-server.mjs", env: { ANGMOO_VISUAL_FIXTURE_PORT: "3302" }, url: "http://127.0.0.1:3302/health", reuseExistingServer: false, timeout: 30_000 },
  ],
});
