import { defineConfig, devices } from "@playwright/test";
const python = process.platform === "win32" ? "../backend/.venv/Scripts/python.exe" : "../backend/.venv/bin/python";
export default defineConfig({
  testDir: ".", testMatch: "local-entry.spec.ts", workers: 1, retries: 0, timeout: 45_000,
  outputDir: "../artifacts/local-entry-browser", reporter: [["list"], ["json", { outputFile: "../artifacts/local-entry-browser/results.json" }]],
  use: { ...devices["Desktop Chrome"], channel: "msedge", timezoneId: "America/New_York", serviceWorkers: "block", screenshot: "only-on-failure", trace: "retain-on-failure" },
  projects: [{ name: "next", use: { baseURL: "http://127.0.0.1:3490" } }, { name: "static", use: { baseURL: "http://127.0.0.1:3491" } }],
  webServer: [
    { command: `"${python}" fixtures/local-entry-server.py`, url: "http://127.0.0.1:3492/_test/health", reuseExistingServer: false, timeout: 45_000 },
    { command: "node ../frontend/node_modules/next/dist/bin/next start ../frontend --hostname 127.0.0.1 --port 3490", env: { ANGMOO_NEXT_DIST_DIR: ".next-local-stability", ANGMOO_API_BASE_URL: "http://127.0.0.1:3492" }, url: "http://127.0.0.1:3490", reuseExistingServer: false, timeout: 45_000 },
    { command: "node fixtures/serve-local-entry-static.mjs", url: "http://127.0.0.1:3491", reuseExistingServer: false, timeout: 30_000 },
  ],
});
