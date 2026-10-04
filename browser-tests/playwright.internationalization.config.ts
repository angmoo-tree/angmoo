import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".", testMatch: "internationalization.spec.ts", workers: 1, retries: 0,
  fullyParallel: false, timeout: 60_000, expect: { timeout: 15_000 },
  reporter: [["list"], ["json", {outputFile: "../artifacts/multilingual-ui-contract-fixes-20261004/browser-results.json"}]],
  outputDir: "../artifacts/multilingual-ui-contract-fixes-20261004/browser",
  use: {...devices["Desktop Chrome"], screenshot: "only-on-failure", trace: "retain-on-failure"},
  projects: [
    {name: "next", use: {baseURL: "http://127.0.0.1:3361"}},
    {name: "static", use: {baseURL: "http://127.0.0.1:3362"}},
  ],
  webServer: [
    {command: "uv run --project ../backend python ../scripts/diagnostics/serve_multilingual_fixture.py --data-root ../artifacts/multilingual-gemini-20261003/ui-contract-fixes-20261004/browser-data --port 18399",
      url: "http://127.0.0.1:18399/health", reuseExistingServer: false, timeout: 120_000},
    {command: "pnpm --dir ../frontend start --hostname 127.0.0.1 --port 3361", url: "http://127.0.0.1:3361", reuseExistingServer: false,
      env: {ANGMOO_API_BASE_URL: "http://127.0.0.1:18399"}, timeout: 120_000},
    {command: "node ../frontend/scripts/serve-static.mjs --port 3362", url: "http://127.0.0.1:3362", reuseExistingServer: false, timeout: 30_000},
  ],
  globalTeardown: "./internationalization-teardown.ts",
});
