import { defineConfig } from "@playwright/test";
import base from "./playwright.config";

// The fixture origin is task-owned. Record the real production mode so the
// pre-existing request-ledger assertions do not apply dev Strict Mode counts.
export default defineConfig({ ...base,
  metadata: { nextRuntime: "production" },
  webServer: [{ command: "node ../frontend/scripts/serve-production.mjs --port 3300", env: { ANGMOO_API_BASE_URL: "http://127.0.0.1:3302" }, url: "http://127.0.0.1:3300", reuseExistingServer: false, timeout: 90_000 }],
  use: { ...base.use, baseURL: "http://127.0.0.1:3300" },
  outputDir: "../artifacts/responsive-shell-20261004/legacy-next",
  reporter: [["line"], ["json", { outputFile: "../artifacts/responsive-shell-20261004/legacy-next-results.json" }]],
});
