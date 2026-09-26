import { defineConfig, devices } from "@playwright/test";

const staticShell = process.env.ANGMOO_CREATOR_STATIC === "1";
const port = staticShell ? 3320 : 3310;
export default defineConfig({
  testDir: ".", testMatch: "local-creator.spec.ts", fullyParallel: false, workers: 1,
  timeout: 60_000, expect: { timeout: 15_000 }, reporter: "list",
  use: { ...devices["Desktop Chrome"], baseURL: `http://127.0.0.1:${port}`, trace: "retain-on-failure" },
  webServer: { command: staticShell ? `node ../frontend/scripts/serve-static.mjs --port ${port}`
    : `pnpm --dir ../frontend dev --hostname 127.0.0.1 --port ${port}`,
    url: `http://127.0.0.1:${port}`, reuseExistingServer: false, timeout: 120_000 },
});
