import config from "./playwright.world-chat-delete-backend.config";
const baseURL = process.env.ANGMOO_CHAT_STATIC_BASE_URL || "http://127.0.0.1:3355";
export default { ...config,
  outputDir: "../artifacts/world-post-detail-chat-management-20261005/chat-backend-static",
  reporter: [["list"], ["json", { outputFile: "../artifacts/world-post-detail-chat-management-20261005/chat-backend-static-results.json" }]],
  projects: [{ name: "static-export", use: { baseURL } }],
  webServer: [
    { command: "node ../frontend/scripts/serve-static.mjs --port 3355", url: baseURL,
      reuseExistingServer: Boolean(process.env.ANGMOO_CHAT_STATIC_BASE_URL), timeout: 30000 },
    config.webServer[1],
  ],
};
