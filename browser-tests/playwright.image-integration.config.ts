import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: ".", testMatch: "image-integration.spec.ts", workers: 1, fullyParallel: false, retries: 0,
  timeout: 60_000, expect: { timeout: 15_000 }, reporter: "list",
  outputDir: "../artifacts/image-integration/browser",
  use: { ...devices["Desktop Chrome"], trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [
    { name: "next", use: { baseURL: "http://127.0.0.1:3351" } },
    { name: "static", use: { baseURL: "http://127.0.0.1:3352" } },
  ],
  webServer: [
    { command: "pnpm --dir ../frontend start --hostname 127.0.0.1 --port 3351", url: "http://127.0.0.1:3351", reuseExistingServer: false, timeout: 120_000 },
    { command: "node ../frontend/scripts/serve-static.mjs --port 3352", url: "http://127.0.0.1:3352", reuseExistingServer: false, timeout: 30_000 },
  ],
});
