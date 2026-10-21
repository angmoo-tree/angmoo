import nextConfig from "./playwright.world-feed-ui.config";
import staticConfig from "./playwright.world-feed-ui-static.config";
const config = process.env.ANGMOO_RUNTIME_PAGES_STATIC === "1" ? staticConfig : nextConfig;

export default { ...config, testMatch: "runtime-pages.spec.ts", timeout: 60000,
  outputDir: `../artifacts/runtime-pages-20261021/${process.env.ANGMOO_RUNTIME_PAGES_STATIC === "1" ? "static" : "next"}`,
  reporter: [["list"], ["json", { outputFile: "../artifacts/runtime-pages-20261021/results.json" }]],
};
