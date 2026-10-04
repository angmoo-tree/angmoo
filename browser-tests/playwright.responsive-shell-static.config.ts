import { defineConfig } from "@playwright/test";
import base from "./playwright.responsive-shell.config";

export default defineConfig({
  ...base, outputDir: "../artifacts/responsive-shell-20261004/static",
  reporter: [["list"], ["json", { outputFile: "../artifacts/responsive-shell-20261004/static-results.json" }]],
  projects: [{ name: "static-export", use: { baseURL: "http://127.0.0.1:3301" } }],
  webServer: [
    { command: "node ../frontend/scripts/serve-static.mjs --port 3301", url: "http://127.0.0.1:3301", reuseExistingServer: false, timeout: 30_000 },
    { command: "node visual-fixture-server.mjs", env: { ANGMOO_VISUAL_FIXTURE_PORT: "3302" }, url: "http://127.0.0.1:3302/health", reuseExistingServer: false, timeout: 30_000 },
  ],
});
