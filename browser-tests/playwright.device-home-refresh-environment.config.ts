import { defineConfig, devices } from "@playwright/test";

const baseline = process.env.ANGMOO_HOME_BASELINE === "1";
const python = process.platform === "win32" ? "..\\backend\\.venv\\Scripts\\python.exe" : "../backend/.venv/bin/python";
export default defineConfig({
  testDir: ".", testMatch: "device-home-refresh-environment.spec.ts", workers: 1, retries: 0, timeout: 45_000,
  outputDir: `../artifacts/device-home-refresh-environment-20261016/${baseline ? "baseline" : "browser"}`,
  reporter: [["list"], ["json", { outputFile: `../artifacts/device-home-refresh-environment-20261016/${baseline ? "baseline" : "browser"}.json` }]],
  use: { ...devices["Desktop Chrome"], locale: "ko-KR", timezoneId: "Asia/Seoul", serviceWorkers: "block", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [{ name: "next-production", use: { baseURL: "http://127.0.0.1:3480" } },
    ...baseline ? [] : [{ name: "static-export", use: { baseURL: "http://127.0.0.1:3481" } }]],
  webServer: [
    ...baseline ? [] : [{ command: `"${python}" fixtures/home-environment-server.py`, url: "http://127.0.0.1:3483/_test/health", reuseExistingServer: false, timeout: 30_000 }],
    { command: "node ../frontend/scripts/serve-production.mjs --port 3480", env: { ANGMOO_API_BASE_URL: "http://127.0.0.1:3482" }, url: "http://127.0.0.1:3480", reuseExistingServer: false, timeout: 90_000 },
    { command: "node visual-fixture-server.mjs", env: { ANGMOO_VISUAL_FIXTURE_PORT: "3482" }, url: "http://127.0.0.1:3482/health", reuseExistingServer: false, timeout: 30_000 },
    ...baseline ? [] : [{ command: "node ../frontend/scripts/serve-static.mjs --port 3481", url: "http://127.0.0.1:3481", reuseExistingServer: false, timeout: 30_000 }],
  ],
});
