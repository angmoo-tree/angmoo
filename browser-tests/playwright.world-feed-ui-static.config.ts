import config from "./playwright.world-feed-ui.config";

export default {
  ...config, outputDir: "../artifacts/world-feed-ui-20261004/static",
  reporter: [["list"], ["json", { outputFile: "../artifacts/world-feed-ui-20261004/static-results.json" }]],
  projects: [{ name: "static-export", use: { baseURL: "http://127.0.0.1:3331" } }],
  webServer: [{ command: "node ../frontend/scripts/serve-static.mjs --port 3331", url: "http://127.0.0.1:3331", reuseExistingServer: false, timeout: 30_000 }],
};
