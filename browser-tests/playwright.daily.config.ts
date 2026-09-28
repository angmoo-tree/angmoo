import { defineConfig, devices } from "@playwright/test";
const staticShell = process.env.ANGMOO_DAILY_STATIC === "1";
const port = staticShell ? 3342 : 3341;
export default defineConfig({ testDir: ".", testMatch: "daily-preparation.spec.ts", workers: 1,
  timeout: 60_000, expect: { timeout: 15000 }, reporter: "list",
  use: { ...devices["Desktop Chrome"], baseURL: `http://127.0.0.1:${port}`, trace: "retain-on-failure" },
  webServer: { command: staticShell ? `node ../frontend/scripts/serve-static.mjs --port ${port}` : `pnpm --dir ../frontend start --hostname 127.0.0.1 --port ${port}`,
    url: `http://127.0.0.1:${port}`, reuseExistingServer: false, timeout: 120_000 },
});
