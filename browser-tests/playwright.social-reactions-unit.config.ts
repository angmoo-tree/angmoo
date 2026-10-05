import { defineConfig } from "@playwright/test";
export default defineConfig({ testDir: ".", testMatch: "social-reactions-unit.spec.ts", workers: 1,
  reporter: [["list"], ["json", { outputFile: "../artifacts/world-post-reactions-20261005/unit-results.json" }]],
  outputDir: "../artifacts/world-post-reactions-20261005/unit" });
