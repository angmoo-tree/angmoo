import config from "./playwright.world-feed-ui.config";
const baseURL = process.env.ANGMOO_CHAT_NEXT_BASE_URL || "http://127.0.0.1:3350";
export default { ...config, testMatch: "world-chat-dialog-delete.spec.ts",
  outputDir: "../artifacts/world-post-detail-chat-management-20261005/chat-next",
  reporter: [["list"], ["json", { outputFile: "../artifacts/world-post-detail-chat-management-20261005/chat-next-results.json" }]],
  projects: [{ name: "next-production", use: { baseURL } }],
  webServer: [
    { command: "node ../frontend/scripts/serve-production.mjs --port 3350", env: { ANGMOO_API_BASE_URL: "http://127.0.0.1:3352" }, url: baseURL, reuseExistingServer: Boolean(process.env.ANGMOO_CHAT_NEXT_BASE_URL), timeout: 90000 },
    { command: "node visual-fixture-server.mjs", env: { ANGMOO_VISUAL_FIXTURE_PORT: "3352" }, url: "http://127.0.0.1:3352/health", reuseExistingServer: false, timeout: 30000 },
  ],
};
