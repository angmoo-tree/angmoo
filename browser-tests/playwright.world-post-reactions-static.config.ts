import config from "./playwright.world-feed-ui-static.config";
const baseURL = process.env.ANGMOO_SOCIAL_PREVIEW_URL;
export default { ...config, testMatch: ["world-post-reactions.spec.ts"],
  projects: [{ name: "static-export", use: { baseURL: baseURL ?? "http://127.0.0.1:3331" } }],
  webServer: baseURL ? undefined : config.webServer,
  outputDir: "../artifacts/world-post-reactions-20261005/static",
  reporter: [["list"], ["json", { outputFile: "../artifacts/world-post-reactions-20261005/static-results.json" }]] };
