import { defineConfig, devices } from "@playwright/test";

const nextBaseURL = "http://127.0.0.1:3300";
const staticBaseURL = "http://127.0.0.1:3301";

export default defineConfig({
  testDir: ".",
  testMatch: "semantic-foundation.visual.spec.ts",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: process.env.CI ? "github" : "list",
  timeout: 45_000,
  workers: 1,
  outputDir: "test-results/visual",
  snapshotPathTemplate: "{testDir}/snapshots/ui-b/{arg}{ext}",
  expect: {
    timeout: 10_000,
    toHaveScreenshot: {
      animations: "disabled",
      caret: "hide",
      maxDiffPixels: 25,
      scale: "css",
      threshold: 0.1,
    },
  },
  use: {
    ...devices["Desktop Chrome"],
    colorScheme: "light",
    contextOptions: { reducedMotion: "reduce" },
    deviceScaleFactor: 1,
    locale: "ko-KR",
    screenshot: "only-on-failure",
    serviceWorkers: "block",
    timezoneId: "Asia/Seoul",
    trace: "retain-on-failure",
    viewport: { width: 436, height: 880 },
  },
  projects: [
    {
      name: "next-production",
      use: { baseURL: nextBaseURL },
    },
    {
      name: "static-export",
      use: { baseURL: staticBaseURL },
    },
  ],
  webServer: [
    {
      command: "node ../frontend/scripts/serve-production.mjs --port 3300",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      url: nextBaseURL,
    },
    {
      command: "node ../frontend/scripts/serve-static.mjs --port 3301",
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
      url: staticBaseURL,
    },
  ],
});
