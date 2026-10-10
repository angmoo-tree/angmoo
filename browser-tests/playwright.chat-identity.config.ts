import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: ".", testMatch: ["chat-identity-evidence.spec.ts", "creator-copy-ui.spec.ts"],
  grep: /historical relationship|evidence lifetime|single column preview|world crop cancel/,
  workers: 1, retries: 0, timeout: 90_000, expect: { timeout: 20_000 },
  outputDir: "../artifacts/chat-identity-20261011/browser",
  reporter: [["list"], ["json", { outputFile: "../artifacts/chat-identity-20261011/browser-results.json" }]],
  use: { ...devices["Desktop Chrome"], permissions: ["local-network-access"], serviceWorkers: "block", timezoneId: "Asia/Seoul", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [{ name: "next", use: { baseURL: "http://127.0.0.1:3380" } }, { name: "static-router", use: { baseURL: "http://127.0.0.1:3381" } }],
});
