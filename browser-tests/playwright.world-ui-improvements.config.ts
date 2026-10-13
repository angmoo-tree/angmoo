import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: ["world-ui-improvements.spec.ts", "world-character-status.spec.ts"],
  workers: 1, retries: 0, timeout: 90_000, expect: { timeout: 20_000 },
  outputDir: "../artifacts/world-ui-improvements-20261009/browser",
  reporter: [["list"], ["json", { outputFile: "../artifacts/world-ui-improvements-20261009/browser-results.json" }]],
  // route.fulfill() serves the static dev document fallback without a socket
  // address. Permit only this test browser's loopback HMR connection; no product
  // runtime or installed-browser security setting is changed.
  use: { ...devices["Desktop Chrome"], launchOptions: { args: ["--disable-features=LocalNetworkAccessChecks"] }, locale: "ko-KR", timezoneId: "Asia/Seoul", serviceWorkers: "block", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [
    { name: "next", use: { baseURL: process.env.ANGMOO_WORLD_UI_NEXT_URL ?? "http://127.0.0.1:3347" } },
    { name: "static-export", use: { baseURL: process.env.ANGMOO_WORLD_UI_STATIC_URL ?? "http://127.0.0.1:3348" } },
  ],
});
