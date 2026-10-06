import config from "./playwright.world-chat-delete.config";
const baseURL = process.env.ANGMOO_CHAT_STATIC_BASE_URL || "http://127.0.0.1:3351";
export default { ...config,
  outputDir: "../artifacts/world-post-detail-chat-management-20261005/chat-static",
  reporter: [["list"], ["json", { outputFile: "../artifacts/world-post-detail-chat-management-20261005/chat-static-results.json" }]],
  projects: [{ name: "static-export", use: { baseURL } }],
  webServer: [{ command: "node ../frontend/scripts/serve-static.mjs --port 3351", url: baseURL,
    reuseExistingServer: Boolean(process.env.ANGMOO_CHAT_STATIC_BASE_URL), timeout: 30000 }],
};
