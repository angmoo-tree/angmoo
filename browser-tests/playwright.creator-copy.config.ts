import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: ".", testMatch: ["creator-copy-baseline.spec.ts", "creator-copy-media.spec.ts", "creator-copy-ui.spec.ts", "creator-copy-state.spec.ts", "local-creator.spec.ts"],
  workers: 1, retries: 0, timeout: 90_000, expect: { timeout: 20_000 },
  outputDir: "../artifacts/creator-copy-media-20261010/browser",
  reporter: [["list"], ["json", { outputFile: "../artifacts/creator-copy-media-20261010/browser-results.json" }]],
  use: { ...devices["Desktop Chrome"], serviceWorkers: "block", timezoneId: "Asia/Seoul",
    trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [
    { name: "next", use: { baseURL: "http://127.0.0.1:3380" } },
    { name: "static-export", testIgnore: "creator-copy-baseline.spec.ts", use: { baseURL: "http://127.0.0.1:3381" } },
  ],
});
