import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: ["world-introduction.spec.ts", "world-social-output.spec.ts", "world-feed-ui.spec.ts", "product-shell.spec.ts"],
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 20_000 },
  outputDir: `../artifacts/world-introduction-20261007/${process.env.ANGMOO_INTRO_RUN ?? "browser"}`,
  reporter: [["list"], ["json", { outputFile: `../artifacts/world-introduction-20261007/${process.env.ANGMOO_INTRO_RUN ?? "browser"}-results.json` }]],
  use: { ...devices["Desktop Chrome"], locale: "ko-KR", timezoneId: "Asia/Seoul", serviceWorkers: "block", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [
    { name: "next-preview", use: { baseURL: process.env.ANGMOO_INTRO_NEXT_URL ?? "http://127.0.0.1:3338" } },
    ...(process.env.ANGMOO_INTRO_STATIC_URL ? [{ name: "static-export", testIgnore: "product-shell.spec.ts", use: { baseURL: process.env.ANGMOO_INTRO_STATIC_URL } }] : []),
  ],
});
