import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: ".", testMatch: ["world-image-recovery.spec.ts", "creator-copy-ui.spec.ts"],
  workers: 1, retries: 0, timeout: 90_000, expect: { timeout: 15_000 },
  outputDir: "../artifacts/world-image-recovery-20261012/browser",
  reporter: [["list"], ["json", { outputFile: "../artifacts/world-image-recovery-20261012/browser-results.json" }]],
  use: { ...devices["Desktop Chrome"], serviceWorkers: "block", timezoneId: "Asia/Seoul", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [
    { name: "next", use: { baseURL: "http://127.0.0.1:3380" } },
    { name: "static-export", use: { baseURL: "http://127.0.0.1:3385" } },
  ],
});
