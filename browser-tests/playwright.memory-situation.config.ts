import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".", testMatch: "memory-situation.spec.ts", workers: 1, retries: 0, timeout: 60000,
  expect: { timeout: 15000 }, outputDir: "../artifacts/situation-validation/browser",
  reporter: [["list"], ["json", { outputFile: "../artifacts/situation-validation/browser-results.json" }]],
  use: { ...devices["Desktop Chrome"], timezoneId: "Asia/Seoul", serviceWorkers: "block", trace: "retain-on-failure", screenshot: "only-on-failure" },
  webServer: [
    { command: "pnpm --dir ../frontend start --port 3349 --hostname 127.0.0.1", url: "http://127.0.0.1:3349", reuseExistingServer: false, timeout: 60000 },
    { command: "node ../frontend/scripts/serve-static.mjs --port 3350", url: "http://127.0.0.1:3350", reuseExistingServer: false, timeout: 60000 },
  ],
  projects: [
    { name: "next-preview", use: { baseURL: "http://127.0.0.1:3349" } },
    { name: "static-export", use: { baseURL: "http://127.0.0.1:3350" } },
  ],
});
