import config from "./playwright.world-feed-ui.config";

const baseURL = process.env.ANGMOO_SOCIAL_PREVIEW_URL;
if (!baseURL) throw new Error("A task-owned ANGMOO_SOCIAL_PREVIEW_URL is required");
const staticExport = process.env.ANGMOO_SOCIAL_REGRESSION_KIND === "static";
const mode = staticExport ? "static" : "next";

export default { ...config,
  testMatch: ["world-feed-ui.spec.ts", staticExport ? "static-product-shell.spec.ts" : "product-shell.spec.ts"],
  // Reuse existing tests for preserved behavior. Profile editing and World
  // management have their own updated tests for the new World-only contracts.
  grep: /header owner|title and body|failed submission|preview, publication|photo replacement|upload pending|feed failure|pull refresh|World identity|missing owner|unavailable World|late World A|photo trigger|changed content|global and World|existing post row|responsive positions|global post detail|static feed paginates|static global social rows|static global detail|static feed .*hydrated/,
  projects: [{ name: staticExport ? "static-export" : "next-production", use: { baseURL } }],
  webServer: undefined,
  outputDir: `../artifacts/world-post-reactions-20261005/${mode}-preservation`,
  reporter: [["list"], ["json", { outputFile: `../artifacts/world-post-reactions-20261005/${mode}-preservation-results.json` }]],
};
