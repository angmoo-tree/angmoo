import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: ".", testMatch: ["home-activity-memory.spec.ts", "world-ui-improvements.spec.ts", "world-character-status.spec.ts", "local-creator.spec.ts"],
  workers: 1, retries: 0, timeout: 90_000, expect: { timeout: 20_000 },
  outputDir: "../artifacts/home-activity-memory-20261010/browser",
  reporter: [["list"], ["json", { outputFile: "../artifacts/home-activity-memory-20261010/browser-results.json" }]],
  use: { ...devices["Desktop Chrome"], launchOptions: { args: ["--disable-features=LocalNetworkAccessChecks"] },
    locale: "ko-KR", timezoneId: "Asia/Seoul", serviceWorkers: "block", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [
    { name: "next", testMatch: ["home-activity-memory.spec.ts", "world-ui-improvements.spec.ts", "world-character-status.spec.ts", "local-creator.spec.ts", "product-shell.spec.ts"], use: { baseURL: "http://127.0.0.1:3370" } },
    { name: "static-export", testMatch: ["home-activity-memory.spec.ts", "world-ui-improvements.spec.ts", "world-character-status.spec.ts", "local-creator.spec.ts", "static-product-shell.spec.ts"], use: { baseURL: "http://127.0.0.1:3371" } },
  ],
});
