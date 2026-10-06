import config from "./playwright.world-chat-delete.config";
import { resolve } from "node:path";
const offlinePython = resolve(__dirname, "../scripts/testing/offline-python");
const backendPath = resolve(__dirname, "../backend");
const baseURL = process.env.ANGMOO_CHAT_NEXT_BASE_URL || "http://127.0.0.1:3353";
export default { ...config, testMatch: "world-chat-delete-backend.spec.ts",
  outputDir: "../artifacts/world-post-detail-chat-management-20261005/chat-backend-next",
  reporter: [["list"], ["json", { outputFile: "../artifacts/world-post-detail-chat-management-20261005/chat-backend-next-results.json" }]],
  projects: [{ name: "next-production", use: { baseURL } }],
  webServer: [
    { command: "node ../frontend/scripts/serve-production.mjs --port 3353", env: { ANGMOO_API_BASE_URL: "http://127.0.0.1:3354" }, url: baseURL, reuseExistingServer: Boolean(process.env.ANGMOO_CHAT_NEXT_BASE_URL), timeout: 90000 },
    { command: process.platform === "win32" ? '"..\\backend\\.venv\\Scripts\\python.exe" world-chat-delete-fixture.py' : "../backend/.venv/bin/python world-chat-delete-fixture.py", env: { PYTHONPATH: [offlinePython, backendPath].join(process.platform === "win32" ? ";" : ":") }, url: "http://127.0.0.1:3354/fixture/evidence", reuseExistingServer: false, timeout: 90000 },
  ],
};
