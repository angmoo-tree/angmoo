import config from "./playwright.world-notifications.config";
import { resolve } from "node:path";
const offlinePython = resolve(__dirname, "../scripts/testing/offline-python");
const backendPath = resolve(__dirname, "../backend");
export default { ...config, testMatch: "world-notifications-backend.spec.ts",
  outputDir: "../artifacts/world-notifications-bulk-20261015/browser-backend",
  reporter: [["list"], ["json", { outputFile: "../artifacts/world-notifications-bulk-20261015/browser-backend.json" }]],
  projects: [
    { name: "next-production", use: { baseURL: "http://127.0.0.1:3393" } },
    { name: "static-export", use: { baseURL: "http://127.0.0.1:3395" } },
  ],
  webServer: [
    { command: "node ../frontend/scripts/serve-production.mjs --port 3393", env: { ANGMOO_API_BASE_URL: "http://127.0.0.1:3394" }, url: "http://127.0.0.1:3393", reuseExistingServer: false, timeout: 90_000 },
    { command: "node ../frontend/scripts/serve-static.mjs --port 3395", url: "http://127.0.0.1:3395", reuseExistingServer: false, timeout: 30_000 },
    { command: process.platform === "win32" ? '"..\\backend\\.venv\\Scripts\\python.exe" world-notifications-backend-fixture.py' : "../backend/.venv/bin/python world-notifications-backend-fixture.py",
      env: { PYTHONPATH: [offlinePython, backendPath].join(process.platform === "win32" ? ";" : ":") },
      url: "http://127.0.0.1:3394/fixture/evidence", reuseExistingServer: false, timeout: 90_000 },
  ],
};
