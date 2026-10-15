import config from "./playwright.world-notifications.config";
export default {
  ...config, outputDir: "../artifacts/world-user-notifications-20261015/browser-static",
  reporter: [["list"], ["json", { outputFile: "../artifacts/world-user-notifications-20261015/browser-static.json" }]],
  projects: [{ name: "static-export", use: { baseURL: "http://127.0.0.1:3391" } }],
  webServer: [{ command: "node ../frontend/scripts/serve-static.mjs --port 3391", url: "http://127.0.0.1:3391", reuseExistingServer: false, timeout: 30_000 }],
};
