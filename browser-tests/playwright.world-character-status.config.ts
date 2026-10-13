import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: ["world-character-status.spec.ts", "world-memory-integration-ui.spec.ts"],
  workers: 1, retries: 0, timeout: 90000, expect: { timeout: 20000 },
  outputDir: "../artifacts/world-character-status-20261007/browser",
  reporter: [["list"], ["json", { outputFile: `../artifacts/world-character-status-20261007/${process.env.ANGMOO_STATUS_RUN ?? "browser"}-results.json` }]],
  use: { ...devices["Desktop Chrome"], locale: "ko-KR", timezoneId: "Asia/Seoul", serviceWorkers: "block", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [
    { name: "next-preview", use: { baseURL: process.env.ANGMOO_STATUS_NEXT_URL ?? "http://127.0.0.1:3338" } },
    ...(process.env.ANGMOO_STATUS_STATIC_URL ? [{ name: "static-export", use: { baseURL: process.env.ANGMOO_STATUS_STATIC_URL } }] : []),
  ],
});
