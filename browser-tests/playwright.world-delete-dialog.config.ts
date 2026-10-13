import { defineConfig, devices } from "@playwright/test";

// All API requests terminate in the synthetic lifecycle fixture. The user's
// development server, backend and real Worlds are not used by this suite.
export default defineConfig({
  testDir: ".",
  testMatch: "chat-world-lifecycle.spec.ts",
  grep: /World lifecycle/,
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: [["list"], ["json", { outputFile: "../artifacts/world-delete-dialog-20261013/browser-results.json" }]],
  outputDir: "../artifacts/world-delete-dialog-20261013/browser",
  use: { ...devices["Desktop Chrome"], serviceWorkers: "block", screenshot: "only-on-failure", trace: "retain-on-failure" },
  projects: [
    { name: "next", use: { baseURL: "http://127.0.0.1:3417" } },
    { name: "static", use: { baseURL: "http://127.0.0.1:3418" } },
  ],
  webServer: [
    { command: "node fixtures/world-delete-next-server.mjs", env: { PORT: "3415", HOSTNAME: "127.0.0.1" }, url: "http://127.0.0.1:3415", reuseExistingServer: false, timeout: 60_000 },
    { command: "node ../frontend/scripts/serve-static.mjs --port 3416", url: "http://127.0.0.1:3416", reuseExistingServer: false, timeout: 30_000 },
    { command: "node fixtures/chat-world-lifecycle-server.mjs", url: "http://127.0.0.1:3417/__phase/audit", reuseExistingServer: false, timeout: 30_000 },
  ],
});
