import { defineConfig, devices } from "@playwright/test";

const nextBaseURL = "http://127.0.0.1:3300";
const staticBaseURL = "http://127.0.0.1:3301";
const fixtureBaseURL = "http://127.0.0.1:3302";

export default defineConfig({
  testDir: ".",
  testMatch: [
    "semantic-foundation.visual.spec.ts",
    "product-surfaces.visual.spec.ts",
  ],
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: process.env.CI ? "github" : "list",
  timeout: 45_000,
  workers: 1,
  outputDir: "test-results/visual",
  snapshotPathTemplate: "{testDir}/snapshots/{arg}{ext}",
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
      env: { ANGMOO_API_BASE_URL: fixtureBaseURL },
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
    {
      command: "node visual-fixture-server.mjs",
      env: { ANGMOO_VISUAL_FIXTURE_PORT: "3302" },
      reuseExistingServer: false,
      timeout: 30_000,
      url: `${fixtureBaseURL}/health`,
    },
  ],
});
