import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: ".", testMatch: ["world-memory-integration-ui.spec.ts", "world-memory-extra-ui.spec.ts", "relationship-graph/product-shell.spec.ts", "local-creator.spec.ts", "product-shell.spec.ts", "static-product-shell.spec.ts"], workers: 1, retries: 0, timeout: 90000,
  expect: { timeout: 20000 },
  outputDir: "../artifacts/world-memory-integration-20261006/browser",
  reporter: [["list"], ["json", { outputFile: `../artifacts/world-memory-integration-20261006/${process.env.ANGMOO_BROWSER_RUN ?? "browser"}-results.json` }]],
  use: { ...devices["Desktop Chrome"], locale: "ko-KR", timezoneId: "Asia/Seoul", serviceWorkers: "block", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [{ name: "next-preview", use: { baseURL: process.env.ANGMOO_INTEGRATION_NEXT_URL ?? "http://127.0.0.1:3338" } },
    ...(process.env.ANGMOO_INTEGRATION_STATIC_URL ? [{ name: "static-export", use: { baseURL: process.env.ANGMOO_INTEGRATION_STATIC_URL } }] : [])],
});
